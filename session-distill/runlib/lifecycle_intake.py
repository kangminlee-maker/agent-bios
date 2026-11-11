#!/usr/bin/env python3
"""S4's lifecycle intake (plan WP-09; design §7.1, §7.4): the lifecycle inputs produced by code before formation.

Five sources, each a list of lifecycle candidates with an id of its own (`<source>:<target>`), so two candidates from
one entry or unit are two rows of the population (lead, D5 scope):

- `due_decision`: every incubate decision a run made that no later decision of its entry resolves
  (`ledger.unresolved_incubates`, design §7.1's `resolves`), whose expiry is on or before the window's last day: an
  incubating entry's, or a pending intervention on a placed entry (§12.3). Each carries the decision it resolves and
  the window's occasions S3 judged for its observation (`observations/<window>.jsonl`, `observations/resolutions.json`).
- `legacy`: every `incubating` entry that has received no applied decision of a run, marked `legacy, observation
  unavailable` (design §7.1's legacy incubation), in every run until it receives one.
- `obsolete_hint`: a unit of the occasion index S12 writes (WP-21) with no match in its three latest windows, all of
  basis source (`obsolete_hints`). The index does not exist yet; its rows are golden here, and a run with no index takes
  none, saying so.
- `redundancy_hint`: every pair of operative units of the current library (S2's `inventory/current.json`, the layers
  `tables/redundancy.json` excludes left out by name) whose similarity reaches the table's fixed threshold
  (`redundancy_pairs`). More pairs than the table's ceiling are refused (REDUNDANCY_OVER_CEILING), never cut.
- `g_cluster`: design §7.4's upward distillation: at least three placed learnings whose top retrieval hit over the same
  units is one unit (`upward_clusters`), the reading of "share retrieved principle text" lead decision D6 (iii)
  adopted. An arc retrospective needs a declared arc, and the declaration has no field for one, so there is none.

The pinned ledger is read as S3 reads it (`stage_read.pinned_ledger`); a schema 1 ledger is migrated in memory by the
cutover's own function (`ledger_migration.migrate`, lead decision D4) and never written.

`intake_problems` holds an intake against a fresh derivation of every source by id (plan WP-09 done-when 3): an id a
source derives that the intake lacks, or one the intake holds that no source derives, is INTAKE_INCOMPLETE by name.

  lifecycle_intake.py --self-test
"""
import collections
import copy
import datetime
import hashlib
import json
import math
import pathlib
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import coverage, ledger as ledger_lib, ledger_migration, records, search, stagelock, validate
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "redundancy.json"
SCHEMA_PATH = HERE / "schemas" / "intake.schema.json"
SOURCES = ("due_decision", "legacy", "obsolete_hint", "redundancy_hint", "g_cluster")  # = stage_form.INTAKE_SOURCES
LEGACY_MARK = "legacy, observation unavailable"   # design §7.1
OBSOLETE_RUN = 3        # design §7.1: "no match in three consecutive windows of basis source"
UPWARD_MIN = 3          # design §7.4: "clusters of at least three placed learnings"


# The checkout ledger this module's D4 leg copies, set by an author-side caller
# (`gates/check-ledger.py`); None in an installed tree, where the leg copies nothing.
CHECKOUT_LEDGER = None

def table():
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


# ---- the pinned ledger -----------------------------------------------------------------------------

def ledger_of(declaration, ledger_ref=None):
    """`(schema 2 document, how it was had)` of the ledger the declaration pins: a schema 2 ledger as it is, a schema 1
    ledger migrated in memory by the cutover's function. Nothing is written.

    `ledger_ref` names the ledger inside the declaration's checkout; without one, the module-level `CHECKOUT_LEDGER`
    the author-side caller sets. A packaged run has neither, and is then refused by name (LEDGER_UNNAMED S3) rather
    than reading whatever file a guessed path lands on."""
    from runlib import stage_read
    doc = stage_read.pinned_ledger(declaration, ledger_ref or CHECKOUT_LEDGER)
    if doc.get("schema") == 2:
        return doc, "schema 2"
    try:
        migrated, _removed = ledger_migration.migrate(doc)
    except ledger_migration.MigrationError as exc:
        raise Refused(f"LEDGER_INVALID S4: the schema {doc.get('schema')} pin does not migrate: {exc}") from exc
    return migrated, f"schema {doc.get('schema')}, migrated in memory"


def last_day(window):
    """The last day a half-open window covers, in its own zone."""
    _start, end, _id = coverage.window_bounds(window)
    return (end - datetime.timedelta(microseconds=1)).date().isoformat()


# ---- (a) and (b): from the ledger ------------------------------------------------------------------

def due_decisions(doc, window, occasions=None):
    """Design §7.1's due decisions: every unresolved incubate whose expiry is on or before the window's last day, with
    the window's occasions for its observation (`occasions` maps a decision id to them)."""
    day, out = last_day(window), []
    for d in ledger_lib.unresolved_incubates(doc):
        if d["expiry"] <= day:
            out.append({"candidate_id": f"due_decision:{d['decision_id']}", "source": "due_decision", "target_entry": d["entry"],
                        "resolves": d["decision_id"], "entry_status": d["status"], "expiry": d["expiry"],
                        "pending_intervention": d["status"] == "placed",
                        "occasions": (occasions or {}).get(d["decision_id"], {"instances": [], "resolution": None})})
    return out


def legacy_incubation(doc):
    """Design §7.1's legacy incubation: every incubating entry with no applied decision of a run."""
    out = []
    for entry in doc["entries"]:
        if entry["status"] != "incubating":
            continue
        if any(not ledger_lib.is_legacy(d) and d["applied"] is not None for d in entry["decisions"]):
            continue
        out.append({"candidate_id": f"legacy:{entry['id']}", "source": "legacy", "target_entry": entry["id"],
                    "resolves": None, "marks": [LEGACY_MARK],
                    "type": (entry.get("classification") or {}).get("type")})
    return sorted(out, key=lambda c: c["candidate_id"])


def window_occasions(run_dir, window):
    """The occasions S3 judged in this window for each due observation, by its id, and the resolution it derived: read
    through S3's own reader of its follow-up (`stage_read.stored_resolutions`), which believes the instances only when
    their lines are the ones S3 recorded and each resolution only when they derive it again (INSTANCE_IMMUTABLE,
    RESOLUTION_DRIFT). A follow-up of another window is refused by name (INPUT_INVALID)."""
    from runlib import stage_read
    run_dir = pathlib.Path(run_dir)
    _s, _e, window_id = coverage.window_bounds(window)
    doc = stage_read.stored_resolutions(run_dir)
    if doc["window"] != window_id:
        raise Refused(f"INPUT_INVALID {stage_read.RESOLUTIONS}: S3's follow-up is of {doc['window']!r}, and this run's "
                      f"window is {window_id!r}")
    rows = [json.loads(line) for line in records.jsonl_read(stagelock.confine(run_dir, run_dir / doc["instances"]))
            if line.strip()]
    out = collections.defaultdict(lambda: {"instances": [], "resolution": None})
    for r in rows:
        out[r["expected_id"]]["instances"].append({k: r[k] for k in ("occasion_locator", "exposure", "verdict", "basis")})
    for ident, r in doc["resolutions"].items():
        out[ident]["resolution"] = r["resolution"]
    return dict(out)



# ---- (c): the occasion index's hints --------------------------------------------------------------

def obsolete_hints(index_rows):
    """Design §7.1: a unit with no match in its three latest windows, each of basis source. `index_rows` are the
    occasion index's rows `{window_start, unit_id, matched, basis}` (WP-21 writes them; golden until it does). A window of
    another basis ends the run of source windows, as a match does: only consecutive source windows count."""
    by_unit = collections.defaultdict(list)
    for r in index_rows:
        by_unit[r["unit_id"]].append(r)
    out = []
    for unit, rows in sorted(by_unit.items()):
        run = 0
        for r in sorted(rows, key=lambda r: r["window_start"]):
            run = run + 1 if (r["basis"] == "source" and not r["matched"]) else 0
        if run >= OBSOLETE_RUN:
            out.append({"candidate_id": f"obsolete_hint:{unit}", "source": "obsolete_hint", "target_unit": unit,
                        "windows_without_match": run})
    return out


# ---- (d) and (e): BM25 over the current library's units -------------------------------------------

def keys_tf(text):
    """A unit's keys with their counts, as the full-source search keys a block (search.keys_of): lowercase words, and
    the character bigrams of a Hangul or CJK run."""
    counts = collections.Counter(w.lower() for w in search.WORD.findall(text) if len(w) <= search.MAX_KEY)
    for run in search.CJK.findall(text):
        counts.update(run[i:i + 2] for i in range(len(run) - 1))
    return counts, len(search.WORD.findall(text))


class Library:
    """BM25 (search.K1, search.B) over a set of documents `{id: text}`: `scores(query keys)` is every document's score
    for a query's distinct keys, through an inverted index."""

    def __init__(self, docs):
        self.ids = sorted(docs)
        self.tf, self.length = {}, {}
        postings = collections.defaultdict(list)
        for ident in self.ids:
            counts, n = keys_tf(docs[ident])
            self.tf[ident], self.length[ident] = counts, max(n, 1)
            for key in counts:
                postings[key].append(ident)
        self.postings = dict(postings)
        self.avg = (sum(self.length.values()) / len(self.ids)) if self.ids else 1.0
        size = len(self.ids)
        self.idf = {k: math.log(1 + (size - len(p) + 0.5) / (len(p) + 0.5)) for k, p in self.postings.items()}

    def scores(self, keys):
        out = collections.defaultdict(float)
        for key in keys:
            for ident in self.postings.get(key, ()):
                tf = self.tf[ident][key]
                out[ident] += self.idf[key] * tf * (search.K1 + 1) / (
                    tf + search.K1 * (1 - search.B + search.B * self.length[ident] / self.avg))
        return out


def relative_path(unit):
    """Where a unit's text sits, relative to the checkout or project that holds it (lead, D5 scope after X round 1). A
    native unit's path is recorded as `<host>:<type>:<path the host reported>` (inventory.member_carrier) and its
    provenance names its scope, the session's working directory, masked as the path is; a path under the scope is taken
    from it, so one file's copies in two checkouts read the same, and any other path is kept whole. Every other layer's
    path is already the checkout's own (a catalog guide, `<ledger>#<entry>`, an overlay)."""
    path = unit.get("path") or ""
    if not unit["layer"].startswith("native_"):
        return path
    reported = path.split(":", 2)[2] if path.count(":") >= 2 else path
    scope = ((unit.get("provenance") or {}).get("scope") or "").rstrip("/")
    return reported[len(scope) + 1:] if scope and reported.startswith(scope + "/") else reported


def eligible_units(units, spec):
    """The current library's units a hint reads, and what was left out, counted: operative units outside the table's
    excluded layers, one per fragment sha, with at least the table's `min_keys` distinct keys. Identical text is read
    once: where its copies share one layer and one relative path (`relative_path`) they are one file's copies, folded and
    counted; where they sit in more than one place, the group is returned as well, as identical text the owner can
    reduce. Returns `(kept, counts, identical groups)`, each group the unit ids of one unit per place, the kept one first."""
    operative = [u for u in units if u["class"] == "operative"]
    left = collections.Counter(u["layer"] for u in operative if u["layer"] in spec["excluded_layers"])
    groups = collections.defaultdict(list)
    for u in sorted((u for u in operative if u["layer"] not in spec["excluded_layers"]), key=lambda u: u["unit_id"]):
        groups[u["sha"]].append(u)
    distinct, places_of, copies = [], {}, 0
    for members in groups.values():
        places = {}
        for u in members:
            places.setdefault((u["layer"], relative_path(u)), u)
        copies += len(members) - len(places)
        distinct.append(members[0])
        places_of[members[0]["unit_id"]] = sorted(u["unit_id"] for u in places.values())
    kept = sorted((u for u in distinct if len(keys_tf(u["text"])[0]) >= spec["min_keys"]), key=lambda u: u["unit_id"])
    identical = [places_of[u["unit_id"]] for u in kept if len(places_of[u["unit_id"]]) > 1]
    return kept, {"excluded_layers": dict(sorted(left.items())), "identical_copies_folded": copies,
                  "identical_groups": len(identical), "below_min_keys": len(distinct) - len(kept),
                  "eligible": len(kept)}, identical


def similarities(units):
    """Every pair of `units` sharing a key, with its similarity: the smaller of the two directions, each one unit's
    BM25 over the other divided by its BM25 over itself. Returns `{(a, b): score}` with a < b."""
    lib = Library({u["unit_id"]: u["text"] for u in units})
    selfs, cross = {}, {}
    for a in lib.ids:
        row = lib.scores(lib.tf[a])
        selfs[a] = row.get(a, 0.0)
        cross[a] = row
    out = {}
    for a in lib.ids:
        if selfs[a] <= 0:
            continue
        for b, s in cross[a].items():
            if b <= a or selfs[b] <= 0:
                continue
            back = cross[b].get(a, 0.0)
            out[(a, b)] = min(s / selfs[a], back / selfs[b])
    return out


def redundancy_pairs(units, spec=None):
    """Design §7.1's redundancy hints over the current library, both operative by construction: every group of
    identical text in more than one place (`eligible_units`), one hint per group at similarity 1.0, and every pair of
    eligible units whose similarity reaches the fixed threshold. More hints than the ceiling is REDUNDANCY_OVER_CEILING.
    Returns `(candidates, excluded counts)`."""
    spec = table() if spec is None else spec
    kept, left, identical = eligible_units(units, spec)
    pairs = sorted((pair, score) for pair, score in similarities(kept).items() if score >= spec["threshold"])
    if len(pairs) + len(identical) > spec["ceiling"]:
        raise Refused(f"REDUNDANCY_OVER_CEILING {len(pairs) + len(identical)} redundancy hints ({len(identical)} groups of "
                      f"identical text, {len(pairs)} pairs at the threshold {spec['threshold']}), more than the ceiling "
                      f"{spec['ceiling']} tables/redundancy.json allows; the threshold is re-measured, never the list cut")
    same = [{"candidate_id": "redundancy_hint:" + "|".join(group), "source": "redundancy_hint", "target_units": group,
             "similarity": 1.0, "match": "identical"} for group in identical]
    near = [{"candidate_id": f"redundancy_hint:{a}|{b}", "source": "redundancy_hint", "target_units": [a, b],
             "similarity": round(score, 4), "match": "near"} for (a, b), score in pairs]
    return sorted(same + near, key=lambda c: c["candidate_id"]), left


def entry_text(entry):
    """The text of a ledger entry a retrieval reads: its lesson and its principle (the rule it states), as the upward
    clusters match it and S5's top ledger entries rank it (runlib/stage_retrieve.py)."""
    return " ".join(t for t in (entry.get("lesson"), entry.get("principle")) if t)


def upward_clusters(doc, units, spec=None):
    """Design §7.4's upward distillation: the placed learnings of the ledger whose top retrieval hit over the eligible
    units is one unit, at least three of them (lead decision D6 (iii)). A learning whose text matches no unit is in
    no cluster. Returns the candidates, each with the lessons the formation packet shows."""
    spec = table() if spec is None else spec
    kept, _left, _identical = eligible_units(units, spec)
    lib = Library({u["unit_id"]: u["text"] for u in kept})
    groups = collections.defaultdict(list)
    for entry in doc["entries"]:
        if entry["status"] != "placed":
            continue
        counts, _n = keys_tf(entry_text(entry))
        row = lib.scores(counts)
        if not row:
            continue
        top = max(row.values())
        best = min(i for i, s in row.items() if s == top)
        groups[best].append(entry)
    out = []
    for unit, entries in sorted(groups.items()):
        if len(entries) >= UPWARD_MIN:
            ordered = sorted(entries, key=lambda e: e["id"])
            out.append({"candidate_id": f"g_cluster:{unit}", "source": "g_cluster", "target_unit": unit,
                        "entries": [e["id"] for e in ordered], "lessons": [e["lesson"] for e in ordered],
                        # what the formation packet shows of each entry, under a label of its own (lead decision after X
                        # round 1, F2): its lesson, where its stored evidence is, and the lineages its record names
                        "members": [{"entry": e["id"], "lesson": e["lesson"], "evidence": copy.deepcopy(e.get("evidence") or []),
                                     "independent_lineages": e.get("independent_lineages")} for e in ordered]})
    return out


# ---- the intake --------------------------------------------------------------------------------------

def derive(doc, window, units, occasions=None, index_rows=None, spec=None):
    """Every source's candidates, and what the intake says beside them."""
    spec = table() if spec is None else spec
    redundancy, left = redundancy_pairs(units, spec)
    sources = {"due_decision": due_decisions(doc, window, occasions), "legacy": legacy_incubation(doc),
               "obsolete_hint": obsolete_hints(index_rows or []), "redundancy_hint": redundancy,
               "g_cluster": upward_clusters(doc, units, spec)}
    notes = {"obsolete_hint": "the occasion index S12 writes (WP-21) does not exist yet; no hint" if index_rows is None else None,
             "g_cluster_arc": "an arc retrospective needs a declared arc, and the declaration has no field for one",
             "excluded_layers": {layer: {"operative_units": left["excluded_layers"].get(layer, 0), "reason": reason}
                                 for layer, reason in sorted(spec["excluded_layers"].items())},
             "library_units": {k: left[k] for k in ("eligible", "identical_copies_folded", "identical_groups", "below_min_keys")}}
    return sources, notes


def build(run_dir, declaration, index_rows=None, ledger_ref=None):
    """`intake.json`'s document for a run: the pinned ledger (as `ledger_of` has it), the window's occasions S3 judged,
    the current library S2 left, and the golden occasion index rows when given. `declaration` is the one S4 was
    admitted against (`records.StageRun.declaration`), never a read of run.json (records.DECLARATION_READERS)."""
    run_dir = pathlib.Path(run_dir)
    doc, had = ledger_of(declaration, ledger_ref)
    units = records.read_json(run_dir / "inventory" / "current.json")["units"]
    sources, notes = derive(doc, declaration["window"], units, window_occasions(run_dir, declaration["window"]), index_rows)
    candidates = [c for s in SOURCES for c in sources[s]]
    doc = {"window": declaration["window"], "ledger": {"sha256": declaration["starting_hashes"]["ledger"], "read": had},
           "candidates": candidates, "notes": notes, "counts": {s: len(sources[s]) for s in SOURCES}}
    problems = schema_problems(doc)
    if problems:
        raise Refused("INTAKE_INVALID " + "; ".join(problems[:5]))
    return doc


def schema_problems(doc):
    """`intake.json`'s document against its schema, each violation a line."""
    return validate.validate_instance(validate.compile_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))), doc)


def intake_problems(intake, sources):
    """The intake against a derivation of every source by id (done-when 3): INTAKE_INCOMPLETE names an id a source
    derives that the intake lacks, and one the intake holds that no source derives."""
    want = {c["candidate_id"]: s for s in SOURCES for c in sources[s]}
    have = collections.Counter(c["candidate_id"] for c in intake["candidates"])
    errors = [f"INTAKE_INCOMPLETE {ident}: {want[ident]} derives it and the intake lacks it" for ident in sorted(set(want) - set(have))]
    errors += [f"INTAKE_INCOMPLETE {ident}: the intake holds it and no source derives it" for ident in sorted(set(have) - set(want))]
    errors += [f"INTAKE_INCOMPLETE {ident}: the intake holds it {n} times" for ident, n in sorted(have.items()) if n > 1]
    return errors


# ---- self-test ---------------------------------------------------------------------------------------

def fx_unit(unit_id, text, layer="catalog", cls="operative", path=None, scope=None):
    """A unit as S2's inventory records one: a native unit's path is `<host>:<type>:<path>`, its scope the session's."""
    unit = {"unit_id": unit_id, "layer": layer, "class": cls, "text": text, "sha": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "path": path if path is not None else f"claude/guides/{unit_id}.md"}
    if scope is not None:
        unit["provenance"] = {"scope": scope}
    return unit


FX_LIBRARY = [
    fx_unit("u-push", "Ask the person before you push to a shared remote; a push cannot be taken back quietly."),
    fx_unit("u-push2", "Ask the person before you push to the shared remote; a push cannot be taken back quietly."),
    fx_unit("u-glob", "Quote a glob in a zsh command line, or the shell expands it before the tool sees it."),
    fx_unit("u-tests", "Run the tests that cover the change before calling the change done."),
    fx_unit("u-ref", "Ask the person before you push to any shared remote; a push cannot be taken back quietly.", cls="reference"),
    fx_unit("u-codex", "Run the tests that cover a change before calling the change done.", layer="native_undivided"),
    fx_unit("u-codex2", "Run the tests that cover the change before you call the change done.", layer="native_undivided"),
    # u-glob's text again, in a project's AGENTS.md: identical text in two places, which the owner can reduce
    fx_unit("u-quote", "Quote a glob in a zsh command line, or the shell expands it before the tool sees it.", layer="native_project",
            path="claude:Project:<HOME>/b/AGENTS.md", scope="<HOME>/b"),
    # one project file in two checkouts of it: the same relative path, so one file's copies
    fx_unit("u-wt1", "Write the changelog entry beside the change it describes.", layer="native_project",
            path="claude:Project:<HOME>/a/CLAUDE.md", scope="<HOME>/a"),
    fx_unit("u-wt2", "Write the changelog entry beside the change it describes.", layer="native_project",
            path="claude:Project:<HOME>/a-wt/CLAUDE.md", scope="<HOME>/a-wt"),
    fx_unit("u-short", "Ask the person before you push."),
    fx_unit("u-true", "true"),
    fx_unit("u-true2", "true,"),
]


def fx_ledger(window_last="2026-11-05", due_expiry="2026-11-04"):
    """A schema 2 ledger with every case the intake tells apart: incubates due (expiring `due_expiry`) and not due, one
    resolved, a pending intervention on a placed entry, legacy entries with and without a run's decision, and placed
    learnings."""
    L = ledger_lib
    due = L.sample_element("r1", "incubate", observation=L.sample_observation(due_expiry))
    late = L.sample_element("r1", "incubate", observation=L.sample_observation("2026-12-31"))
    settled = L.sample_element("r2", "drop", reason="expired and not seen", resolves="N-3@r1")
    legacy = lambda eid, status: L.sample_entry(eid, status, decisions=[  # noqa: E731
        ledger_migration.element(f"legacy-{window_last}", "status", "unknown", "unavailable", window_last, status,
                                 kind="legacy_migration", legacy_status=status)])
    placed = lambda eid, lesson: L.sample_entry(eid, "placed", lesson=lesson, decisions=[L.sample_element("r0", "place")])  # noqa: E731
    return L.sample_ledger(
        L.sample_entry("N-1", "incubating", decisions=[copy.deepcopy(due)]),
        L.sample_entry("N-2", "incubating", decisions=[copy.deepcopy(late)]),
        L.sample_entry("N-3", "retired", decisions=[copy.deepcopy(due), settled]),
        L.sample_entry("P-1", "placed", decisions=[L.sample_element("r0", "place"), copy.deepcopy(due)]),
        legacy("M-1", "incubating"), legacy("M-2", "incubating"), legacy("M-3", "placed"),
        placed("S-1", "run the tests before you call the change done"),
        placed("S-2", "a change is done only after the tests that cover it ran"),
        placed("S-3", "call a change done after running the tests that cover the change"),
        placed("S-4", "quote a glob in a zsh command line"),
        placed("S-5", "zsh expands an unquoted glob before the tool sees it"))


FX_WINDOW = {"start": "2026-11-05T00:00:00", "end": "2026-11-06T00:00:00", "tz": "Asia/Seoul"}


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
            return default(exc) if callable(default) else default

    def refusal(action):
        try:
            action()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            return f"RAISED {exc!r}"
        return ""

    spec = {"threshold": 0.7, "min_keys": 3, "ceiling": 10, "excluded_layers": {"native_undivided": "the host's own instructions"}}
    doc = guarded(fx_ledger, None)
    control("positive control: the fixture ledger validates", doc is not None and guarded(lambda: ledger_lib.validate_ledger(doc), ["RAISED"]) == [],
            f"{guarded(lambda: ledger_lib.validate_ledger(doc), ['RAISED'])[:3]}")
    occasions = {"N-1@r1": {"instances": [{"occasion_locator": "v#3", "exposure": "eligible", "verdict": "observed", "basis": "source"}],
                            "resolution": "observed"}}
    sources, notes = guarded(lambda: derive(doc, FX_WINDOW, FX_LIBRARY, occasions, None, spec), lambda exc: ({}, {"problem": repr(exc)}))
    ids = {s: [c["candidate_id"] for c in sources.get(s, [])] for s in SOURCES}

    # (a) due decisions
    control("done-when 3 (a): an incubate whose expiry is on or before the window's last day enters, with the window's "
            "occasions for its observation",
            "due_decision:N-1@r1" in ids["due_decision"]
            and next(c for c in sources["due_decision"] if c["target_entry"] == "N-1")["occasions"]["resolution"] == "observed",
            f"{ids['due_decision']} {notes.get('problem')}")
    control("done-when 3: a pending intervention on a placed entry enters, not only incubating entries",
            "due_decision:P-1@r1" in ids["due_decision"]
            and next((c for c in sources["due_decision"] if c["target_entry"] == "P-1"), {}).get("pending_intervention") is True,
            f"{ids['due_decision']}")
    control("done-when 3 (a): an incubate whose expiry lies after the window, and one a later decision resolves, do not "
            "enter; each due decision names the decision it resolves",
            "due_decision:N-2@r1" not in ids["due_decision"] and "due_decision:N-3@r1" not in ids["due_decision"]
            and all(c["resolves"] == c["candidate_id"].split(":", 1)[1] for c in sources["due_decision"]),
            f"{ids['due_decision']}")
    control("the window's last day is the day before a half-open window's end at midnight",
            guarded(lambda: last_day(FX_WINDOW), None) == "2026-11-05"
            and guarded(lambda: last_day({**FX_WINDOW, "end": "2026-11-06T09:00:00"}), None) == "2026-11-06",
            f"{guarded(lambda: last_day(FX_WINDOW), None)}")
    # (b) legacy incubation
    control("done-when 3 (b): every incubating entry with no applied decision of a run enters as legacy, observation "
            "unavailable; a placed legacy entry and an entry with a run's decision do not",
            ids["legacy"] == ["legacy:M-1", "legacy:M-2"]
            and all(c["marks"] == [LEGACY_MARK] for c in sources["legacy"]), f"{ids['legacy']}")
    # the two scratch runs: an entry that received an applied decision in the previous run does not re-enter
    after = copy.deepcopy(doc) if doc else None
    if after:
        m1 = next(e for e in after["entries"] if e["id"] == "M-1")
        m1["decisions"].append(ledger_lib.sample_element("r5", "incubate", observation=ledger_lib.sample_observation("2027-01-31")))
    second = guarded(lambda: derive(after, FX_WINDOW, FX_LIBRARY, None, None, spec)[0], {})
    control("done-when 3 (two scratch runs): an entry that received an applied decision in the previous run does not "
            "re-enter, as legacy or as due",
            "legacy:M-1" in ids["legacy"] and guarded(lambda: ledger_lib.validate_ledger(after), ["RAISED"]) == []
            and "legacy:M-1" not in [c["candidate_id"] for c in second.get("legacy", [])]
            and not any(c["target_entry"] == "M-1" for c in second.get("due_decision", [])),
            f"{[c['candidate_id'] for c in second.get('legacy', [])]}")
    # (c) obsolete hints over the golden occasion index
    row = lambda day, unit, matched, basis="source": {"window_start": day, "unit_id": unit, "matched": matched, "basis": basis}  # noqa: E731
    index = [row("2026-10-01", "u-a", False), row("2026-10-08", "u-a", False), row("2026-10-15", "u-a", False),
             row("2026-10-08", "u-b", False), row("2026-10-15", "u-b", False),
             row("2026-10-01", "u-c", False), row("2026-10-08", "u-c", False, "view"), row("2026-10-15", "u-c", False),
             row("2026-10-22", "u-c", False),
             row("2026-10-01", "u-d", False), row("2026-10-08", "u-d", False), row("2026-10-15", "u-d", False),
             row("2026-10-22", "u-d", True)]
    hints = [c["candidate_id"] for c in guarded(lambda: obsolete_hints(index), [])]
    control("done-when 3 (c): a unit with no match in three consecutive source-basis windows is an obsolete hint; two "
            "are not; a view-basis window breaks the run; a later match ends it",
            hints == ["obsolete_hint:u-a"], f"{hints}")
    control("with no occasion index, the intake takes no obsolete hint and says why",
            ids["obsolete_hint"] == [] and "WP-21" in (notes.get("obsolete_hint") or ""), f"{notes.get('obsolete_hint')}")
    # (d) redundancy hints
    near_hints = [c["candidate_id"] for c in sources.get("redundancy_hint", []) if c.get("match") == "near"]
    control("done-when 3 (d): a near-duplicate pair of operative units reaches the threshold and is a redundancy hint",
            near_hints == ["redundancy_hint:u-push|u-push2"], f"{ids['redundancy_hint']}")
    control("D5 scope: a reference unit and the excluded layer's units are no part of a pair, and the units the layer "
            "left out are counted with its reason",
            not any("u-ref" in i or "u-codex" in i for i in ids["redundancy_hint"])
            and notes.get("excluded_layers", {}).get("native_undivided", {}).get("operative_units") == 2,
            f"{notes.get('excluded_layers')}")
    same_hints = [c for c in sources.get("redundancy_hint", []) if c.get("match") == "identical"]
    control("one file's copies in two checkouts (one layer, one path relative to its scope) are folded and counted, and "
            "are no hint",
            not any("u-wt" in i for i in ids["redundancy_hint"]) and notes.get("library_units", {}).get("identical_copies_folded") == 1
            and guarded(lambda: [relative_path(u) for u in FX_LIBRARY if u["unit_id"].startswith("u-wt")], []) == ["CLAUDE.md"] * 2,
            f"{notes.get('library_units')} {ids['redundancy_hint']}")
    control("identical text in two places (another layer, or another relative path) is one redundancy hint at similarity "
            "1.0 naming one unit of each place, and is paired no further",
            [(c["candidate_id"], c["similarity"], c["target_units"]) for c in same_hints]
            == [("redundancy_hint:u-glob|u-quote", 1.0, ["u-glob", "u-quote"])]
            and notes.get("library_units", {}).get("identical_groups") == 1
            and sum("u-quote" in i for i in ids["redundancy_hint"]) == 1, f"{[c['candidate_id'] for c in same_hints]}")
    control("a unit of fewer than min_keys keys is left out, counted, and never paired",
            not any("u-true" in i for i in ids["redundancy_hint"])
            and notes.get("library_units", {}).get("below_min_keys") == 2, f"{notes.get('library_units')}")
    table_now = guarded(table, {})
    control("the table's threshold, floor and ceiling are numbers with the measurement they rest on, and each excluded "
            "layer carries its reason",
            isinstance(table_now.get("threshold"), (int, float)) and isinstance(table_now.get("min_keys"), int)
            and isinstance(table_now.get("ceiling"), int) and "measured" in table_now.get("basis", "")
            and table_now.get("excluded_layers") and all(r for r in table_now["excluded_layers"].values()), f"{table_now}")
    sims = guarded(lambda: similarities([u for u in FX_LIBRARY if u["layer"] == "catalog" and u["class"] == "operative"
                                         and not u["unit_id"].startswith("u-true")]), {})
    control("the similarity of a pair is one number for both orders, at most 1, and the near-duplicate's is far above "
            "an unrelated pair's",
            sims and all(a < b and 0 <= s <= 1.0000001 for (a, b), s in sims.items())
            and sims.get(("u-push", "u-push2"), 0) >= 0.7 and sims.get(("u-glob", "u-push"), 0) < 0.3,
            f"{ {k: round(v, 3) for k, v in sims.items()} }")
    control("a short unit whose every key a longer one holds is no pair: the similarity is the smaller direction",
            not any("u-short" in i for i in ids["redundancy_hint"]) and sims.get(("u-push", "u-short"), 1) < 0.7,
            f"{ids['redundancy_hint']} {sims.get(('u-push', 'u-short'))}")
    control("more pairs than the ceiling are refused by name, never cut",
            refusal(lambda: redundancy_pairs(FX_LIBRARY, {**spec, "threshold": 0.0, "ceiling": 1})).startswith("REDUNDANCY_OVER_CEILING"),
            refusal(lambda: redundancy_pairs(FX_LIBRARY, {**spec, "threshold": 0.0, "ceiling": 1})))
    control("a group of identical text is a hint the ceiling counts: one near pair and one group over a ceiling of 1 are "
            "refused by name",
            refusal(lambda: redundancy_pairs(FX_LIBRARY, {**spec, "ceiling": 1})).startswith("REDUNDANCY_OVER_CEILING 2 redundancy hints (1 groups"),
            refusal(lambda: redundancy_pairs(FX_LIBRARY, {**spec, "ceiling": 1})))
    # (e) G clusters
    control("done-when 3 (e): three placed learnings whose top hit is one unit are a G cluster with their lessons; two "
            "sharing a unit are not",
            ids["g_cluster"] == ["g_cluster:u-tests"]
            and next(c for c in sources["g_cluster"])["entries"] == ["S-1", "S-2", "S-3"], f"{sources.get('g_cluster')}")
    control("an arc retrospective needs a declared arc; there is none, and the intake says why",
            "arc" in (notes.get("g_cluster_arc") or ""), f"{notes.get('g_cluster_arc')}")
    # done-when 3: the intake equals the sources' union by id
    intake = {"candidates": [c for s in SOURCES for c in sources.get(s, [])]}
    control("done-when 3: an intake holding every source's candidates passes", guarded(lambda: intake_problems(intake, sources), ["RAISED"]) == [],
            f"{guarded(lambda: intake_problems(intake, sources), ['RAISED'])}")
    short = {"candidates": [c for c in intake["candidates"] if c["candidate_id"] != "due_decision:N-1@r1"]}
    control("done-when 3: one due decision removed from the produced intake is INTAKE_INCOMPLETE naming it",
            any(p.startswith("INTAKE_INCOMPLETE due_decision:N-1@r1:") for p in guarded(lambda: intake_problems(short, sources), [])),
            f"{guarded(lambda: intake_problems(short, sources), [])}")
    stray = {"candidates": intake["candidates"] + [{"candidate_id": "legacy:Z-9", "source": "legacy"}]}
    control("an intake candidate no source derives is INTAKE_INCOMPLETE naming it",
            any(p.startswith("INTAKE_INCOMPLETE legacy:Z-9:") for p in guarded(lambda: intake_problems(stray, sources), [])),
            f"{guarded(lambda: intake_problems(stray, sources), [])}")
    # one entry, two candidates: told apart by id, both in the population
    from runlib import stage_form
    two = [{"candidate_id": "legacy:M-1", "source": "legacy"}, {"candidate_id": "redundancy_hint:L-M-1|u-push", "source": "redundancy_hint"}]
    pop = guarded(lambda: stage_form.population({"candidates": [], "rejected_findings": [], "non_findings": []},
                                                {"events": [], "carried_forward": [], "not_formed": [], "units": {}}, "r9", two), {})
    control("two lifecycle candidates of one entry are two rows of the population, told apart by id",
            pop.get("candidate_ids") == ["legacy:M-1", "redundancy_hint:L-M-1|u-push"]
            and guarded(lambda: stage_form.population_problems(pop, {"events": [], "carried_forward": [], "not_formed": [],
                                                                     "units": {}}, two), ["RAISED"]) == [],
            f"{pop.get('candidate_ids')}")
    # done-when 7: the sources equal the formation contract's closed list, and the intake schema holds them
    schema = guarded(lambda: json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), {})
    enum = schema.get("$defs", {}).get("candidate", {}).get("properties", {}).get("source", {}).get("enum")
    control("done-when 7: the intake's sources equal design §7.1's list (stage_form.INTAKE_SOURCES), in code and in the "
            "intake schema", SOURCES == stage_form.INTAKE_SOURCES and enum == list(SOURCES), f"{SOURCES} {enum}")
    built = {"candidates": intake["candidates"], "window": FX_WINDOW, "ledger": {"sha256": "0" * 64, "read": "schema 2"},
             "notes": notes, "counts": {s: len(sources.get(s, [])) for s in SOURCES}}
    from runlib import validate
    control("the intake document passes its schema", guarded(lambda: validate.validate_instance(validate.compile_schema(schema), built), ["RAISED"]) == [],
            f"{guarded(lambda: validate.validate_instance(validate.compile_schema(schema), built), ['RAISED'])[:3]}")

    def bent_build():
        """build over a derivation bent to return a redundancy hint naming one unit, which the intake schema refuses."""
        bad = {s: [] for s in SOURCES}
        bad["redundancy_hint"] = [{"candidate_id": "redundancy_hint:u-one", "source": "redundancy_hint", "target_units": ["u-one"],
                                   "similarity": 1.0, "match": "identical"}]
        saved = {name: globals()[name] for name in ("ledger_of", "window_occasions", "derive")}
        globals().update(ledger_of=lambda declaration, ledger_ref=None: (doc, "schema 2"),
                         window_occasions=lambda run_dir, window: {},
                         derive=lambda *args, **kwargs: (bad, notes))
        try:
            with tempfile.TemporaryDirectory(prefix="intake-") as td:
                (pathlib.Path(td) / "inventory").mkdir()
                (pathlib.Path(td) / "inventory" / "current.json").write_text('{"units": []}', encoding="utf-8")
                return build(td, {"window": FX_WINDOW, "starting_hashes": {"ledger": "0" * 64}})
        finally:
            globals().update(saved)
    control("build refuses an intake document its schema refuses (INTAKE_INVALID), before any stage writes it",
            refusal(bent_build).startswith("INTAKE_INVALID"), refusal(bent_build))
    # D4: the pinned ledger is had as it is when it is schema 2 and migrated in memory when it is
    # schema 1, and its file is never written. The repository's own file was schema 1 until the
    # WP-22 cutover moved it, so this leg judges the file by the schema it actually carries and
    # keeps a schema 1 FIXTURE beside it: a control that only knew the migration path stopped
    # testing the migration the moment the real file stopped being schema 1.
    with tempfile.TemporaryDirectory(prefix="intake-") as td:
        checkout = pathlib.Path(td)
        # The fixture writes the ledger where the READ will look for it: the reference the
        # author-side caller injected, so the path is named once and in one place.
        rel = checkout / (CHECKOUT_LEDGER or ledger_lib.STATE_LEDGER_REL)
        rel.parent.mkdir(parents=True, exist_ok=True)
        # The owner's own ledger when this runs from a checkout, and nothing when it does not: the
        # path of a checkout's ledger is not a thing shipped code may name (WP-24).
        real = pathlib.Path(CHECKOUT_LEDGER) if CHECKOUT_LEDGER else None
        raw = real.read_bytes() if real is not None and real.is_file() else b""
        rel.write_bytes(raw)
        declaration = {"destinations": {"checkout": str(checkout)},
                       "starting_hashes": {"ledger": hashlib.sha256(raw).hexdigest()}}
        had = guarded(lambda: ledger_of(declaration), lambda exc: (None, repr(exc)))
        migrated, how = had
        pinned = json.loads(raw) if raw else {}
        incubating = sum(1 for e in pinned.get("entries", []) if str(e.get("status", "")).startswith("incubating"))
        legacy_ids = [c["candidate_id"] for c in guarded(lambda: legacy_incubation(migrated), [])] if migrated else []
        expected_how = {1: "schema 1, migrated in memory", 2: "schema 2"}.get(pinned.get("schema"))
        if not raw:
            # The owner's schema 1 ledger lives in a checkout, which shipped code may not name
            # (WP-24): the author-side caller sets CHECKOUT_LEDGER, and without it this leg is
            # reported as skipped by name rather than passing over an empty file.
            print("lifecycle_intake --self-test SKIPPED: D4, the migration of the repository's schema 1 "
                  "ledger (set CHECKOUT_LEDGER, as gates/check-ledger.py does)")
        else:
            control("D4: the repository's ledger is had by the schema it carries, and its every incubating entry is a "
                    "legacy candidate, its file unchanged",
                    expected_how is not None and how == expected_how and incubating > 0
                    and len(legacy_ids) == incubating and hashlib.sha256(rel.read_bytes()).hexdigest() == hashlib.sha256(raw).hexdigest(),
                    f"schema={pinned.get('schema')} {how} incubating={incubating} legacy={len(legacy_ids)}")
        # The migration path, on a subject this suite owns: whatever schema the repository's file
        # carries today, a schema 1 pin is still migrated in memory and its entries still arrive.
        fixture = checkout / "fx-schema1-pin.json"
        fx_raw = json.dumps({"schema": 1, "framework": "f",
                             "window": "census ending 2026-08-25 (previous: census 21d ending 2026-07-18)",
                             "entries": [{"id": "FX-1", "lesson": "a legacy candidate\n", "status": "incubating",
                                          "window": "2026-08-25", "surfaced": "2026-08-25", "classification": None},
                                         {"id": "FX-2", "lesson": "a placed one\n", "status": "placed",
                                          "window": "2026-08-25", "surfaced": "2026-08-25", "classification": None}]},
                            ensure_ascii=False).encode()
        fixture.write_bytes(fx_raw)
        fx_declaration = {"destinations": {"checkout": str(checkout)},
                          "starting_hashes": {"ledger": hashlib.sha256(fx_raw).hexdigest()}}
        fx_doc, fx_how = guarded(lambda: ledger_of(fx_declaration, "fx-schema1-pin.json"), lambda exc: (None, repr(exc)))
        fx_ids = [c["candidate_id"] for c in guarded(lambda: legacy_incubation(fx_doc), [])] if fx_doc else []
        control("D4: a schema 1 pin is migrated in memory by the cutover's function, its one incubating entry becomes "
                "a legacy candidate, and its file is not written",
                fx_how == "schema 1, migrated in memory" and len(fx_ids) == 1
                and (fx_doc or {}).get("schema") == 2 and fixture.read_bytes() == fx_raw,
                f"{fx_how} candidates={fx_ids}")
    control("the suite leaves no temporary tree", not checkout.exists(), str(checkout))

    for failure in failures:
        print(f"lifecycle_intake --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"lifecycle_intake --self-test: OK ({len(ran)} controls: " + "; ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    # `--checkout-ledger` is how an author-side caller hands this suite the owner's schema 1 ledger;
    # shipped code names no path under `design/` (WP-24), and without the flag the D4 leg is skipped
    # by name — which is also what an installed tree gets.
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: lifecycle_intake.py --self-test [--checkout-ledger PATH]")
    given = sys.argv[1:]
    if "--checkout-ledger" in given:
        at = given.index("--checkout-ledger")
        if at + 1 >= len(given):
            sys.exit("usage: --checkout-ledger takes a path")
        CHECKOUT_LEDGER = given[at + 1]
    sys.exit(self_test())
