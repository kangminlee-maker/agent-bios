#!/usr/bin/env python3
"""S5 retrieve and check (plan WP-10; design §6.2 retrieval, §5.3 counting, §6.4's absence at an incomplete point).

Code only: no model is called. For every candidate of S4's population - formed and lifecycle - S5 writes one row of
`checks.json`:

- **Retrieval** (§6.2): BM25 (lifecycle_intake.Library, search.K1/B) over the operative units of the current library
  S2 left, one per text in each layer (identical copies folded and counted), the query being the candidate's situation,
  action and exception and the text of every unit and ledger entry it names (the named hints: a lifecycle candidate's
  `target_unit`, `target_units`, `target_entry`, `entries`; a formed type G candidate's `instance_entry_ids` and the
  hints of the cluster it names). The top PER_LAYER units of each layer, every unit it names, and the top TOP_ENTRIES
  ledger entries by the same query (lifecycle_intake.entry_text), every entry it names among them. A named unit or entry
  the library or ledger does not hold is listed by id, never dropped. Reference units are not indexed: §6.1 splits a
  unit operative or reference, and a reference unit states no requirement a candidate could be covered by.
- **Quote checks** (plan WP-10 Goal): every quote a formed candidate cites - through its admission and through the
  claims of its events, and the origin quotes S4 verified and kept in `candidates.json` - is verified again against the
  immutable copy (`evidence.verify`); a failure is named by code and evidence id. A candidate citing no quote has
  `quote_ok` null, not true.
- **Sessions**: each session a candidate names is a census row and the session of one of its events; otherwise
  SESSION_UNKNOWN / SESSION_MISMATCH, by id (the fabricated session id of design §6.5's planted controls).
- **Recurrence** (§5.3): the affirmed lineages its sessions come from that the census counts - the census's own
  `counted` verdict on the component's root (unique root, `indexed`, owned, of a counted class), read and never
  re-derived - each once however many of its sessions the candidate has. Every other session is excluded by name:
  `unknown_independence` (no single root), `not_indexed` (the root is not in its host's index), `not_counted` (the
  census counts the root out for another reason), `not_in_census`.
- **Absence** (§6.2, §6.4): an absence conclusion needs a complete reference point; under the table's policy
  (derive.absence) the current point S2 recorded decides, and when it is not complete every candidate is withheld from
  an absence sweep, with the count and the reason travelling by name to the summary and the report (D-20261111-eaa2a8).

The output holds names, ids, hashes, scores and counts; no unit text, lesson or quote.
  stage_retrieve.py --self-test
"""
import collections
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import census, controls, derive, evidence, lifecycle_intake, lineage, records, stage_form, validate
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/: the self-test runs the driver from it
STAGE = "S5"
SCHEMA_PATH = HERE / "schemas" / "checks.schema.json"
# What S5 reads, each pinned at admission to the record of the stage that produced it (records.run_stage): S4's
# candidates, and what S4's subject was read from, so the events, claims and quotes S5 checks again are S3's as S4 read
# them, and the library and census are the ones S4 was admitted against.
INPUTS = ({"artifact": "candidates.json", "producer_stage": "S4"},
          {"artifact": "read-results.json", "producer_stage": "S3"},
          {"artifact": "read.json", "producer_stage": "S3"},
          {"artifact": "observations/resolutions.json", "producer_stage": "S3"},
          {"artifact": "census.json", "producer_stage": "S1"},
          {"artifact": "coverage.json", "producer_stage": "S1"},
          {"artifact": "views.json", "producer_stage": "S2"},
          {"artifact": "inventory/current.json", "producer_stage": "S2"})
# checks.json: one row per candidate; checked-candidates.json: the population S6 judges, natural and planted in one
# shape, ordered by id, with the evidence records no S3 store holds; the expected verdicts of the planted controls,
# which no packet carries and S6 never reads (controls.reader_problems)
POPULATION_FILE = "checked-candidates.json"
OUTPUTS = ("checks.json", POPULATION_FILE, controls.CONTROLS_FILE)
# design §6.2 line 411: "top 20 per layer plus every unit a candidate names"
PER_LAYER = 20
# design §6.2 line 412 names "the top ledger entries" and no number, nor does the plan: the per-layer count, a declared
# constant (lead, 2026-11-11), revisited at C3 against the entries the judges relate
TOP_ENTRIES = 20
TOP_ENTRIES_BASIS = "the per-layer count (design §6.2 names no number; lead, 2026-11-11); revisit at C3"
INDEXED_CLASS = "operative"
HINT_UNITS = ("target_unit", "target_units")
HINT_ENTRIES = ("target_entry", "entries")
EXCLUDED = ("unknown_independence", "not_indexed", "not_counted", "not_in_census")
SCORE_DIGITS = 6


# ---- retrieval -------------------------------------------------------------------------------------

class UnitIndex:
    """The current library as retrieval reads it: the operative units, one per text in each layer (the lowest unit id
    stands for its copies), under one BM25 index; `rep_of` maps every indexed unit to the unit that stands for it."""

    def __init__(self, units):
        self.units = {u["unit_id"]: u for u in units}
        groups = collections.defaultdict(list)
        not_indexed = collections.Counter()
        for u in sorted(units, key=lambda u: u["unit_id"]):
            if u.get("class") != INDEXED_CLASS:
                not_indexed[u.get("class") or "unclassed"] += 1
                continue
            groups[(u["layer"], u["sha"])].append(u)
        self.rep_of, self.copies, self.layer_of = {}, {}, {}
        for members in groups.values():
            rep = members[0]["unit_id"]
            self.copies[rep], self.layer_of[rep] = len(members) - 1, members[0]["layer"]
            for u in members:
                self.rep_of[u["unit_id"]] = rep
        self.library = lifecycle_intake.Library({rep: self.units[rep]["text"] for rep in self.copies})
        self.counts = {"indexed": len(self.copies), "folded_copies": sum(self.copies.values()),
                       "not_indexed": dict(sorted(not_indexed.items())),
                       "layers": dict(sorted(collections.Counter(self.layer_of.values()).items()))}


class EntryIndex:
    """The ledger's entries under one BM25 index, each by the text lifecycle_intake.entry_text reads."""

    def __init__(self, entries):
        self.entries = {e["id"]: e for e in entries}
        self.library = lifecycle_intake.Library({i: lifecycle_intake.entry_text(e) for i, e in self.entries.items()})


def keys_of(text):
    return set(lifecycle_intake.keys_tf(text)[0]) if text else set()


def as_list(value):
    if value is None or value == "":
        return []
    return [value] if isinstance(value, str) else [v for v in value if v]


def named(candidate, clusters):
    """`(unit ids, entry ids)` a candidate names: its lifecycle hint fields, and a formed type G candidate's cluster
    entries and the hint fields of the cluster candidate its tension names."""
    units, entries = [], []
    hinted = [candidate.get("lifecycle") or {}]
    tension = candidate.get("tension") or {}
    entries += as_list(tension.get("instance_entry_ids"))
    if tension.get("cluster"):
        hinted.append((clusters.get(tension["cluster"]) or {}).get("lifecycle") or {})
    for hints in hinted:
        for field in HINT_UNITS:
            units += as_list(hints.get(field))
        for field in HINT_ENTRIES:
            entries += as_list(hints.get(field))
    return sorted(set(units)), sorted(set(entries))


def query_keys(candidate, unit_index, entry_index, clusters):
    """The query's keys: situation, action and exception, and the text of every unit and entry the candidate names."""
    names_u, names_e = named(candidate, clusters)
    parts = [candidate.get(f) for f in ("situation", "action", "exception")]
    parts += [unit_index.units[u]["text"] for u in names_u if u in unit_index.units]
    parts += [lifecycle_intake.entry_text(entry_index.entries[e]) for e in names_e if e in entry_index.entries]
    return keys_of(" ".join(p for p in parts if p)), names_u, names_e


def score(value):
    return None if value is None else round(value, SCORE_DIGITS)


def retrieval_of(declaration):
    """The counts S5 keeps (plan WP-11, lead decision on J0's numbers): run.json's `retrieval.per_layer` and
    `retrieval.top_entries` when the run declares them, else PER_LAYER and TOP_ENTRIES, each with where it came from."""
    held = (declaration or {}).get("retrieval") or {}
    return {"per_layer": held.get("per_layer", PER_LAYER), "top_entries": held.get("top_entries", TOP_ENTRIES),
            "basis": {key: "declared" if key in held else "default" for key in ("per_layer", "top_entries")}}


def retrieve_units(keys, names_u, index, per_layer=PER_LAYER):
    """`(rows, named ids the library does not hold)`: the top `per_layer` units of each layer by score (ties by unit
    id), each with its rank, then every named unit outside them, unranked."""
    scores = index.library.scores(keys) if keys else {}
    by_layer = collections.defaultdict(list)
    for rep, value in scores.items():
        if value > 0:
            by_layer[index.layer_of[rep]].append((rep, value))
    wanted = set(names_u)
    rows = []
    for layer in sorted(by_layer):
        ranked = sorted(by_layer[layer], key=lambda pair: (-pair[1], pair[0]))[:per_layer]
        rows += [{"unit_id": rep, "layer": layer, "rank": rank, "score": score(value), "named": rep in wanted,
                  "copies": index.copies[rep]} for rank, (rep, value) in enumerate(ranked, 1)]
    have = {r["unit_id"] for r in rows}
    absent = []
    for ident in names_u:
        if ident in have:
            continue
        unit = index.units.get(ident)
        if unit is None:
            absent.append(ident)
            continue
        rep = index.rep_of.get(ident)
        rows.append({"unit_id": ident, "layer": unit["layer"], "rank": None,
                     "score": score(scores.get(rep, 0.0)) if rep else None, "named": True,
                     "copies": index.copies.get(rep, 0) if rep == ident else 0})
    return rows, absent


def retrieve_entries(keys, names_e, index, top_entries=TOP_ENTRIES):
    """`(rows, named ids the ledger does not hold)`: the top `top_entries` entries by score (ties by id), then every
    named entry outside them, unranked."""
    scores = index.library.scores(keys) if keys else {}
    ranked = sorted(((i, v) for i, v in scores.items() if v > 0), key=lambda pair: (-pair[1], pair[0]))[:top_entries]
    wanted = set(names_e)
    rows = [{"entry_id": i, "status": index.entries[i].get("status"), "rank": rank, "score": score(v), "named": i in wanted}
            for rank, (i, v) in enumerate(ranked, 1)]
    have = {r["entry_id"] for r in rows}
    absent = []
    for ident in names_e:
        if ident in have:
            continue
        if ident not in index.entries:
            absent.append(ident)
            continue
        rows.append({"entry_id": ident, "status": index.entries[ident].get("status"), "rank": None,
                     "score": score(scores.get(ident, 0.0)), "named": True})
    return rows, absent


# ---- recurrence ------------------------------------------------------------------------------------

def recurrence(sessions, rows):
    """Design §5.3's count over the census `rows` for a candidate's `sessions`: `{count, independent_sessions,
    lineages, excluded}`. A session counts through its component when the component's one root is a row the census
    counted; every other session is excluded under one named reason."""
    by_key = {census.key_of(r): r for r in rows}
    lineages, excluded = {}, {name: [] for name in EXCLUDED}
    for session in sorted(set(sessions)):
        row = by_key.get(session)
        if row is None:
            excluded["not_in_census"].append(session)
            continue
        lin = row.get("lineage") or {}
        if row.get("counted"):
            root = row
        elif lin.get("unique_root") and lin.get("root"):
            root = by_key.get(lin["root"])
        else:
            root = None
        if root is None:
            excluded["unknown_independence"].append(session)
            continue
        if not root.get("counted"):
            excluded["not_indexed" if root.get("provenance") != "indexed" else "not_counted"].append(session)
            continue
        component = (root.get("lineage") or {}).get("component") or census.key_of(root)
        lineages.setdefault(component, {"component": component, "root": census.key_of(root), "sessions": []})["sessions"].append(session)
    ordered = [lineages[c] for c in sorted(lineages)]
    return {"count": len(ordered), "independent_sessions": sorted(min(l["sessions"]) for l in ordered),
            "lineages": ordered, "excluded": excluded}


# ---- quotes and sessions ---------------------------------------------------------------------------

def stored_evidence(run_dir, names):
    """Every evidence record of the views' files, by id."""
    out = {}
    for name in names:
        for record in evidence.load(run_dir, name):
            out[record["evidence_id"]] = record
    return out


def cited(candidate, subject_of):
    """`(evidence ids a candidate cites, problems)`: its admission's quotes, and the quotes of every claim it cites - by
    its admission's `claim_ids`, its tension's `instance_claim_ids` and its events' claims - each claim once. Codex WP-10
    r1 #1: the claims cited directly were skipped, so a quote reached only through one was never verified again."""
    events = {r["id"]: r for r in subject_of["events"]}
    ids, problems, claim_ids = set(), [], []
    for requirement in (candidate.get("admission") or {}).values():
        ids.update(requirement.get("evidence_ids") or [])
        claim_ids += list(requirement.get("claim_ids") or [])
    claim_ids += list((candidate.get("tension") or {}).get("instance_claim_ids") or [])
    for event_id in candidate.get("event_ids") or []:
        row = events.get(event_id)
        if row is None:
            continue
        claim_ids += row["claim_ids"] + row["outcome_claim_ids"]
    for claim_id in dict.fromkeys(claim_ids):
        claim = subject_of["claims"].get(claim_id)
        if claim is None:
            problems.append(f"CLAIM_UNKNOWN {claim_id}")
            continue
        ids.update(q["evidence_id"] for q in claim["quotes"])
    return sorted(ids), problems


def quote_problems(run_dir, ids, stored, extra):
    """Each cited quote verified again against the immutable copy: the problems, each `<code> <evidence id>`. A record is
    an S3 store's, or one of `extra`: S4's origin quotes and the planted controls' own."""
    problems = []
    for ident in ids:
        record = stored.get(ident) or extra.get(ident)
        if record is None:
            problems.append(f"EVIDENCE_ABSENT {ident}")
            continue
        problems += [f"{p.split(' ', 1)[0]} {ident}" for p in evidence.verify(run_dir, record)]
    return problems


def session_problems(candidate, subject_of, rows):
    """A candidate's sessions against the census and its events: SESSION_UNKNOWN (no census row), SESSION_MISMATCH
    (a session none of its events is of, or an event's session it does not name), EVENT_UNKNOWN (an event the subject
    does not hold)."""
    known = {census.key_of(r) for r in rows}
    events = {r["id"]: r for r in subject_of["events"]}
    problems = [f"EVENT_UNKNOWN {e}" for e in candidate.get("event_ids") or [] if e not in events]
    named_sessions = set(candidate.get("sessions") or [])
    problems += [f"SESSION_UNKNOWN {s}" for s in sorted(named_sessions - known)]
    of_events = {events[e]["session"] for e in candidate.get("event_ids") or [] if e in events}
    problems += [f"SESSION_MISMATCH {s}" for s in sorted(named_sessions ^ of_events)]
    return problems


# ---- absence ---------------------------------------------------------------------------------------

def current_point(current):
    """The current reference point as derive.absence reads one: its completeness flag and its layers' statuses."""
    return {"complete": (current.get("reference") or {}).get("complete"),
            "layers": {row["layer"]: row["status"] for row in current.get("layers") or []}}


def absence_of(current):
    """`(checks.json's absence, the reason a candidate is withheld or None)`."""
    complete, read = derive.absence(current_point(current))
    layers = read.get("unknown_layers") or []
    doc = {"reference": "current", "policy": read["policy"], "complete": complete, "unknown_layers": layers}
    if complete:
        return doc, None
    what = (f"completeness of the {', '.join(layers)} layer{'s' if len(layers) > 1 else ''} unknown" if layers
            else "the current reference point records no completeness")
    return doc, what


# ---- the stage -------------------------------------------------------------------------------------

def schema_problems(doc):
    return validate.validate_instance(validate.compile_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))), doc)


def natural_population(run_dir):
    """S4's population as `candidates.json` lists it, formed and lifecycle."""
    return records.read_json(pathlib.Path(run_dir) / "candidates.json")


def build(run_dir, declaration, nonce=None):
    """`(checks.json, checked-candidates.json, controls.json)` for a run: S4's population with the planted controls
    of design §6.5 (controls.plant) among it under ordinary ids, every candidate checked alike."""
    run_dir = pathlib.Path(run_dir)
    cands = natural_population(run_dir)
    current = records.read_json(run_dir / "inventory" / "current.json")
    rows = census.rows(census.load(run_dir))
    subject_of = stage_form.subject(run_dir)
    ledger, read = lifecycle_intake.ledger_of(declaration)
    names = [t["name"] for t in records.read_json(run_dir / "views.json")["transcripts"]]
    stored, origins = stored_evidence(run_dir, names), cands.get("origin_evidence") or {}
    unit_index, entry_index = UnitIndex(current["units"]), EntryIndex(ledger["entries"])
    planted, planted_evidence, planted_doc = controls.plant(
        cands["candidates"], unit_index, lambda k: cited(k, subject_of)[0], lambda i: stored.get(i) or origins.get(i),
        {census.key_of(r) for r in rows}, nonce)
    extra = {**origins, **planted_evidence}
    everyone = sorted(cands["candidates"] + planted, key=lambda k: k["candidate_id"])
    clusters = {c["candidate_id"]: c for c in everyone if c["source"] == "g_cluster"}
    absence, withheld_reason = absence_of(current)
    limits = retrieval_of(declaration)
    out = []
    for k in everyone:
        keys, names_u, names_e = query_keys(k, unit_index, entry_index, clusters)
        units, absent_u = retrieve_units(keys, names_u, unit_index, limits["per_layer"])
        entries, absent_e = retrieve_entries(keys, names_e, entry_index, limits["top_entries"])
        ids, claim_problems = cited(k, subject_of)
        quotes = claim_problems + quote_problems(run_dir, ids, stored, extra)
        out.append({"candidate_id": k["candidate_id"], "source": k["source"], "query_keys": len(keys),
                    "retrieved_units": units, "named_units_absent": absent_u, "ledger_entries": entries,
                    "named_entries_absent": absent_e, "recurrence": recurrence(k.get("sessions") or [], rows),
                    "quote_ok": (not quotes) if (ids or claim_problems) else None, "quotes_checked": len(ids),
                    "quote_problems": quotes, "session_problems": session_problems(k, subject_of, rows),
                    "absence_withheld": withheld_reason is not None})
    planted_ids = {k["candidate_id"] for k in planted}
    doc = {"constants": {"per_layer": limits["per_layer"], "top_entries": limits["top_entries"],
                         "top_entries_basis": TOP_ENTRIES_BASIS, "indexed_class": INDEXED_CLASS, "declared": limits["basis"]},
           "library": unit_index.counts, "ledger_index": {"entries": len(entry_index.entries), "read": read},
           "absence": absence, "candidates": out,
           "summary": summary_of([r for r in out if r["candidate_id"] not in planted_ids], withheld_reason)}
    return doc, {"candidates": everyone, "evidence": dict(sorted(extra.items()))}, planted_doc


def summary_of(rows, withheld_reason):
    excluded = {name: sum(len(r["recurrence"]["excluded"][name]) for r in rows) for name in EXCLUDED}
    withheld = sum(1 for r in rows if r["absence_withheld"])
    return {"candidates": len(rows), "formed": sum(1 for r in rows if r["source"] == "formed"),
            "lifecycle": sum(1 for r in rows if r["source"] != "formed"),
            "retrieved_units": sum(len(r["retrieved_units"]) for r in rows),
            "named_units": sum(1 for r in rows for u in r["retrieved_units"] if u["named"]),
            "ledger_entries": sum(len(r["ledger_entries"]) for r in rows),
            "quotes_checked": sum(r["quotes_checked"] for r in rows),
            "quote_failed": sum(1 for r in rows if r["quote_ok"] is False),
            "session_failed": sum(1 for r in rows if r["session_problems"]),
            "recurrence": {"lineages": sum(r["recurrence"]["count"] for r in rows),
                           "sessions": sum(len(l["sessions"]) for r in rows for l in r["recurrence"]["lineages"]),
                           "excluded": excluded},
            "absence_withheld": {"candidates": withheld, "reason": withheld_reason if withheld else None}}


def run(run_dir, nonce=None):
    """S5 over S4's population and the planted controls: admitted against its inputs, writes `checks.json`
    (schema-checked), the population S6 judges and the controls' expected verdicts, and records them. `nonce` fixes
    the controls' draw; only a self-test passes it."""
    run_dir = pathlib.Path(run_dir)
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        doc, checked, planted_doc = build(run_dir, stage.declaration, nonce)
        problems = schema_problems(doc)
        if problems:
            raise Refused("CHECKS_INVALID " + "; ".join(problems[:5]))
        # a planted control S5 checks and does not fail, or a kind not planted, stops the run here (design §4, §6.5)
        stops = controls.check_s5(planted_doc, {r["candidate_id"]: r for r in doc["candidates"]})
        if stops:
            raise Refused("\n".join(stops))
        records.write_json(run_dir, run_dir / "checks.json", doc)
        records.write_json(run_dir, run_dir / POPULATION_FILE, checked)
        records.write_json(run_dir, run_dir / controls.CONTROLS_FILE, planted_doc)
        for name in OUTPUTS:
            stage.output(name)
        declaration_seq = stage.record["declaration_seq"]
    return {**doc["summary"], "declaration_seq": declaration_seq, "library": doc["library"], "constants": doc["constants"],
            "ledger_index": doc["ledger_index"], "absence": doc["absence"],
            "controls": {"planted": len(planted_doc["planted"]),
                         "s5_checked": sum(1 for e in planted_doc["planted"] if "S5" in e),
                         "s5_held": sum(1 for e in planted_doc["planted"] if (e.get("S5") or {}).get("ok")),
                         "gate_declared": len(planted_doc["gate"])}}


def withheld_line(summary):
    """The withheld count and its reason, by name (D-20261111-eaa2a8), or None when nothing is withheld."""
    w = summary["absence_withheld"]
    return f"{w['candidates']} candidates not advanced to an absence sweep: {w['reason']}" if w["candidates"] else None


def report_lines(summary):
    """What the driver prints of a run of S5: counts and codes, never a unit's text, a lesson or a quote."""
    lib, rec = summary["library"], summary["recurrence"]
    lines = [f"S5 retrieve: declaration_seq {summary['declaration_seq']}; {summary['candidates']} candidates "
             f"({summary['formed']} formed, {summary['lifecycle']} lifecycle)",
             f"library: {lib['indexed']} indexed texts over {len(lib['layers'])} layers, {lib['folded_copies']} identical "
             f"copies folded, not indexed {lib['not_indexed']}; ledger: {summary['ledger_index']['entries']} entries "
             f"({summary['ledger_index']['read']})",
             f"retrieval: {summary['retrieved_units']} unit rows ({summary['named_units']} named), "
             f"{summary['ledger_entries']} ledger entry rows; at most {summary['constants']['per_layer']} per layer "
             f"({summary['constants']['declared']['per_layer']}) and {summary['constants']['top_entries']} entries "
             f"({summary['constants']['declared']['top_entries']})",
             f"quotes: {summary['quotes_checked']} verified again, {summary['quote_failed']} candidates failed; "
             f"sessions: {summary['session_failed']} candidates with a session problem",
             f"recurrence: {rec['lineages']} counted lineages over {rec['sessions']} sessions; excluded "
             + ", ".join(f"{k} {v}" for k, v in rec["excluded"].items())]
    line = withheld_line(summary)
    lines.append(f"absence: {line}" if line else "absence: the current reference point is complete; none withheld")
    c = summary["controls"]
    lines.append(f"controls (apart from the counts above): {c['planted']} planted; S5 checked {c['s5_checked']}, each "
                 f"given its verdict: {c['s5_held']}; {c['gate_declared']} gate controls declared for the dispatching stage")
    return lines


# ---- self-test -------------------------------------------------------------------------------------

def fx_current(units, complete=False, statuses=None):
    """An `inventory/current.json` as S2 records one: units, a completeness flag, and its layers' statuses."""
    statuses = {"catalog": "complete", "native_project": "complete", "native_undivided": "complete",
                "native_settings": "unknown"} if statuses is None else statuses
    return {"units": list(units), "reference": {"kind": "current", "complete": complete, "incomplete_reasons": []},
            "layers": [{"layer": k, "status": v} for k, v in sorted(statuses.items())]}


def fx_gold(root, current=None):
    """A golden run through S4 (stage_form's golden S3 run and its formation plan), its current library re-recorded by
    S2's inventory part before S4 reads it. Returns the run directory."""
    run_dir, _summary = stage_form.fx_s3(root)
    doc = fx_current(lifecycle_intake.FX_LIBRARY) if current is None else current
    with records.run_stage(run_dir, "S2", [{"artifact": "census.json", "producer_stage": "S1"}], part="inventory") as stage:
        records.write_json(run_dir, run_dir / "inventory" / "current.json", doc)
        stage.output("inventory/current.json")
    plan = stage_form.fx_form_plan(run_dir, root / "form-plan.json")
    stage_form.run(run_dir, stage_form.supervisor(run_dir, root / "form-cells", plan))
    return run_dir


def fx_census_rows(nodes, indexed=()):
    """Census rows over lineage nodes as S1 links them (lineage.components): each eligible, `indexed` when its id is in
    `indexed`, and counted as the census counts a row - the one root of its component, indexed."""
    linked = lineage.components(nodes)
    rows = []
    for node in nodes:
        host, ident = lineage.split_identity(node["id"])
        lin = {**linked[node["id"]], "measurement_pending": False}
        provenance = "indexed" if node["id"] in indexed else "not_indexed"
        rows.append({"host": host, "id": ident, "status": "eligible", "provenance": provenance, "lineage": lin,
                     "counted": bool(lin["unique_root"] and lin["root"] == node["id"] and provenance == "indexed")})
    return rows


def fx_node(ident, ids, root=True, links=()):
    return {"id": ident, "host": "claude", "root": root, "ids": list(ids), "turns": [], "links": list(links)}


def self_test():
    failures, ran = [], []

    def control(name, condition, detail=""):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def guarded(action, default):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - reported by the control that reads the default
            return default if not callable(default) else default(exc)

    def refusal(action):
        try:
            action()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a control whose subject raises anything else fails by its own name
            return f"RAISED {exc!r}"
        return ""

    fx_unit = lifecycle_intake.fx_unit
    # ---- retrieval over a library of its own ---------------------------------------------------------------------
    many = [fx_unit(f"u-z{n:02d}", f"Feed the zebra {'hay ' * n}at noon.") for n in range(1, 23)]
    lib = many + [fx_unit("u-zp", "Feed the zebra at noon in the project.", layer="native_project"),
                  fx_unit("u-zref", "Feed the zebra at noon, as the keeper said.", cls="reference"),
                  fx_unit("u-twin1", "Okapi visits are booked a week ahead.", layer="native_project"),
                  fx_unit("u-twin2", "Okapi visits are booked a week ahead.", layer="native_project"),
                  fx_unit("u-ex", "Wash the bucket after the okapi drinks.")]
    index = UnitIndex(lib)
    no_entries = EntryIndex([])

    def retrieved(candidate, units_index=index, entries_index=no_entries, clusters=None):
        keys, names_u, _names_e = query_keys(candidate, units_index, entries_index, clusters or {})
        return retrieve_units(keys, names_u, units_index)

    zebra = {"situation": "the zebra is fed", "action": "feed the zebra", "exception": "", "source": "formed"}
    rows, _absent = retrieved(zebra)
    catalog = [r for r in rows if r["layer"] == "catalog"]
    control("§6.2: at most the top 20 units of a layer are retrieved, ranked by score, ties by unit id",
            len(catalog) == PER_LAYER and [r["rank"] for r in catalog] == list(range(1, PER_LAYER + 1))
            and all((-a["score"], a["unit_id"]) <= (-b["score"], b["unit_id"]) for a, b in zip(catalog, catalog[1:])),
            f"{len(catalog)} {[r['rank'] for r in catalog][:3]}")
    control("§6.2: each layer has its own top 20: the one matching project unit is retrieved beside a full catalog layer",
            [r["unit_id"] for r in rows if r["layer"] == "native_project"] == ["u-zp"], f"{rows}")
    control("§6.1: a reference unit is not indexed, and the index says how many were left out",
            "u-zref" not in {r["unit_id"] for r in rows} and index.counts["not_indexed"] == {"reference": 1},
            f"{index.counts}")
    twins, _a = retrieved({"situation": "okapi visits booked", "action": "", "exception": "", "source": "formed"})
    control("identical text in one layer is one retrieved unit, the lowest id standing for its counted copies",
            [(r["unit_id"], r["copies"]) for r in twins if r["layer"] == "native_project"] == [("u-twin1", 1)]
            and index.counts["folded_copies"] == 1, f"{twins}")
    exc_rows, _a = retrieved({"situation": "kiwi", "action": "", "exception": "okapi drinks", "source": "formed"})
    plain_rows, _a = retrieved({"situation": "kiwi", "action": "", "exception": "", "source": "formed"})
    control("§6.2: the query holds the exception: a unit only the exception's words match is retrieved",
            "u-ex" in {r["unit_id"] for r in exc_rows}, f"{exc_rows}")
    control("control: without the exception that unit is not retrieved", "u-ex" not in {r["unit_id"] for r in plain_rows},
            f"{plain_rows}")
    beyond = next((u["unit_id"] for u in many if u["unit_id"] not in {r["unit_id"] for r in catalog}), None)
    hinted = {"source": "redundancy_hint", "lifecycle": {"target_units": [beyond, "u-gone"]}}
    h_rows, h_absent = retrieved(hinted)
    control("§6.2: every unit a candidate names is retrieved, unranked when outside its layer's top 20",
            any(r["unit_id"] == beyond and r["rank"] is None and r["named"] for r in h_rows), f"{h_rows}")
    control("a named unit the library does not hold is listed by id, never dropped", h_absent == ["u-gone"], f"{h_absent}")
    control("the named hints are part of the query: a lifecycle candidate with no text of its own retrieves by its "
            "named units' text", sum(1 for r in h_rows if r["rank"] is not None) > 0, f"{h_rows}")
    control("a candidate with no words and nothing named retrieves nothing, and says its query had no keys",
            retrieved({"source": "legacy", "lifecycle": {}}) == ([], []) and query_keys({}, index, no_entries, {})[0] == set(),
            "retrieved")
    entries = [{"id": f"E-{n}", "status": "placed", "lesson": f"Feed the zebra {'hay ' * n}at noon", "principle": ""}
               for n in range(1, 23)] + [{"id": "E-99", "status": "retired", "lesson": "Paint the fence", "principle": "blue"}]
    e_index = EntryIndex(entries)
    keys, _u, names_e = query_keys({**zebra, "lifecycle": {"target_entry": "E-99", "entries": ["E-0"]}}, index, e_index, {})
    e_rows, e_absent = retrieve_entries(keys, names_e, e_index)
    control("§6.2: the top ledger entries by the same query, at most TOP_ENTRIES, ranked",
            len([r for r in e_rows if r["rank"] is not None]) == TOP_ENTRIES, f"{len(e_rows)}")
    control("... every entry the candidate names among them, unranked when outside, its status shown; an entry the ledger "
            "does not hold is listed by id", any(r["entry_id"] == "E-99" and r["named"] and r["status"] == "retired"
                                                 for r in e_rows) and e_absent == ["E-0"], f"{e_rows[-2:]} {e_absent}")
    gate_index = EntryIndex(entries + [{"id": "E-77", "status": "placed", "lesson": "Keep it shut", "principle":
                                        "a gate left open lets the animals out"}])
    gate_rows, _ = retrieve_entries(keys_of("the gate"), [], gate_index)
    control("an entry is ranked by its lesson and its principle (lifecycle_intake.entry_text): one only its principle "
            "matches is retrieved", [r["entry_id"] for r in gate_rows if r["score"] and r["entry_id"] == "E-77"] == ["E-77"],
            f"{gate_rows[:3]}")
    outside, _absent = retrieve_entries(keys_of("feed the zebra"), ["E-99"], e_index)
    control("a named entry the query does not match is listed unranked, never dropped",
            [(r["entry_id"], r["rank"], r["named"]) for r in outside if r["entry_id"] == "E-99"] == [("E-99", None, True)]
            and len([r for r in outside if r["rank"] is not None]) == TOP_ENTRIES, f"{outside[-2:]}")
    g = {"source": "formed", "situation": "", "action": "", "exception": "",
         "tension": {"instance_entry_ids": ["E-3"], "cluster": "g_cluster:u-zp"}}
    names_g = named(g, {"g_cluster:u-zp": {"lifecycle": {"target_unit": "u-zp", "entries": ["E-4", "E-5"]}}})
    control("a formed type G candidate names its cluster entries and the hints of the cluster its tension names",
            names_g == (["u-zp"], ["E-3", "E-4", "E-5"]), f"{names_g}")

    # ---- recurrence over the census's lineages (plan WP-10 done-when 3) -------------------------------------------
    root_n, replay = fx_node("claude:r-1", ["m1", "m2", "m3"]), fx_node("claude:r-1-replay", ["m1", "m2", "m3", "m4"], root=False)
    pair = fx_census_rows([root_n, replay], indexed={"claude:r-1", "claude:r-1-replay"})
    got = recurrence(["claude:r-1", "claude:r-1-replay"], pair)
    control("done-when 3 (O4 F-O4-04): a session pair whose replay hides its ancestry - same root, copied record ids, no "
            "pointer - counts as one lineage", got["count"] == 1 and got["independent_sessions"] == ["claude:r-1"]
            and got["lineages"][0]["sessions"] == ["claude:r-1", "claude:r-1-replay"], f"{got}")
    two = fx_census_rows([fx_node("claude:a-1", ["a1"]), fx_node("claude:b-1", ["b1"])], indexed={"claude:a-1", "claude:b-1"})
    got2 = recurrence(["claude:a-1", "claude:b-1"], two)
    control("control: two genuinely distinct roots count as two", got2["count"] == 2, f"{got2}")
    copy_pair = fx_census_rows([fx_node("claude:c-1", ["c1", "c2"]), fx_node("claude:c-1-copy", ["c1", "c2"])],
                               indexed={"claude:c-1", "claude:c-1-copy"})
    got3 = recurrence(["claude:c-1", "claude:c-1-copy"], copy_pair)
    control("§5.3: a copy of a root beside its original has no single root, counts toward nothing, and both sessions are "
            "excluded as unknown independence", got3["count"] == 0
            and got3["excluded"]["unknown_independence"] == ["claude:c-1", "claude:c-1-copy"], f"{got3}")
    unindexed = fx_census_rows([fx_node("claude:d-1", ["d1"])])
    got4 = recurrence(["claude:d-1", "claude:fabricated"], unindexed)
    control("§5.3 (O4): an affirmed lineage whose root its host's index does not hold counts toward nothing; a session the "
            "census does not hold is excluded by id", got4["count"] == 0 and got4["excluded"]["not_indexed"] == ["claude:d-1"]
            and got4["excluded"]["not_in_census"] == ["claude:fabricated"], f"{got4}")
    owned_out = [{**r, "counted": False} for r in fx_census_rows([fx_node("claude:e-1", ["e1"])], indexed={"claude:e-1"})]
    got5 = recurrence(["claude:e-1"], owned_out)
    control("a root the census counts out for another reason (not owned, another class) is excluded as not_counted: the "
            "census's verdict is read, never re-derived", got5["count"] == 0 and got5["excluded"]["not_counted"] == ["claude:e-1"],
            f"{got5}")

    # ---- absence ---------------------------------------------------------------------------------------------------
    doc_in, why_in = absence_of(fx_current([]))
    doc_ok, why_ok = absence_of(fx_current([], complete=True, statuses={"catalog": "complete"}))
    control("§6.2/§6.4: at an incomplete current point every candidate is withheld from an absence sweep, the reason naming "
            "the layers whose completeness is unknown", why_in == "completeness of the native_settings layer unknown"
            and doc_in["complete"] is False and doc_in["unknown_layers"] == ["native_settings"], f"{doc_in} {why_in}")
    control("control: at a complete point nothing is withheld", why_ok is None and doc_ok["complete"] is True, f"{doc_ok}")
    control("a point that records no completeness is incomplete, and says so",
            absence_of({"units": []})[1] == "the current reference point records no completeness", f"{absence_of({'units': []})}")

    # ---- the stage over a golden run through S4 --------------------------------------------------------------------
    root = pathlib.Path(tempfile.mkdtemp(prefix="s5-"))
    try:
        base = guarded(lambda: fx_gold(root / "base"), lambda exc: exc)
        if isinstance(base, Exception):
            failures.append(f"the golden run through S4 could not be made: {base!r}")
            base = None

        def copy_of(label):
            where = root / f"c-{label}"
            shutil.copytree(base.parent, where)
            return where / base.name

        def record_of(where):
            return guarded(lambda: records.read_json(records.record_path(where, STAGE)), {})

        if base is not None:
            gold = copy_of("gold")
            made = guarded(lambda: run(gold), lambda exc: {"problem": repr(exc)})
            doc = guarded(lambda: records.read_json(gold / "checks.json"), {"candidates": []})
            cands = guarded(lambda: records.read_json(gold / "candidates.json")["candidates"], [])
            rows_by = {r["candidate_id"]: r for r in doc["candidates"]}
            control("golden: S5 runs over S4's population, completes, and records its three outputs",
                    record_of(gold).get("status") == "complete"
                    and [o["artifact"] for o in record_of(gold).get("outputs", [])] == list(OUTPUTS), f"{made}")
            checked = guarded(lambda: records.read_json(gold / POPULATION_FILE), {"candidates": [], "evidence": {}})
            planted_doc = guarded(lambda: records.read_json(gold / controls.CONTROLS_FILE), {"planted": [], "gate": []})
            planted_ids = {e["candidate_id"] for e in planted_doc["planted"]}
            natural_ids = [k["candidate_id"] for k in cands]
            control("golden (done-when 4): the planted controls join the population every run - the six of §6.5 among "
                    "S4's candidates, one population ordered by id, one row of checks.json per member",
                    len(planted_ids) == 6 and set(natural_ids) | planted_ids == {k["candidate_id"] for k in checked["candidates"]}
                    and [k["candidate_id"] for k in checked["candidates"]] == sorted(set(natural_ids) | planted_ids)
                    and [r["candidate_id"] for r in doc["candidates"]] == [k["candidate_id"] for k in checked["candidates"]]
                    and len(cands) > 2, f"{len(planted_ids)} {len(doc['candidates'])} {len(cands)}")
            control("golden: S5 gives each of its controls its verdict - the paraphrased unit retrieved, the altered quote "
                    "QUOTE_MISMATCH, the fabricated session SESSION_UNKNOWN - and the run goes on",
                    [e.get("S5", {}).get("ok") for e in planted_doc["planted"] if "S5" in e["checked_at"]] == [True] * 4
                    and made.get("controls", {}).get("s5_held") == 4, f"{planted_doc['planted']}")
            gold_ranks = [u["rank"] for r in doc["candidates"] for u in r["retrieved_units"] if u["rank"] is not None]
            control("WP-11: with no retrieval declared, S5 keeps its own counts and says they are its defaults",
                    doc.get("constants", {}).get("declared") == {"per_layer": "default", "top_entries": "default"}
                    and doc["constants"].get("per_layer") == PER_LAYER and doc["constants"].get("top_entries") == TOP_ENTRIES
                    and f"at most {PER_LAYER} per layer (default)" in "\n".join(guarded(lambda: report_lines(made), [])),
                    f"{doc.get('constants')}")
            from runlib import declare
            narrow_run = copy_of("narrow")
            # two per layer, under a fixed draw: at one per layer a paraphrase control can lose its unit to another of its
            # layer, and S5 then stops the run by name (CONTROL_FAILED), which is S5's verdict on too narrow a retrieval
            narrowed = guarded(lambda: (declare.amend(narrow_run, [("retrieval", {"per_layer": 2, "top_entries": 1})],
                                                      "narrow S5's retrieval (WP-11)", scope=["S5"]),
                                        run(narrow_run, "aa" * 8))[1],
                               lambda exc: {"problem": repr(exc)})
            narrow = guarded(lambda: records.read_json(narrow_run / "checks.json"), {"problem": narrowed})
            ranked = {u["rank"] for r in narrow.get("candidates", []) for u in r["retrieved_units"] if u["rank"] is not None}
            entry_ranks = {e["rank"] for r in narrow.get("candidates", []) for e in r["ledger_entries"] if e["rank"] is not None}
            control("WP-11: a declared retrieval keeps that many units of each layer and ledger entries, says the counts are "
                    "declared, and its checks.json is schema-valid",
                    narrow.get("constants", {}).get("declared") == {"per_layer": "declared", "top_entries": "declared"}
                    and gold_ranks and max(gold_ranks) > 2 and ranked == {1, 2} and entry_ranks == {1}
                    and not guarded(lambda: schema_problems(narrow), ["unreadable"]),
                    f"{narrow.get('constants', narrow)} {sorted(ranked)} {sorted(entry_ranks)}")
            control("golden: the summary counts the natural candidates; the controls are reported apart",
                    doc.get("summary", {}).get("candidates") == len(cands) and doc["summary"].get("quote_failed") == 0
                    and doc["summary"].get("session_failed") == 0, f"{doc.get('summary')}")
            nat_formed = next((k for k in cands if k["source"] == "formed" and k["event_ids"]), {})
            twin = next((k for k in checked["candidates"] if k["candidate_id"] in planted_ids
                         and k.get("event_ids") == nat_formed.get("event_ids")), {})
            control("F27: a control's row in checks.json has a natural row's paths and types, and its record in the "
                    "population a natural record's", twin and not controls.marker_problems(rows_by.get(twin.get("candidate_id"), {}),
                                                                                         rows_by.get(nat_formed.get("candidate_id"), {}))
                    and not controls.marker_problems(twin, nat_formed), f"{twin.get('candidate_id')}")
            control("golden: checks.json holds to its schema", not schema_problems(doc), f"{schema_problems(doc)[:3]}")
            formed_c = next((k for k in cands if k["source"] == "formed" and k["event_ids"]), {})
            row_c = rows_by.get(formed_c.get("candidate_id"), {})
            control("golden: the formed candidate's quotes - its admission's origin quote and its events' claims' quotes - "
                    "are verified again, and verify", row_c.get("quote_ok") is True and row_c.get("quotes_checked", 0) >= 2
                    and not row_c.get("quote_problems"), f"{row_c.get('quote_ok')} {row_c.get('quote_problems')}")
            control("golden: its session is a counted census row: recurrence 1, nothing excluded",
                    row_c.get("recurrence", {}).get("count") == 1 and not row_c.get("session_problems")
                    and not any(row_c.get("recurrence", {}).get("excluded", {}).values()), f"{row_c.get('recurrence')}")
            g_row = next((r for r in doc["candidates"] if r["source"] == "g_cluster"), {})
            g_cand = next((k for k in cands if k["source"] == "g_cluster"), {})
            control("golden: the G cluster's named unit and its entries are retrieved, each named",
                    any(u["unit_id"] == g_cand.get("lifecycle", {}).get("target_unit") and u["named"]
                        for u in g_row.get("retrieved_units", []))
                    and set(g_cand.get("lifecycle", {}).get("entries", []))
                    <= {e["entry_id"] for e in g_row.get("ledger_entries", []) if e["named"]}, f"{g_row}")
            lc = [r for r in doc["candidates"] if r["source"] != "formed"]
            control("golden: a lifecycle candidate cites no quote (quote_ok null) and has no session to count",
                    lc and all(r["quote_ok"] is None and r["recurrence"]["count"] == 0 for r in lc), f"{lc[:1]}")
            control("golden: at the run's incomplete current point every natural candidate is withheld, and the summary "
                    "carries the count and the reason by name",
                    doc.get("summary", {}).get("absence_withheld") == {"candidates": len(cands), "reason":
                                                                      "completeness of the native_settings layer unknown"}
                    and all(r["absence_withheld"] for r in doc["candidates"]), f"{doc.get('summary', {}).get('absence_withheld')}")
            said = guarded(lambda: report_lines(made), ["RAISED", "RAISED"])
            control("golden: the report carries the withheld line: '<n> candidates not advanced to an absence sweep: <reason>'",
                    said[-2] == f"absence: {len(cands)} candidates not advanced to an absence sweep: completeness of the "
                                "native_settings layer unknown", f"{said[-2:]}")
            control("golden: the report carries the controls apart from the natural counts",
                    said[-1].startswith("controls (apart from the counts above): 6 planted; S5 checked 4"), f"{said[-1:]}")
            # a planted S5 control that S5 lets through stops the run before S6 reads anything
            slipped = copy_of("slipped")
            held_alter = controls.alter
            controls.alter = lambda text: text
            try:
                said_slipped = refusal(lambda: run(slipped))
            finally:
                controls.alter = held_alter
            control("CONTROL_FAILED: an altered quote that is not altered passes S5's quote check, and S5 stops the run by "
                    "name, writing nothing", "CONTROL_FAILED" in said_slipped and "altered_quote" in said_slipped
                    and not (slipped / "checks.json").exists() and record_of(slipped).get("status") == "failed",
                    said_slipped[:300])
            # a text short enough to be a JSON word ("true") says nothing about what the file holds
            texts = [t for t in [u["text"] for u in lifecycle_intake.FX_LIBRARY] + [k.get("lesson") for k in cands]
                     if t and len(t) > 12]
            raw = guarded(lambda: (gold / "checks.json").read_text(encoding="utf-8"), "")
            control("checks.json holds names, ids, scores and counts: no unit text and no lesson",
                    raw and not [t for t in texts if t and t in raw], f"{[t for t in texts if t and t in raw][:2]}")

            # quote checks: an altered quote in the store fails by code and id
            altered = copy_of("altered")
            cited_ids = set(guarded(lambda: cited(formed_c, stage_form.subject(altered))[0], []))
            target_id = None
            for path in sorted((altered / "evidence").glob("*.jsonl")):
                lines = path.read_text(encoding="utf-8").splitlines()
                for n, line in enumerate(lines):
                    rec = json.loads(line) if line.strip() else {}
                    if target_id is None and rec.get("evidence_id") in cited_ids:
                        rec["redacted_text"] = rec["redacted_text"] + " (changed)"
                        lines[n], target_id = json.dumps(rec, sort_keys=True, ensure_ascii=False), rec["evidence_id"]
                if target_id:
                    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    break
            guarded(lambda: run(altered), None)
            a_doc = guarded(lambda: records.read_json(altered / "checks.json"), {"candidates": [], "summary": {}})
            a_row = next((r for r in a_doc["candidates"] if r["candidate_id"] == formed_c.get("candidate_id")), {})
            control("an altered quote no longer walks back to the immutable copy: quote_ok false, QUOTE_MISMATCH by evidence id, "
                    "counted in the summary", target_id and a_row.get("quote_ok") is False
                    and a_row.get("quote_problems") == [f"QUOTE_MISMATCH {target_id}"]
                    and a_doc["summary"].get("quote_failed") == 1, f"{target_id} {a_row.get('quote_problems')}")
            # Codex WP-10 r1 #1: the same altered quote, reached only through a claim the candidate cites directly - by
            # its admission's claim_ids, and by its tension's instance_claim_ids - is QUOTE_MISMATCH too
            sub_a = guarded(lambda: stage_form.subject(altered), {"events": [], "claims": {}})
            direct = next((c for c, claim in sub_a["claims"].items()
                           if any(q["evidence_id"] == target_id for q in claim["quotes"])), None)
            names_a = [t["name"] for t in guarded(lambda: records.read_json(altered / "views.json")["transcripts"], [])]
            stored_a = guarded(lambda: stored_evidence(altered, names_a), {})
            by_claims = {"candidate_id": "k-direct", "event_ids": [],
                         "admission": {"observed_event": {"claim_ids": [direct], "evidence_ids": []}}}
            by_tension = {"candidate_id": "k-tension", "event_ids": [], "admission": {},
                          "tension": {"instance_claim_ids": [direct]}}
            got_direct = [guarded(lambda k=k: quote_problems(altered, cited(k, sub_a)[0], stored_a, {}), ["RAISED"])
                          for k in (by_claims, by_tension)]
            control("Codex WP-10 r1 #1: an altered quote reached only through a claim cited directly - by the admission's "
                    "claim_ids or the tension's instance_claim_ids - is QUOTE_MISMATCH by evidence id",
                    direct and target_id and got_direct == [[f"QUOTE_MISMATCH {target_id}"]] * 2,
                    f"{direct} {target_id} {got_direct}")
            control("Codex WP-10 r1 #1: a claim cited directly that no store holds is CLAIM_UNKNOWN",
                    guarded(lambda: cited({**by_claims, "admission": {"observed_event": {"claim_ids": ["c-none"]}}},
                                          sub_a)[1], []) == ["CLAIM_UNKNOWN c-none"])
            # a tampered immutable copy, at the function: the record's own copy hashes otherwise
            tampered = copy_of("tampered")
            sub_t = guarded(lambda: stage_form.subject(tampered), None)
            ids_t = guarded(lambda: cited(formed_c, sub_t)[0], [])
            names_t = [t["name"] for t in guarded(lambda: records.read_json(tampered / "views.json")["transcripts"], [])]
            stored_t = guarded(lambda: stored_evidence(tampered, names_t), {})
            plain_id = next((i for i in ids_t if not i.startswith("origin:") and i in stored_t), None)
            if plain_id:
                copy_path = tampered / evidence.copy_rel(stored_t[plain_id]["version_sha"])
                copy_path.chmod(0o600)   # the copy is written read-only; this control is the edit that mode does not stop
                copy_path.write_bytes(copy_path.read_bytes() + b"\n")
            got_t = guarded(lambda: quote_problems(tampered, [plain_id], stored_t, {}), ["RAISED"])
            control("a quote whose immutable copy no longer hashes as its version is SOURCE_TAMPERED by evidence id",
                    plain_id and got_t == [f"SOURCE_TAMPERED {plain_id}"], f"{plain_id} {got_t}")
            control("a cited quote no store holds is EVIDENCE_ABSENT by id",
                    quote_problems(gold, ["e-0000000000000000"], {}, {}) == ["EVIDENCE_ABSENT e-0000000000000000"], "listed")
            # sessions: a fabricated session id, at the function, over the golden subject
            sub_g = guarded(lambda: stage_form.subject(gold), {"events": [], "claims": {}})
            rows_g = guarded(lambda: census.rows(census.load(gold)), [])
            fabricated = {**formed_c, "sessions": list(formed_c.get("sessions", [])) + ["claude:00000000-0000-4000-8000-00000000dead"]}
            control("§6.5: a fabricated session id is SESSION_UNKNOWN and SESSION_MISMATCH by id",
                    session_problems(fabricated, sub_g, rows_g) == ["SESSION_UNKNOWN claude:00000000-0000-4000-8000-00000000dead",
                                                                   "SESSION_MISMATCH claude:00000000-0000-4000-8000-00000000dead"],
                    f"{session_problems(fabricated, sub_g, rows_g)}")
            control("control: the candidate as S4 formed it has no session problem",
                    session_problems(formed_c, sub_g, rows_g) == [], f"{session_problems(formed_c, sub_g, rows_g)}")
            # inputs: S5 reads what S4 recorded, and nothing S4 did not finish
            stale = copy_of("stale")
            path = stale / "candidates.json"
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            control("an S4 output changed after S4 recorded it is refused by name before anything is written",
                    "candidates.json" in refusal(lambda: run(stale)) and not (stale / "checks.json").exists(),
                    refusal(lambda: run(stale)))
            # the driver, as a process
            cli = copy_of("cli")
            # The fixture's ledger reference, named for the subprocess: the in-process calls above read
            # it from the module-level value `fx_reader` set, which a child process does not inherit.
            from runlib import stage_read
            done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "retrieve", "--run-id", cli.name,
                                   "--out", str(cli.parent),
                                   "--checkout-ledger", stage_read.CHECKOUT_LEDGER],
                                  capture_output=True, text=True, timeout=600)
            said_cli = done.stdout + done.stderr
            control("the driver's `retrieve` runs S5 as a process, completes, and prints counts with the withheld line",
                    done.returncode == 0 and "S5 retrieve: declaration_seq" in said_cli
                    and "candidates not advanced to an absence sweep" in said_cli and record_of(cli).get("status") == "complete",
                    f"{done.returncode} {said_cli[-600:]}")
        # a run S4 has not completed is refused by name
        bare_root = root / "bare"
        bare, _s = stage_form.fx_s3(bare_root)
        said_bare = refusal(lambda: run(bare))
        control("S5 over a run S4 has not run is refused by name (INPUT_INVALID S4)", "INPUT_INVALID S4" in said_bare,
                said_bare[:300])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    for failure in failures:
        print(f"stage_retrieve --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stage_retrieve --self-test: OK ({len(ran)} controls: §6.2's retrieval - the top {PER_LAYER} of each layer, "
          f"every named unit and entry, the top {TOP_ENTRIES} ledger entries, the exception and the named hints in the "
          "query, reference units and identical copies; done-when 3's recurrence over lineage-linked census rows and its "
          "control; quotes verified again, altered and tampered; a fabricated session; the withheld absence with its "
          "count and reason; the stage over a golden run through S4, its inputs and the driver as a process)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    print("usage: stage_retrieve.py --self-test (the stage runs as `distill.py retrieve --run-id ID`)", file=sys.stderr)
    sys.exit(2)
