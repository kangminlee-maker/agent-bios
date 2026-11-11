#!/usr/bin/env python3
"""S6 (plan WP-11): the judges A and B over S5's population, held to design §6.2.

This module holds the contract a judgment is held to, which no packet shape changes:

- the judgment schema (`schemas/judge.schema.json`) against §6.2's judged fields, both ways
  (`contract_problems`, CONTRACT_DRIFT): every field §6.2 names is a field of the schema, and every field of the
  schema is one §6.2 names or one this module declares with its reason (EXTRA_FIELDS);
- the reuse key (lead decision D12, D-20261111-f174ea): one key per (candidate, unit, seat), the hash of exactly §6.2's components
  (`unit_key`, `key_components`), the component list held against the design's (`key_problems`);
- one judgment payload for both judges (N#1): PACKET_DIVERGENCE when the payloads two seats were sent differ
  (`divergence`), RECEIPT_STALE when two calls' receipts carry one packet hash, since a receipt serves one call
  (`receipt_problems`);
- the answer a judge returns, checked against the packet it answered (`answer_problems`): every unit judged once,
  a quote exactly where a match is yes (D14, D-20261111-1aa1b3) and a span of that unit's text, every matching unit's following and
  contribution, every ledger entry's relation, labels the packet shows;
- the consequence classes, owned by the schema's enum (lead decision D11, D-20261111-f3d39c), which the derivations' promotion row reads
  (`classes`).

The judgment packet (plan WP-11 J1b2, lead decision on J0's numbers: shape a1_min) is built by code from what the stores
hold, one per candidate and the same for both judges (`JudgeLabels`, `payload`, `packets/judge.md`): the candidate as
S5's population records it, its events, claims and quotes; the units S5 retrieved for it, each with its text, its
heading, the lines that enclose it (inventory `edges.direct`, in full) and the files it mentions (`edges.reached`, by
their headings and counts); the ledger entries S5 retrieved. Every stored id is turned into a label of the packet's
own, so no store's naming reaches a judge. A planted control's packet has a natural one's blocks, rows and fields
(`packet_markers`, F27). `distill.py judge --dry` builds every packet of the judged population and measures it per
seat (`run`).

The calls (plan WP-11 J2): `distill.py judge --cells DIR` sends every judged candidate to Judge A and Judge B through
the dispatcher, each judge an item of its own with the candidate's one payload (N#1). Each answer is held to its packet
by the stage (`check`) and kept in the stores' ids (`judgments/<item>/<A|B>.json`); the receipts carry the payload S6
built and one packet each (`stage_receipts`); a call whose capture shows an undeclared instruction is failed by the
gate whatever it answered (done-when 5). A re-run reuses every accepted attempt and calls only the rest; another run
reuses nothing, and one judge's attempt never answers the other's item (done-when 4's decidable halves; the reuse map and
the later reference point's call are deferred, D-20261111-c4fa71).

  stage_judge.py --self-test
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, controls, gate, lifecycle_intake, packet, records, stage_form, stage_retrieve, validate  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S6"
TEMPLATE = "judge"
SCHEMA_PATH = HERE / "schemas" / "judge.schema.json"
SEATS = ("A", "B")
REQUIREMENTS = ("observed_event", "consequence", "causal_support", "recognizable_in_advance", "actionable", "bounded",
                "positioned", "audience")

# Design §6.2, the judges' paragraph, as written: what both judges return per unit and per candidate. Each phrase is
# mapped to the schema paths that hold it; `contract_problems` holds the map against the schema both ways.
DESIGN_6_2_UNIT = {
    "situation match": ("units[].situation",),
    "action match": ("units[].action",),
    "reason": ("units[].reason",),
    "quoting the unit": ("units[].quote",),
}
DESIGN_6_2_CANDIDATE = {
    "each admission requirement `met | unmet | uncertain` with reason": ("requirements.*.mark", "requirements.*.reason"),
    "for each matching unit, its following (`followed | not_followed | unknown`)": ("matching_units[].following",),
    "its contribution to the outcome (`helped | harmed | neutral | unknown`)": ("matching_units[].contribution",),
    "each with evidence ids": ("matching_units[].following_evidence_ids", "matching_units[].contribution_evidence_ids"),
    "the consequence class": ("consequence_class",),
    "the relation to each retrieved ledger entry (recurrence, revision, contradiction, relation to a retired entry, "
    "or none)": ("ledger_relations[].relation",),
}
# Fields of the schema §6.2's paragraph does not name, each with the reason it is there.
EXTRA_FIELDS = {
    "units[].unit": "the packet's label of the unit judged, turned back into its stored id by code",
    "matching_units[].unit": "the label of the matching unit the following and contribution are of",
    "ledger_relations[].entry": "the packet's label of the ledger entry related",
    "ledger_relations[].reason": "the reason the relation is given, as every other judged field has one",
    "no_longer_arises.value": "§6.4 obsolete: both judges find that the situation no longer arises",
    "no_longer_arises.reason": "§6.4 obsolete: the reason for that finding",
    "no_longer_arises.evidence_ids": "§6.4 obsolete: 'a lifecycle candidate with evidence that the situation no "
                                     "longer arises'",
}
# Design §6.2's reuse key, as written: "the key is the hash of the packet itself — candidate version with its claim
# and evidence versions, unit text, heading path, the enclosing guide's or router line's trigger, enclosing
# exceptions, the operative units it references, layer, scope, prompt and schema versions, and seat".
DESIGN_6_2_KEY = ("candidate version", "claim versions", "evidence versions", "unit text", "heading path",
                  "the enclosing guide's or router line's trigger", "enclosing exceptions",
                  "the operative units it references", "layer", "scope", "prompt version", "schema version", "seat")


def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_paths(spec, defs, prefix=""):
    """Every leaf of a schema node as a dotted path, an array's items as `[]` and an object's named properties by
    name, `*` for properties sharing one shape (the requirements), `$ref` resolved."""
    if not isinstance(spec, dict):
        return []
    if "$ref" in spec:
        return schema_paths(defs[spec["$ref"].rsplit("/", 1)[-1]], defs, prefix)
    if spec.get("type") == "array":
        items = spec.get("items") or {}
        while isinstance(items, dict) and "$ref" in items:
            items = defs[items["$ref"].rsplit("/", 1)[-1]]
        if not (isinstance(items, dict) and items.get("type") == "object"):
            return [prefix]  # a list of scalars is one field: its values, not their positions, are judged
        return schema_paths(items, defs, prefix + "[]")
    props = spec.get("properties")
    if spec.get("type") == "object" and props:
        if set(props) == set(REQUIREMENTS):
            shapes = {json.dumps(v, sort_keys=True) for v in props.values()}
            if len(shapes) == 1:
                return schema_paths(next(iter(props.values())), defs, f"{prefix}.*" if prefix else "*")
        out = []
        for name, member in props.items():
            out += schema_paths(member, defs, f"{prefix}.{name}" if prefix else name)
        return out
    return [prefix]


def contract_problems(held=None):
    """Plan WP-11 done-when 8, the schema's half: CONTRACT_DRIFT for a field §6.2 names that the schema does not hold,
    and for a schema field neither §6.2 names nor EXTRA_FIELDS declares."""
    held = held or schema()
    defs = held.get("$defs") or {}
    paths = set(schema_paths(held, defs))
    named = {p for table in (DESIGN_6_2_UNIT, DESIGN_6_2_CANDIDATE) for ps in table.values() for p in ps}
    problems = [f"CONTRACT_DRIFT judge.schema.json: §6.2 names '{phrase}' and the schema holds no {p}"
                for table in (DESIGN_6_2_UNIT, DESIGN_6_2_CANDIDATE) for phrase, ps in table.items() for p in ps
                if p not in paths]
    problems += [f"CONTRACT_DRIFT judge.schema.json: {p} is a field §6.2 does not name and no reason declares"
                 for p in sorted(paths - named - set(EXTRA_FIELDS))]
    problems += [f"CONTRACT_DRIFT stage_judge.EXTRA_FIELDS: {p} declares a field the schema does not hold"
                 for p in sorted(set(EXTRA_FIELDS) - paths)]
    return problems


def classes(held=None):
    """The consequence classes (lead decision D11): the schema's enum is their one owner."""
    held = held or schema()
    return tuple(held["$defs"]["consequence_class"]["enum"])


# ---- which candidates are judged ------------------------------------------------------------------------------

# the sources S5's population names - S4's formed candidates and the lifecycle intake's (stage_form.INTAKE_SOURCES) -
# which are the keys of run.json's judged scope (held against the schema by the self-test)
SOURCES = ("formed",) + tuple(stage_form.INTAKE_SOURCES)


def check_failures(rows):
    """`{candidate id: codes}` of the candidates S5's checks failed (a quote that does not verify, a session problem):
    they are not judged, and stand rejected by check failure (lead, WP-11 stage 0)."""
    out = {}
    for row in rows:
        codes = sorted({p.split()[0] for p in (row.get("quote_problems") or []) + (row.get("session_problems") or [])})
        if row.get("quote_ok") is False or row.get("session_problems"):
            out[row["candidate_id"]] = codes
    return out


def judged_of(candidates, declaration, run_id, failed=()):
    """`(judged ids, left out)` (plan WP-11, lead decision on J0's numbers). Of the candidates S5's checks passed, a
    source run.json's `judge.candidate_kinds` maps to `all` is judged whole, one mapped to n by a sample of n drawn by
    code from the run id (the first n by the hash of run id and candidate id), one the map leaves out not at all; with
    no map every candidate is judged. `left out` names every candidate not judged, by source:
    `{source: {count, of, why}}`. A source S6 does not know is SOURCE_UNDECLARED."""
    kinds = ((declaration or {}).get("judge") or {}).get("candidate_kinds")
    by = {}
    for k in candidates:
        if k["candidate_id"] not in failed:
            by.setdefault(k["source"], []).append(k["candidate_id"])
    unknown = sorted(set(by) - set(SOURCES))
    if unknown:
        raise Refused(f"SOURCE_UNDECLARED {unknown}: S5's population names a source S6's judged scope has no key for "
                      f"({list(SOURCES)})")
    judged, left = [], {}
    for source in SOURCES:
        ids = sorted(by.get(source, []))
        scope = "all" if kinds is None else kinds.get(source)
        if scope == "all":
            judged += ids
            continue
        if scope is None:
            keep, why = [], "the declaration's judge.candidate_kinds leaves this source out"
        else:
            keep = sorted(ids, key=lambda i: hashlib.sha256(f"{run_id}\x00{i}".encode("utf-8")).hexdigest())[:scope]
            why = f"a sample of {scope} drawn from the run id"
        judged += keep
        if len(keep) < len(ids):
            left[source] = {"count": len(ids) - len(keep), "of": len(ids), "why": why}
    return sorted(judged), left


# ---- the reuse key --------------------------------------------------------------------------------------------

def sha256_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def key_components(candidate, claims, quotes, unit, trigger, exceptions, references, prompt_sha256, schema_sha256, seat):
    """§6.2's components of one (candidate, unit, seat) judgment, by the design's own names: the candidate record, its
    claims and its quotes as the packet shows them, the unit's text, heading and layer and scope, the units that enclose
    it as its trigger (frontmatter and router lines) and its exceptions (the headings and conditions above it), the
    operative units it references (by id and the hash of their text), the template's and the schema's hashes, the seat.
    `unit` is `{unit_id, text, heading, layer, scope}`; `trigger`, `exceptions` and `references` lists of
    `{unit_id, text}`."""
    return {
        "candidate version": sha256_json(candidate),
        "claim versions": sha256_json(claims),
        "evidence versions": sha256_json(quotes),
        "unit text": hashlib.sha256(unit["text"].encode("utf-8")).hexdigest(),
        "heading path": unit["heading"],
        "the enclosing guide's or router line's trigger": sha256_json(sorted((u["unit_id"], u["text"]) for u in trigger)),
        "enclosing exceptions": sha256_json(sorted((u["unit_id"], u["text"]) for u in exceptions)),
        "the operative units it references": sha256_json(sorted((u["unit_id"], hashlib.sha256(u["text"].encode("utf-8"))
                                                                 .hexdigest()) for u in references)),
        "layer": unit["layer"],
        "scope": unit.get("scope"),
        "prompt version": prompt_sha256,
        "schema version": schema_sha256,
        "seat": seat,
    }


def unit_key(components):
    """The reuse key (D12): the hash of exactly §6.2's components, refused by name when it is handed any other set."""
    problems = key_problems(tuple(components))
    if problems:
        raise Refused("\n".join(problems))
    return sha256_json(components)


def key_problems(names):
    """Plan WP-11 done-when 8, the key's half: CONTRACT_DRIFT when the key's components are not §6.2's."""
    missing, extra = [n for n in DESIGN_6_2_KEY if n not in names], [n for n in names if n not in DESIGN_6_2_KEY]
    return ([f"CONTRACT_DRIFT reuse key: §6.2's component '{n}' is not in the key" for n in missing]
            + [f"CONTRACT_DRIFT reuse key: '{n}' is not a component §6.2 names" for n in extra])


# ---- one payload, one receipt per call ------------------------------------------------------------------------

def divergence(payloads):
    """N#1: both judges are sent one judgment payload. `payloads` maps a seat to the payload text it was sent;
    PACKET_DIVERGENCE names the first line where two differ."""
    seats = sorted(payloads)
    out = []
    for other in seats[1:]:
        a, b = payloads[seats[0]].splitlines(), payloads[other].splitlines()
        if a == b and payloads[seats[0]] == payloads[other]:
            continue
        line = next((n for n, (x, y) in enumerate(zip(a, b), 1) if x != y), min(len(a), len(b)) + 1)
        out.append(f"PACKET_DIVERGENCE {seats[0]} {other}: the payloads differ from line {line}; both judges are sent "
                   "one judgment payload, and a seat's envelope is the only part of a packet that is its own")
    return out


def receipt_problems(receipts):
    """A receipt serves one call: RECEIPT_STALE when two receipts carry one `packet_sha256`, and PACKET_DIVERGENCE when
    the receipts of one judgment's seats carry different `evidence.payload_sha256`. `receipts` maps a call id to
    `(seat, receipt)`, the seats of one judgment."""
    out, by_packet, payloads = [], {}, {}
    for call_id, (seat, receipt) in sorted(receipts.items()):
        digest = receipt.get("packet_sha256")
        if digest in by_packet:
            out.append(f"RECEIPT_STALE {call_id}: its receipt carries the packet hash {str(digest)[:12]} of "
                       f"{by_packet[digest]}; a receipt serves one call")
        by_packet.setdefault(digest, call_id)
        payloads.setdefault((receipt.get("evidence") or {}).get("payload_sha256"), []).append(f"{seat}:{call_id}")
    if len(payloads) > 1:
        out.append("PACKET_DIVERGENCE receipts: the judges' receipts carry "
                   + ", ".join(f"{str(p)[:12]} ({', '.join(c)})" for p, c in sorted(payloads.items(), key=str))
                   + "; both judges are sent one judgment payload")
    return out


# ---- the answer against its packet ----------------------------------------------------------------------------

def answer_problems(shown, answer, first=True):
    """What a schema-valid answer gets wrong against the packet it answered, each by name. `shown` is
    `{units: {label: text}, quotes: [labels], entries: [labels]}`; `first` is the candidate's first call, which also
    judges its requirements, class, matching units and ledger relations (D12), while a later reference point's call
    judges its units only."""
    out = []
    units = shown["units"]
    seen = {}
    for n, row in enumerate(answer.get("units") or []):
        label = row["unit"]
        where = f"units[{n}] {label}"
        if label not in units:
            out.append(f"UNKNOWN_LABEL {where}: this packet shows no unit so labelled")
            continue
        if label in seen:
            out.append(f"UNIT_JUDGED_TWICE {where}: judged at units[{seen[label]}] already")
            continue
        seen[label] = n
        matched = "yes" in (row["situation"], row["action"])
        if matched and not row["quote"]:
            out.append(f"QUOTE_MISSING {where}: a match is yes and no words of the unit show it (D14)")
        elif not matched and row["quote"]:
            out.append(f"QUOTE_UNEXPECTED {where}: neither match is yes, and a quote is given only where one is (D14)")
        elif matched and row["quote"] not in units[label]:
            out.append(f"QUOTE_NOT_IN_UNIT {where}: the quote is not a span of the unit's text")
    out += [f"UNIT_UNJUDGED {label}: the packet shows it and the answer does not judge it"
            for label in units if label not in seen]
    if not first:
        for field in ("matching_units", "ledger_relations"):
            if answer.get(field):
                out.append(f"FIELD_UNEXPECTED {field}: a later reference point's call judges its units only (D12)")
        return out
    matching = {label for label, n in seen.items()
                if "yes" in (answer["units"][n]["situation"], answer["units"][n]["action"])}
    given = {}
    quotes = set(shown.get("quotes") or ())
    for n, row in enumerate(answer.get("matching_units") or []):
        where = f"matching_units[{n}] {row['unit']}"
        if row["unit"] not in matching:
            out.append(f"MATCHING_UNIT_UNEXPECTED {where}: the unit is not one this answer finds matching")
        elif row["unit"] in given:
            out.append(f"MATCHING_UNIT_TWICE {where}")
        given.setdefault(row["unit"], n)
        out += [f"UNKNOWN_LABEL {where}: this packet shows no quote {q!r}"
                for q in row["following_evidence_ids"] + row["contribution_evidence_ids"] if q not in quotes]
    out += [f"MATCHING_UNIT_MISSING {label}: a matching unit's following and contribution are judged (§6.2)"
            for label in sorted(matching - set(given))]
    out += [f"UNKNOWN_LABEL no_longer_arises: this packet shows no quote {q!r}"
            for q in (answer.get("no_longer_arises") or {}).get("evidence_ids") or [] if q not in quotes]
    entries = list(shown.get("entries") or ())
    related = {}
    for n, row in enumerate(answer.get("ledger_relations") or []):
        if row["entry"] not in entries:
            out.append(f"UNKNOWN_LABEL ledger_relations[{n}] {row['entry']}: this packet shows no entry so labelled")
        elif row["entry"] in related:
            out.append(f"ENTRY_JUDGED_TWICE ledger_relations[{n}] {row['entry']}")
        related.setdefault(row["entry"], n)
    out += [f"ENTRY_UNJUDGED {e}: the packet shows the entry and the answer gives no relation to it"
            for e in entries if e not in related]
    return out


# ---- the judgment packet --------------------------------------------------------------------------------------

CASE = "judge"          # the judgment call's class (dispatch.class_key)
SEAT_KEYS = {"A": "S6.A", "B": "S6.B"}
# lead, on J0's numbers (2026-11-11): above the about 11.7k tokens J0 measured for 112 units with D14's quotes;
# re-derived when retrieval.per_layer changes
OUTPUT_CAP = 20_000
OUTPUT_CAP_BASIS = "J0 (2026-11-11): about 11.7k output tokens at 112 units with D14's quotes; re-derived when K changes"
INPUTS = ({"artifact": "checks.json", "producer_stage": "S5"},
          {"artifact": "checked-candidates.json", "producer_stage": "S5"},
          {"artifact": "read-results.json", "producer_stage": "S3"},
          {"artifact": "read.json", "producer_stage": "S3"},
          {"artifact": "observations/resolutions.json", "producer_stage": "S3"},
          {"artifact": "census.json", "producer_stage": "S1"},
          {"artifact": "coverage.json", "producer_stage": "S1"},
          {"artifact": "views.json", "producer_stage": "S2"},
          {"artifact": "inventory/current.json", "producer_stage": "S2"})
DRY_RECORD = "judgments/dry.json"
# the template's blocks, by the field that fills each and the tag that encloses it
BLOCKS = {"candidate": "candidate", "claims": "claims", "units": "units", "context": "context", "entries": "ledger_entries"}
# what the candidate block leaves out of a candidate's record: its ids (shown as labels elsewhere or not at all) and the
# lifecycle record, which it shows without the candidate's own id and source
CANDIDATE_HIDDEN = ("candidate_id", "label", "event_ids", "sessions", "lifecycle")
CLUSTER_PREFIX = "g_cluster:"  # a placed cluster's id (lifecycle_intake): the prefix and the unit its entries share


def item_of(candidate_id):
    """A candidate's item name in its calls: opaque, as a call directory's name must be whatever the id holds."""
    return "j" + hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:12]


class JudgeLabels:
    """What one judgment packet labels, in the order it lists them: the candidate's events v1, ... and their sessions
    s1, ...; the claims c1, ... its events and admission name; their quotes q1, ... and its events' origin quotes; the
    units S5 retrieved n1, ... in S5's order; the lines enclosing them that S5 did not retrieve x1, ...; the ledger
    entries S5 retrieved e1, .... The labels follow from what the packet lists, so a retry's packet shows the same ones
    and nothing stores them.

    `candidate` is a member of S5's population, `row` its checks.json row, `units` current.json's units by id (each
    with the `edges` S2's inventory publishes: EDGES_ABSENT otherwise), `entries` the ledger's by id, `subject_of`
    `stage_form.subject(run)`, `evidence` the evidence records by id (S3's stores and S5's population's). A quote the
    candidate cites that is neither one of its claims' nor one of its events' origins is shown with the candidate
    (`quotes`), from its record. A reference the stores do not hold is RECORD_INTEGRITY."""

    def __init__(self, candidate, row, units, entries, subject_of, evidence):
        cid = candidate["candidate_id"]
        self.candidate, self.unit_store, self.entry_store = candidate, units, entries
        events = {e["id"]: e for e in subject_of["events"]}
        missing = [e for e in candidate.get("event_ids") or [] if e not in events]
        if missing:
            raise Refused(f"RECORD_INTEGRITY S6 packet {cid}: events no S3 store holds: {missing[:5]}")
        self.event_rows = [events[e] for e in candidate.get("event_ids") or []]
        self.events = {f"v{n}": ev["id"] for n, ev in enumerate(self.event_rows, 1)}
        sessions = list(dict.fromkeys([ev["session"] for ev in self.event_rows] + list(candidate.get("sessions") or [])))
        self.sessions = {f"s{n}": s for n, s in enumerate(sessions, 1)}
        claims, admission = subject_of["claims"], candidate.get("admission") or {}
        named = list(dict.fromkeys([c for ev in self.event_rows for c in [*ev["claim_ids"], *ev["outcome_claim_ids"]]]
                                   + [c for req in admission.values() for c in req.get("claim_ids") or []]
                                   + list((candidate.get("tension") or {}).get("instance_claim_ids") or [])))
        missing = [c for c in named if c not in claims]
        if missing:
            raise Refused(f"RECORD_INTEGRITY S6 packet {cid}: claims no S3 store holds: {missing[:5]}")
        self.claim_rows = {c: claims[c] for c in named}
        self.claims = {f"c{n}": c for n, c in enumerate(named, 1)}
        quotes = list(dict.fromkeys([q["evidence_id"] for c in named for q in claims[c]["quotes"]]
                                    + [o["evidence_id"] for ev in self.event_rows for o in ev.get("origin", [])
                                       if o.get("evidence_id")]))
        # a quote the admission cites beyond its claims and its own events' origins: S4 may cite any quote its packet
        # showed, another event's origin among them
        self.cited = [q for q in dict.fromkeys(q for req in admission.values() for q in req.get("evidence_ids") or [])
                      if q not in quotes]
        missing = [q for q in self.cited if q not in evidence]
        if missing:
            raise Refused(f"RECORD_INTEGRITY S6 packet {cid}: its admission cites quotes no evidence record holds: "
                          f"{missing[:5]}")
        self.evidence = {q: evidence[q] for q in self.cited}
        self.quotes = {f"q{n}": q for n, q in enumerate(quotes + self.cited, 1)}
        self.unit_rows = list(row["retrieved_units"])
        self.units = {f"n{n}": r["unit_id"] for n, r in enumerate(self.unit_rows, 1)}
        of_unit = {v: k for k, v in self.units.items()}
        enclosing = []
        for r in self.unit_rows:
            unit = units.get(r["unit_id"])
            if unit is None:
                raise Refused(f"RECORD_INTEGRITY S6 packet {cid}: S5 retrieved {r['unit_id']}, which current.json "
                              "does not hold")
            if not isinstance(unit.get("edges"), dict):
                raise Refused(f"EDGES_ABSENT S6 packet {cid}: current.json's unit {r['unit_id']} carries no edges; S2's "
                              "inventory part is run again so every unit carries them (D-20261111-92d81a)")
            enclosing += [d for d in unit["edges"]["direct"] if d != r["unit_id"] and d not in of_unit]
        enclosing = list(dict.fromkeys(enclosing))
        missing = [d for d in enclosing if d not in units]
        if missing:
            raise Refused(f"RECORD_INTEGRITY S6 packet {cid}: an edge names units current.json does not hold: {missing[:5]}")
        self.context = {f"x{n}": d for n, d in enumerate(enclosing, 1)}
        self.entry_rows = list(row["ledger_entries"])
        missing = [r["entry_id"] for r in self.entry_rows if r["entry_id"] not in entries]
        if missing:
            raise Refused(f"RECORD_INTEGRITY S6 packet {cid}: S5 retrieved ledger entries the ledger does not hold: "
                          f"{missing[:5]}")
        self.entries = {f"e{n}": r["entry_id"] for n, r in enumerate(self.entry_rows, 1)}
        self.label_of = {stored: label for table in (self.events, self.sessions, self.claims, self.quotes, self.units,
                                                     self.context, self.entries) for label, stored in table.items()}

    def relabel(self, value):
        """`value` with every string that is a stored id this packet labels turned into its label. A type G candidate's
        tension names its cluster by the cluster's own id, `g_cluster:<the unit its entries are placed at>`
        (lifecycle_intake), which is shown as that unit's label."""
        if isinstance(value, dict):
            return {k: self.relabel(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.relabel(v) for v in value]
        if isinstance(value, str) and value.startswith(CLUSTER_PREFIX) and value[len(CLUSTER_PREFIX):] in self.label_of:
            return self.label_of[value[len(CLUSTER_PREFIX):]]
        return self.label_of.get(value, value) if isinstance(value, str) else value

    def candidate_text(self):
        k = self.candidate
        view = {key: k[key] for key in sorted(k) if key not in CANDIDATE_HIDDEN}
        life = k.get("lifecycle")
        view["lifecycle"] = {key: v for key, v in sorted(life.items()) if key not in ("candidate_id", "source")} \
            if isinstance(life, dict) else None
        view["sessions"] = list(k.get("sessions") or [])
        view["quotes"] = [{"evidence_id": q, **stage_form.quote_row({"record": self.evidence[q].get("line"),
                                                                      "window_role": self.evidence[q]["window_role"],
                                                                      "text": self.evidence[q]["redacted_text"]})}
                          for q in self.cited]
        view["events"] = [{"event_id": ev["id"], "session": ev["session"], "kind": ev["kind"],
                           "description": ev["description"],
                           **({"origin": [{**({"evidence_id": o["evidence_id"]} if o.get("evidence_id") else {"citable": False}),
                                           "record": o["record"], "window_role": "origin", "text": o["text"],
                                           **({"cut": True} if o.get("cut") else {})} for o in ev["origin"]]}
                              if "origin" in ev else {}),
                           "claims": list(ev["claim_ids"]), "outcome_claims": list(ev["outcome_claim_ids"])}
                          for ev in self.event_rows]
        return json.dumps(self.relabel(view), ensure_ascii=False, sort_keys=True)

    def claims_text(self):
        if not self.claims:
            return "none"
        return "\n".join(json.dumps(self.relabel({
            "claim_id": ident, "fact": c["fact"], "interpretation": c["interpretation"], "uncertainty": c["uncertainty"],
            "quotes": [{"evidence_id": q["evidence_id"], **stage_form.quote_row(q)} for q in c["quotes"]]}),
            ensure_ascii=False) for ident, c in self.claim_rows.items())

    def units_text(self):
        if not self.units:
            return "none"
        shown = set(self.units.values()) | set(self.context.values())
        rows = []
        for r in self.unit_rows:
            unit = self.unit_store[r["unit_id"]]
            edges = unit["edges"]
            mentions = {}
            for ref in edges["reached"]:
                target = self.unit_store.get(ref)
                if target is not None:
                    held = mentions.setdefault(target.get("path") or "", {"headings": set(), "units": 0})
                    held["headings"].add(target.get("heading") or "")
                    held["units"] += 1
            rows.append(json.dumps(self.relabel({
                "unit_id": r["unit_id"], "layer": unit["layer"], "path": unit.get("path"), "heading": unit.get("heading") or "",
                "text": unit["text"], "named": bool(r.get("named")),
                "context": [d for d in edges["direct"] if d != r["unit_id"]],
                "mentions": [{"path": path, "headings": sorted(m["headings"]), "units": m["units"]}
                             for path, m in sorted(mentions.items())],
                "shown": sorted(ref for ref in edges["reached"] if ref in shown),
                "unresolved_mentions": sum(1 for ref in edges["reached"] if ref not in self.unit_store)}),
                ensure_ascii=False))
        return "\n".join(rows)

    def context_text(self):
        if not self.context:
            return "none"
        return "\n".join(json.dumps(self.relabel({
            "context_id": ident, "path": self.unit_store[ident].get("path"),
            "heading": self.unit_store[ident].get("heading") or "", "block": self.unit_store[ident].get("block"),
            "text": self.unit_store[ident]["text"]}), ensure_ascii=False) for ident in self.context.values())

    def entries_text(self):
        if not self.entries:
            return "none"
        return "\n".join(json.dumps(self.relabel({
            "entry_id": r["entry_id"], "status": r.get("status"), "named": bool(r.get("named")),
            "text": lifecycle_intake.entry_text(self.entry_store[r["entry_id"]])}), ensure_ascii=False)
            for r in self.entry_rows)

    def shown(self):
        """What `answer_problems` holds an answer to: the units by label with their text, the quote and entry labels."""
        return {"units": {label: self.unit_store[i]["text"] for label, i in self.units.items()},
                "quotes": list(self.quotes), "entries": list(self.entries)}

    def resolve(self, answer):
        """An accepted answer read back in the stores' ids: units and matching units by unit id, quotes by evidence id,
        ledger relations by entry id. Only an answer `answer_problems` passed reaches here, so every label is one this
        packet shows."""
        def quoted(ids):
            return [self.quotes[q] for q in ids]
        later = answer.get("no_longer_arises") or {}
        return {"requirements": answer["requirements"], "consequence_class": answer["consequence_class"],
                "no_longer_arises": {**later, "evidence_ids": quoted(later.get("evidence_ids") or [])},
                "units": [{"unit_id": self.units[r["unit"]], **{k: r[k] for k in ("situation", "action", "reason", "quote")}}
                          for r in answer["units"]],
                "matching_units": [{"unit_id": self.units[r["unit"]], "following": r["following"],
                                    "following_evidence_ids": quoted(r["following_evidence_ids"]),
                                    "contribution": r["contribution"],
                                    "contribution_evidence_ids": quoted(r["contribution_evidence_ids"])}
                                   for r in answer["matching_units"]],
                "ledger_relations": [{"entry_id": self.entries[r["entry"]], "relation": r["relation"], "reason": r["reason"]}
                                     for r in answer["ledger_relations"]]}


def payload(labels):
    """The judgment payload both judges are sent (N#1): `packets/judge.md` with its five blocks filled."""
    return packet.render(TEMPLATE, {"candidate": labels.candidate_text(), "claims": labels.claims_text(),
                                    "units": labels.units_text(), "context": labels.context_text(),
                                    "entries": labels.entries_text()})


def blocks_of(text):
    """`(frame, {field: rows})` of a payload: each block's JSON rows, and the text outside the blocks."""
    rows, frame = {}, text
    for field, tag in BLOCKS.items():
        found = re.search(f"<{tag}>\n(.*?)\n</{tag}>", frame, re.S)
        if found is None:
            raise Refused(f"PACKET_INVALID S6: the payload holds no <{tag}> block")
        body = found.group(1)
        rows[field] = [] if body == "none" else [json.loads(line) for line in body.splitlines()]
        frame = frame[:found.start(1)] + f"<{field}>" + frame[found.end(1):]
    return frame, rows


def packet_markers(control_text, natural_text):
    """F27 over two payloads: FRAME_DIFFERS when the text outside the blocks differs, and every MARKER_FIELD and
    MARKER_TYPE `controls.marker_problems` finds between their blocks' rows."""
    (c_frame, c_rows), (n_frame, n_rows) = blocks_of(control_text), blocks_of(natural_text)
    out = [] if c_frame == n_frame else ["FRAME_DIFFERS: the text outside the blocks is not the natural packet's"]
    for field in BLOCKS:
        out += controls.marker_problems(c_rows[field], n_rows[field], f"/{field}")
    return out


def seats_of(declaration):
    """`{A, B}`: the judges' seats as run.json declares them (`seats.S6.A`, `seats.S6.B`), SEAT_UNDECLARED otherwise."""
    held = (declaration or {}).get("seats") or {}
    missing = [key for key in SEAT_KEYS.values() if not held.get(key)]
    if missing:
        raise Refused(f"SEAT_UNDECLARED {missing}: S6's judges are seated by run.json, {list(SEAT_KEYS.values())}")
    return {who: held[key] for who, key in SEAT_KEYS.items()}


def limits_of(seat, run_dir, declaration, seats_path=None):
    """What one judgment call of `seat` is held to: the seat's context capacity and the host's measured hermetic
    allowance from seats.json (`gate.seat_capacity`), the run's density for this class of call and the host's retry
    share (`dispatch.measured_density`, `retry_share`), the output cap. What is not measured is named in `unmeasured`
    (ALLOWANCE_UNMEASURED, CAPACITY_UNDECLARED; lead decision D13: the first live call of a seat measures it)."""
    from runlib import dispatch
    path = gate.SEATS if seats_path is None else pathlib.Path(seats_path)
    host = seat.partition(":")[0]
    entry = (gate.seats(path).get("hosts") or {}).get(host) or {}
    slot = (entry.get("host_allowance") or {}).get("hermetic") or {}
    allowance = slot.get("allowance_tokens") if slot.get("measured") is True else None
    capacity, basis = gate.seat_capacity(seat, entry.get("version"), path=path)
    density = dispatch.measured_density(run_dir, seat, STAGE, CASE, (declaration or {}).get("density"))
    retry = dispatch.retry_share(run_dir, host, (declaration or {}).get("retry"))
    unmeasured = ([] if isinstance(allowance, int) else
                  [f"ALLOWANCE_UNMEASURED {seat}: seats.json holds no measured hermetic allowance for {host}"]) \
        + ([] if capacity is not None else [f"CAPACITY_UNDECLARED {seat}: {basis}"])
    return {"seat": seat, "capacity": capacity, "capacity_basis": basis, "allowance": allowance,
            "bytes_per_token": density["bytes_per_token"], "density_basis": density["basis"],
            "retry_margin": retry["margin"], "retries": retry["count"], "output_cap": OUTPUT_CAP, "unmeasured": unmeasured}


def at_most_of(size, limits):
    """Input tokens at most of a judgment call of `size` driver bytes under `limits` (`dispatch.input_at_most`), or None
    for a seat whose allowance or capacity is not measured."""
    from runlib import dispatch
    if limits["unmeasured"]:
        return None
    return dispatch.input_at_most(size, {"bytes_per_token": limits["bytes_per_token"]}, limits["allowance"], OUTPUT_CAP,
                                  limits["retry_margin"], limits["retries"])[1]


def beyond_capacity(size, limits):
    """Whether a call of `size` driver bytes, with room for its one retry's correction (S4's rule, stage_read's
    CORRECTION_ROOM) and the output cap, exceeds the seat's capacity; None when it cannot be told."""
    from runlib import stage_read
    at_most = at_most_of(size + stage_read.CORRECTION_ROOM, limits)
    return None if at_most is None else at_most + OUTPUT_CAP > limits["capacity"]


def measure(run_id, who, limits, text, schema_bytes, item):
    """`(driver bytes, input tokens at most or None, over the seat's capacity)` of one judge's packet."""
    built = packet.build(f"{run_id}-{STAGE}-{item}-{who}-a1", STAGE, limits["seat"], text, schema_bytes)
    size = bound.driver_bytes(built, schema_bytes)[0]
    return size, at_most_of(size, limits), beyond_capacity(size, limits)


def build(run_dir, declaration, seats_path=None):
    """`(summary, packets)` of S6 dry over a run (plan WP-11 J1b2), under the declaration its stage was admitted against:
    the candidates it judges (`check_failures`, `judged_of`), each one's packet and its measure per judge. `packets` maps
    a judged candidate to `(labels, payload)`."""
    run_dir = pathlib.Path(run_dir)
    run_id = run_dir.resolve().name
    seats = seats_of(declaration)
    checks = records.read_json(run_dir / "checks.json")
    population = records.read_json(run_dir / "checked-candidates.json")
    units = {u["unit_id"]: u for u in records.read_json(run_dir / "inventory" / "current.json")["units"]}
    ledger, _read = lifecycle_intake.ledger_of(declaration)
    entries = {e["id"]: e for e in ledger["entries"]}
    subject_of = stage_form.subject(run_dir)
    names = [t["name"] for t in records.read_json(run_dir / "views.json")["transcripts"]]
    evidence = {**stage_retrieve.stored_evidence(run_dir, names), **(population.get("evidence") or {})}
    rows = {r["candidate_id"]: r for r in checks["candidates"]}
    by_id = {k["candidate_id"]: k for k in population["candidates"]}
    if set(rows) != set(by_id):
        raise Refused(f"SET_MISMATCH S6: checks.json and checked-candidates.json name different candidates "
                      f"({len(set(rows) ^ set(by_id))} apart)")
    failed = check_failures(checks["candidates"])
    judged, left = judged_of(population["candidates"], declaration, run_id, failed)
    schema_bytes = packet.schema_bytes(schema())
    limits = {who: limits_of(seat, run_dir, declaration, seats_path) for who, seat in seats.items()}
    out, over, packets = [], {who: [] for who in seats}, {}
    for cid in judged:
        labels = JudgeLabels(by_id[cid], rows[cid], units, entries, subject_of, evidence)
        text, item = payload(labels), item_of(cid)
        packets[cid] = (labels, text)
        sizes = {who: measure(run_id, who, limits[who], text, schema_bytes, item) for who in seats}
        for who, (_size, _at_most, beyond) in sizes.items():
            if beyond:
                over[who].append(cid)
        out.append({"candidate_id": cid, "item": item, "source": by_id[cid]["source"], "units": len(labels.units),
                    "named_units": sum(1 for r in labels.unit_rows if r.get("named")), "context": len(labels.context),
                    "entries": len(labels.entries), "claims": len(labels.claims), "quotes": len(labels.quotes),
                    "payload_bytes": len(text.encode("utf-8")),
                    "payload_sha256": packet.sha256_bytes(text.encode("utf-8")),
                    "driver_bytes": {who: v[0] for who, v in sizes.items()},
                    "input_at_most": {who: v[1] for who, v in sizes.items()}})
    totals = {"calls": len(out) * len(seats), "payload_bytes": sum(r["payload_bytes"] for r in out),
              "driver_bytes": {who: sum(r["driver_bytes"][who] for r in out) for who in seats},
              "input_at_most": {who: (None if limits[who]["unmeasured"] else sum(r["input_at_most"][who] for r in out))
                                for who in seats},
              "output_at_most": len(out) * len(seats) * OUTPUT_CAP}
    summary = {"stage": STAGE, "declaration_seq": declaration["declaration_seq"], "dry": True,
               "population": {"candidates": len(by_id), "judged": len(judged), "check_failed": failed, "left_out": left},
               "seats": seats, "limits": limits, "output_cap": OUTPUT_CAP, "output_cap_basis": OUTPUT_CAP_BASIS,
               "template_sha256": packet.sha256_bytes(packet.template_text(TEMPLATE).encode("utf-8")),
               "schema_sha256": packet.sha256_bytes(schema_bytes), "packets": out, "totals": totals,
               "over_capacity": over,
               "budget": {"per_stage": ((declaration.get("budget") or {}).get("per_stage") or {}).get(STAGE)}}
    return summary, packets


# ---- the calls ------------------------------------------------------------------------------------------------

SUMMARY = "judgments/judge.json"
OUTCOMES = ("accepted", "failed", "not_done", "deferred", "budget_stopped")


def judgment_rel(item, who):
    """Where one judge's judgment of a candidate is kept: under the candidate's item name, since a candidate id may hold
    any character (`item_of`)."""
    return f"judgments/{item}/{who}.json"


def check(labels, capacity):
    """The stage's check of a judgment call's attempts, as `Supervisor.item(stage_check=)` asks it: the capacity the
    call was admitted against is the one its record carries (CAPACITY_UNRECORDED, S4's rule), and the answer judges the
    packet it was sent (`answer_problems`, a candidate's first call)."""
    from runlib import stage_read
    shown = labels.shown()

    def judged(call_dir):
        held = ((records.read_json(pathlib.Path(call_dir) / "call.json").get("bound")) or {}).get("context_capacity")
        if held != capacity:
            raise Refused(f"CAPACITY_UNRECORDED {pathlib.Path(call_dir).name}: its call record carries the capacity "
                          f"{held!r}, and S6 was admitted against {capacity!r}")
        return answer_problems(shown, stage_read.answer_of(call_dir), first=True)
    return judged


def attempt_problems(built, limits, schema_bytes, who):
    """The bound on one judgment attempt's packet as `Supervisor.item(packet_check=)` asks it, built under the call id
    its reservation gave it and, on a retry, carrying its correction: JUDGE_OVER_CAPACITY when it and the output cap
    exceed the seat's capacity. A seat whose capacity is not measured is not bounded here (D13)."""
    from runlib import stage_read
    size = bound.driver_bytes(built, schema_bytes)[0]
    beyond = beyond_capacity(max(size - stage_read.CORRECTION_ROOM, 0), limits)
    return [f"JUDGE_OVER_CAPACITY {who}: this attempt's packet of {size} driver bytes with the output cap exceeds the "
            f"seat's capacity {limits['capacity']}"] if beyond else []


def stage_receipts(calls):
    """N#1 over the accepted calls: each candidate's two receipts carry the payload S6 built for it and one payload hash
    between them (PACKET_DIVERGENCE), and no two receipts of the stage one packet hash (RECEIPT_STALE). `calls` are
    `(candidate id, seat, call id, receipt, payload sha256)`."""
    out, by_candidate = [], {}
    for cid, seat, call_id, receipt, built in calls:
        by_candidate.setdefault(cid, {})[call_id] = (seat, receipt)
        got = (receipt.get("evidence") or {}).get("payload_sha256")
        if got != built:
            out.append(f"PACKET_DIVERGENCE {call_id}: its receipt carries the payload hash {str(got)[:12]}, and S6 built "
                       f"{str(built)[:12]} for {cid}")
    for held in by_candidate.values():
        out += [p for p in receipt_problems(held) if not p.startswith("RECEIPT_STALE")]
    out += [p for p in receipt_problems({c: (s, r) for _cid, s, c, r, _b in calls}) if p.startswith("RECEIPT_STALE")]
    return out


# S6's golden host: dispatch's (FAKE_HOST) for both hosts, with what its Codex branch does not do
JUDGE_HOST = r'''
"""S6's golden host. It runs dispatch's golden host (FAKE_HOST) and adds two things: a Codex call is answered from the
plan, as FAKE_HOST's Claude branch answers one; and a plan row's `context` names a replayed capture (WP-03's planted
working directories) whose effective context replaces the one the host reports. argv: fake-host host mode spec-json."""
import json, os, pathlib, subprocess, sys
fake, host, mode, spec = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
packet = sys.stdin.buffer.read()
done = subprocess.run([sys.executable, fake, host, mode, json.dumps(spec)], input=packet, stdout=subprocess.PIPE)
text = packet.decode("utf-8")
call_id = text.splitlines()[0].split(": ", 1)[1]
plan = json.loads(pathlib.Path(spec["answers"]).read_text())
row = next((r for r in plan if all(t in text for t in r["match"])), None)
if row is not None and row.get("context") and done.returncode == 0:
    capture = pathlib.Path(os.environ["REVIEW_CAPTURE_DIR"]) / "host.json"
    held = json.loads(capture.read_text())
    held["context"] = json.loads(pathlib.Path(row["context"]).read_text())["context"]
    capture.write_text(json.dumps(held))
out = done.stdout
if host == "codex" and done.returncode == 0:
    out = json.dumps(row["answer"] if row is not None else {"unplanned": True}).replace("<CALL-ID>", call_id).encode()
sys.stdout.buffer.write(out)
sys.exit(done.returncode)
'''


def supervisor(run_dir, cells, plan=None, seats_path=None):
    """The supervisor S6's calls go through, their cells under `cells` (made mode 700). Live, the pinned runners: Judge
    A's token reaches claude-run only as CLAUDE_RUN_TOKEN_FILE in this process's environment - a path never read here,
    refused by name before anything is reserved when it is not set (TOKEN_FILE_UNSET). With `plan`, a golden host's plan
    (`[{match, answer, context?}]`, `JUDGE_HOST`), realization golden: the host answers from the plan and starts no model,
    and the dispatcher refuses that runner under any other realization."""
    from runlib import dispatch
    if plan is None and not os.environ.get("CLAUDE_RUN_TOKEN_FILE"):
        raise Refused("TOKEN_FILE_UNSET S6: a live judgment call's token reaches claude-run only as "
                      "CLAUDE_RUN_TOKEN_FILE, and this environment does not set it")
    cells = pathlib.Path(cells)
    cells.mkdir(mode=0o700, parents=True, exist_ok=True)
    if plan is None:
        return dispatch.Supervisor(run_dir, cell_root=cells, realization="live", seats_path=seats_path)
    fake, host, plan = cells / "fake_host.py", cells / "judge_host.py", pathlib.Path(plan).resolve()
    fake.write_text(dispatch.FAKE_HOST, encoding="utf-8")
    host.write_text(JUDGE_HOST, encoding="utf-8")
    sup = dispatch.Supervisor(run_dir, cell_root=cells, realization="golden", seats_path=seats_path)
    sup.runner = lambda h, spec: [sys.executable, str(host), str(fake), h, "clean", json.dumps({**spec, "answers": str(plan)})]
    return sup


def call_row(out):
    """What S6 records of one judge's item: its outcome and codes, its attempts with what the stage's check said of
    each, whether an earlier accepted attempt answered it (`reused`), and why when it was not done."""
    from runlib import stage_read
    return {"outcome": out["outcome"], "codes": out.get("codes", []), "attempts": stage_read.attempts_of(out),
            "reused": out.get("reused"), "not_reused": out.get("not_reused", []),
            **({"why": out["why"]} if out.get("why") else {})}


def run(run_dir, supervisor=None, *, dry=False, seats_path=None, tranche="calibration"):
    """S6 over S5's population (plan WP-11): admitted against its inputs, it builds and measures every judgment packet
    (`build`); dry, it writes `judgments/dry.json` and leaves the record `partial`. Otherwise every judged candidate is
    sent to Judge A and Judge B through `supervisor`, each an item of its own, with the same payload; each answer is
    checked by the stage (`check`) and kept in the stores' ids (`judgments/<item>/<A|B>.json`), the receipts are held to
    one payload per candidate and one packet per receipt (`stage_receipts`), and `judgments/judge.json` says what each
    call did. A call that ends other than accepted leaves the record `partial`; a re-run reuses each accepted attempt
    (dispatch's resume) and calls only the rest. The calls run in a calibration tranche by default: a seat whose host
    allowance is not measured (D13: Judge B's) is dispatched only in one. `seats_path` is the dry measure's seats file;
    a run with calls reads its supervisor's. Without a supervisor and not dry, JUDGE_UNSUPERVISED."""
    from runlib import dispatch
    if not dry and supervisor is None:
        raise Refused("JUDGE_UNSUPERVISED S6: a judgment call goes through a supervisor; without one, run it dry (--dry)")
    run_dir = pathlib.Path(run_dir)
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        declaration = stage.declaration
        # the stage's lock is held, so a reservation of S6 still open is a dead run's: closed before any reuse
        interrupted = [] if dry else supervisor.interrupted(STAGE)
        summary, packets = build(run_dir, declaration, seats_path if dry else supervisor.seats_path)
        if dry:
            records.write_json(run_dir, run_dir / DRY_RECORD, summary)
            stage.output(DRY_RECORD)
            stage.record["status"] = "partial"
            return summary
        over = {who: ids for who, ids in summary["over_capacity"].items() if ids}
        if over:
            raise Refused("JUDGE_OVER_CAPACITY S6: " + "; ".join(
                f"{len(ids)} packets exceed Judge {who}'s capacity {summary['limits'][who]['capacity']} with the output "
                f"cap and a retry's correction ({ids[:3]})" for who, ids in sorted(over.items()))
                + "; the run narrows retrieval.per_layer or seats a judge with more context")
        episode = declaration["budget"]["per_episode"]
        caps = {"tokens": episode["tokens"], "compactions": episode["compactions"]}
        held_schema = schema()
        schema_bytes = packet.schema_bytes(held_schema)
        calls, receipts = [], []
        for measured in summary["packets"]:
            cid, item = measured["candidate_id"], measured["item"]
            labels, text = packets[cid]
            row = {"candidate_id": cid, "item": item, "source": measured["source"], "seats": {}}
            for who, seat in summary["seats"].items():
                limits = summary["limits"][who]
                out = supervisor.item(STAGE, f"{item}-{who}", seat, text, held_schema, case_type=CASE, caps=caps,
                                      view_window=False, tranche=tranche, max_output_tokens=OUTPUT_CAP,
                                      stage_check=check(labels, limits["capacity"]), resume=True,
                                      context_capacity=limits["capacity"],
                                      packet_check=lambda built, limits=limits, who=who: attempt_problems(
                                          built, limits, schema_bytes, who))
                held = call_row(out)
                if out["outcome"] == "accepted":
                    call_dir = pathlib.Path(out["accepted"])
                    call_id = records.read_json(call_dir / "call.json")["call_id"]
                    receipt = records.read_json(call_dir / "receipt.json")
                    rel = judgment_rel(item, who)
                    records.write_json(run_dir, run_dir / rel, {
                        "candidate_id": cid, "item": item, "judge": who, "seat": seat, "call_id": call_id,
                        "payload_sha256": measured["payload_sha256"], "packet_sha256": receipt.get("packet_sha256"),
                        "judgment": labels.resolve(gate.accepted(call_dir, judged=True))})
                    stage.output(rel)
                    receipts.append((cid, seat, call_id, receipt, measured["payload_sha256"]))
                    held.update(call_id=call_id, judgment=rel)
                row["seats"][who] = held
            calls.append(row)
        problems = stage_receipts(receipts)
        if problems:
            raise Refused("\n".join(problems))
        outcomes = [held["outcome"] for row in calls for held in row["seats"].values()]
        summary.update(dry=False, calls=calls, interrupted=interrupted, tranche=tranche,
                       counts={**{o: outcomes.count(o) for o in OUTCOMES},
                               "reused": sum(1 for row in calls for held in row["seats"].values() if held["reused"]),
                               "judged_by_both": sum(1 for row in calls
                                                     if all(h["outcome"] == "accepted" for h in row["seats"].values()))},
                       density_table=dispatch.measured_table(run_dir))
        records.write_json(run_dir, run_dir / SUMMARY, summary)
        stage.output(SUMMARY)
        if any(o != "accepted" for o in outcomes):
            stage.record["status"] = "partial"
    return summary


def report_lines(summary):
    """What the driver prints of S6: counts, sizes and codes, never a candidate's, a unit's or a quote's text."""
    pop, tot = summary["population"], summary["totals"]
    left = "; ".join(f"{s} {v['count']} of {v['of']} ({v['why']})" for s, v in pop["left_out"].items()) or "none"
    lines = [f"S6 judge{' (dry)' if summary['dry'] else ''}: declaration_seq {summary['declaration_seq']}; {pop['judged']} of {pop['candidates']} "
             f"candidates judged; {len(pop['check_failed'])} rejected by S5's checks; left out: {left}",
             f"packets: {tot['payload_bytes']} payload bytes over {len(summary['packets'])} candidates, "
             f"{tot['calls']} calls; output at most {tot['output_at_most']} tokens at the cap {summary['output_cap']}"]
    for who, lim in summary["limits"].items():
        at_most = tot["input_at_most"][who]
        lines.append(f"judge {who} ({lim['seat']}): {tot['driver_bytes'][who]} driver bytes; input at most "
                     + (f"{at_most} tokens at {lim['bytes_per_token']} bytes a token ({lim['density_basis']}); "
                        f"{len(summary['over_capacity'][who])} packets over its capacity {lim['capacity']}"
                        if at_most is not None else "not computed: " + "; ".join(c.split(":")[0] for c in lim["unmeasured"])))
    lines.append(f"budget: per_stage S6 {summary['budget']['per_stage']}")
    if not summary["dry"]:
        counts = summary["counts"]
        lines.append(f"calls ({summary['tranche']} tranche): " + ", ".join(f"{o} {counts[o]}" for o in OUTCOMES)
                     + f"; {counts['reused']} answered by an earlier accepted attempt; {counts['judged_by_both']} of "
                       f"{len(summary['calls'])} candidates judged by both")
        failed = sorted({c for row in summary["calls"] for held in row["seats"].values() if held["outcome"] != "accepted"
                         for c in held["codes"]})
        if failed:
            lines.append(f"codes of the calls not accepted: {', '.join(failed)}")
        if summary["interrupted"]:
            lines.append(f"interrupted reservations closed: {len(summary['interrupted'])}")
    return lines


# ---- the self-test --------------------------------------------------------------------------------------------

def fx_answer(units=("n1", "n2"), yes=("n1",), entries=("e1",)):
    """A schema-valid first-call answer over `units`, matching on `yes`."""
    return {"requirements": {r: {"mark": "met", "reason": "shown"} for r in REQUIREMENTS},
            "consequence_class": "quality", "no_longer_arises": {"value": False, "reason": "", "evidence_ids": []},
            "units": [{"unit": u, "situation": "yes" if u in yes else "no", "action": "yes" if u in yes else "no",
                       "reason": "one line", "quote": "Feed the zebra" if u in yes else ""} for u in units],
            "matching_units": [{"unit": u, "following": "followed", "following_evidence_ids": ["q1"],
                                "contribution": "helped", "contribution_evidence_ids": ["q1"]} for u in yes],
            "ledger_relations": [{"entry": e, "relation": "none", "reason": "unrelated"} for e in entries]}


def fx_library():
    """S5's fixture library with what S2's inventory now publishes of each unit (D-20261111-92d81a): its heading, its
    block and its edges. One unit is enclosed by a frontmatter line of its file (a reference unit S5 does not index), and
    reaches a unit of another file and an unresolved mention."""
    front = lifecycle_intake.fx_unit("u-front", "description: when a push reaches a shared remote", cls="reference",
                                     path="claude/guides/u-push.md")
    units = [dict(u) for u in lifecycle_intake.FX_LIBRARY] + [front]
    for n, unit in enumerate(units, 1):  # a path of its own, so a unit's id is never a spelling of its path
        if unit["path"] == f"claude/guides/{unit['unit_id']}.md":
            unit["path"] = f"claude/guides/guide-{n}.md"
    front["path"] = next(u["path"] for u in units if u["unit_id"] == "u-push")
    for n, unit in enumerate(units, 1):
        unit.setdefault("heading", f"Guide {n} > Rule")
        unit["block"] = "frontmatter" if unit is front else "list-item"
        unit["edges"] = {"direct": [unit["unit_id"]], "reached": []}
    push = next(u for u in units if u["unit_id"] == "u-push")
    push["edges"] = {"direct": sorted(["u-push", "u-front"]), "reached": sorted(["u-tests", "k-" + "a" * 24])}
    return units


def fx_seats(root, capacity_a=None, name="seats.json"):
    """A seats file as D13 leaves the judges' seats until their first live calls: seats.json's own, with Judge A's
    capacity and Claude's allowance measured and Judge B's host allowance and seat capacity not; `capacity_a` replaces
    Judge A's capacity."""
    held = json.loads(gate.SEATS.read_text(encoding="utf-8"))
    if capacity_a is not None:
        held["seat_capacity"]["claude:claude-opus-5-5/high"]["context_capacity"] = capacity_a
    held["hosts"]["codex"]["host_allowance"] = {"hermetic": {"allowance_tokens": None, "measured": False,
                                                             "basis": "unmeasured: D13"}}
    held["seat_capacity"].pop("codex:gpt-6-astra/xhigh", None)
    path = pathlib.Path(root) / name
    path.write_text(json.dumps(held), encoding="utf-8")
    return path


def fx_judge_answer(labels):
    """A schema-valid first-call answer to one packet, in its labels: every unit judged, the first one matching with a
    span of its text, its following and contribution shown by the packet's first quote, every ledger entry related."""
    units = list(labels.units)
    answer = fx_answer(units=tuple(units), yes=tuple(units[:1]), entries=tuple(labels.entries))
    quote = list(labels.quotes)[:1]
    for row in answer["units"]:
        if row["quote"]:
            row["quote"] = labels.unit_store[labels.units[row["unit"]]]["text"][:12]
    for row in answer["matching_units"]:
        row["following_evidence_ids"], row["contribution_evidence_ids"] = list(quote), list(quote)
    return answer


def fx_judge_plan(run_dir, path, edit=None):
    """The golden hosts' plan for S6 over a run S5 completed: one row per (candidate, judge), matched by the judge's seat
    and the candidate's whole payload, answering it (`fx_judge_answer`); `edit(candidate id, judge, row)` plants a
    defect in a row. The packets are built under an S6 admission of `run_dir`, so the plan is made on a copy of the run
    it answers. `(path, {candidate id: (labels, payload)})`."""
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        summary, packets = build(run_dir, stage.declaration)
        stage.record["status"] = "partial"
    rows = []
    for cid, (labels, text) in sorted(packets.items()):
        for who, seat in summary["seats"].items():
            row = {"match": [f"SEAT: {seat}", text], "answer": fx_judge_answer(labels)}
            if edit is not None:
                edit(cid, who, row)
            rows.append(row)
    pathlib.Path(path).write_text(json.dumps(rows), encoding="utf-8")
    return path, packets


def self_test():
    failures, ran = [], []

    def control(name, condition, detail=""):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def named(name, lines, code):
        control(name, any(line.startswith(code) for line in lines), f"expected {code} in {lines[:3]}")

    def refusal(action):
        try:
            action()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - reported by the control that reads it
            return f"RAISED {exc!r}"
        return ""

    def guarded(action, default):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - reported by the control that reads the default
            return default(exc) if callable(default) else default

    held = schema()
    # ---- done-when 8: the schema's fields are §6.2's, both ways --------------------------------------------------
    control("the judgment schema compiles under the schema policy", not refusal(lambda: validate.compile_schema(held)),
            refusal(lambda: validate.compile_schema(held)))
    control("done-when 8: the judgment schema's per-unit and per-candidate fields are §6.2's", not contract_problems(held),
            f"{contract_problems(held)}")
    dropped = json.loads(json.dumps(held))
    del dropped["$defs"]["unit_judgment"]["properties"]["quote"]
    dropped["$defs"]["unit_judgment"]["required"].remove("quote")
    named("control: a §6.2 field dropped from the schema is CONTRACT_DRIFT", contract_problems(dropped), "CONTRACT_DRIFT")
    added = json.loads(json.dumps(held))
    added["$defs"]["unit_judgment"]["properties"]["confidence"] = {"type": "string"}
    named("control: a schema field §6.2 does not name and no reason declares is CONTRACT_DRIFT",
          contract_problems(added), "CONTRACT_DRIFT")
    gone = json.loads(json.dumps(held))
    del gone["properties"]["no_longer_arises"]
    gone["required"].remove("no_longer_arises")
    named("control: a declared extra field the schema no longer holds is CONTRACT_DRIFT", contract_problems(gone),
          "CONTRACT_DRIFT stage_judge.EXTRA_FIELDS")
    control("the schema's paths are read through its references (the requirements and the units are reached)",
            {"requirements.*.mark", "units[].quote", "matching_units[].contribution"} <= set(schema_paths(held, held["$defs"])),
            f"{sorted(schema_paths(held, held['$defs']))}")
    control("D11: the schema's enum holds §7.5's six consequence classes", classes(held) == (
        "irreversible", "security", "verification-corrupting", "cost", "quality", "none"), f"{classes(held)}")
    answer = fx_answer()
    control("a first-call answer of the fixture is schema-valid",
            not validate.violations(validate.compile_schema(held), answer), f"{validate.violations(validate.compile_schema(held), answer)}")

    # ---- the reuse key -----------------------------------------------------------------------------------------
    unit = {"unit_id": "u-0000000000000001", "text": "Feed the zebra at noon.", "heading": "Zoo > Feeding",
            "layer": "catalog", "scope": None}
    base = dict(candidate={"candidate_id": "k-1", "lesson": "feed on time"}, claims=[{"claim_id": "c1"}],
                quotes=[{"evidence_id": "q1", "text": "fed late"}], unit=unit,
                trigger=[{"unit_id": "u-f", "text": "description: feeding"}], exceptions=[{"unit_id": "u-h", "text": "## Feeding"}],
                references=[{"unit_id": "u-r", "text": "The keeper's rota."}], prompt_sha256="p" * 64, schema_sha256="s" * 64,
                seat="claude:claude-opus-5-5/high")
    parts = key_components(**base)
    control("done-when 8: the reuse key's component list is §6.2's", not key_problems(tuple(parts)), f"{key_problems(tuple(parts))}")
    named("control: a component missing from the key is CONTRACT_DRIFT",
          key_problems(tuple(k for k in parts if k != "seat")), "CONTRACT_DRIFT")
    said = refusal(lambda: unit_key({**parts, "attempt": 1}))
    control("control: a key handed a component §6.2 does not name is refused by name", said.startswith("CONTRACT_DRIFT"), said)
    key = unit_key(parts)
    control("the same components give the same key", unit_key(key_components(**base)) == key)
    for name, change in (("the seat", {"seat": "codex:gpt-6-astra/xhigh"}),
                         ("one byte of the unit's text", {"unit": {**unit, "text": unit["text"][:-1] + "!"}}),
                         ("the heading path", {"unit": {**unit, "heading": "Zoo"}}),
                         ("an enclosing exception", {"exceptions": [{"unit_id": "u-h", "text": "## Feeding, except Sundays"}]}),
                         ("a referenced unit's text", {"references": [{"unit_id": "u-r", "text": "The keeper's new rota."}]}),
                         ("the candidate", {"candidate": {"candidate_id": "k-1", "lesson": "feed earlier"}}),
                         ("a quote", {"quotes": [{"evidence_id": "q1", "text": "fed later"}]}),
                         ("the prompt", {"prompt_sha256": "q" * 64})):
        control(f"D12: {name} changed gives another key", unit_key(key_components(**{**base, **change})) != key)

    # ---- one payload for both seats; one receipt per call ------------------------------------------------------
    sample = "line one\nline two\n"
    control("the same payload to both seats is no divergence", not divergence({"A": sample, "B": sample}))
    named("done-when 1 control: a seat-specific line injected into one payload is PACKET_DIVERGENCE",
          divergence({"A": sample, "B": sample + "You are Judge B.\n"}), "PACKET_DIVERGENCE")
    built = {seat: packet.build(f"r1-S6-k1-{seat}-a1", STAGE, s, sample, None)
             for seat, s in (("A", "claude:claude-opus-5-5/high"), ("B", "codex:gpt-6-astra/xhigh"))}
    hashes = {seat: (packet.sha256_bytes(b), packet.payload_sha256(b)) for seat, b in built.items()}
    control("done-when 1: the two seats' packets share the payload hash and each packet hash is its own",
            hashes["A"][1] == hashes["B"][1] and hashes["A"][0] != hashes["B"][0], f"{hashes}")

    def receipt(seat):
        return {"packet_sha256": hashes[seat][0], "evidence": {"payload_sha256": hashes[seat][1]}}

    control("the two seats' receipts of one judgment pass", not receipt_problems(
        {"c-A": ("A", receipt("A")), "c-B": ("B", receipt("B"))}))
    named("done-when 1 control: two receipts carrying one packet hash are RECEIPT_STALE",
          receipt_problems({"c-A": ("A", receipt("A")), "c-A2": ("A", receipt("A"))}), "RECEIPT_STALE")
    named("control: the seats' receipts carrying different payload hashes are PACKET_DIVERGENCE",
          receipt_problems({"c-A": ("A", receipt("A")),
                            "c-B": ("B", {**receipt("B"), "evidence": {"payload_sha256": "0" * 64}})}), "PACKET_DIVERGENCE")

    # ---- the answer against its packet -------------------------------------------------------------------------
    shown = {"units": {"n1": "Feed the zebra at noon.", "n2": "Wash the bucket."}, "quotes": ["q1"], "entries": ["e1"]}
    control("a first-call answer that judges every unit and entry passes", not answer_problems(shown, answer),
            f"{answer_problems(shown, answer)}")

    def edited(change):
        a = json.loads(json.dumps(answer))
        change(a)
        return answer_problems(shown, a)

    for name, change, code in (
            ("a unit left unjudged", lambda a: a["units"].pop(), "UNIT_UNJUDGED"),
            ("a unit judged twice", lambda a: a["units"].append(dict(a["units"][1])), "UNIT_JUDGED_TWICE"),
            ("a unit the packet does not show", lambda a: a["units"].append({**a["units"][1], "unit": "n9"}), "UNKNOWN_LABEL"),
            ("a yes without its quote", lambda a: a["units"][0].update(quote=""), "QUOTE_MISSING"),
            ("a quote where both matches are no", lambda a: a["units"][1].update(quote="Wash"), "QUOTE_UNEXPECTED"),
            ("a quote that is not a span of its unit", lambda a: a["units"][0].update(quote="Feed the lion"), "QUOTE_NOT_IN_UNIT"),
            ("a matching unit without its following and contribution", lambda a: a["matching_units"].clear(),
             "MATCHING_UNIT_MISSING"),
            ("a following given for a unit that does not match", lambda a: a["matching_units"].append(
                {**a["matching_units"][0], "unit": "n2"}), "MATCHING_UNIT_UNEXPECTED"),
            ("evidence the packet does not show", lambda a: a["matching_units"][0].update(following_evidence_ids=["q7"]),
             "UNKNOWN_LABEL"),
            ("a matching unit's following given twice", lambda a: a["matching_units"].append(dict(a["matching_units"][0])),
             "MATCHING_UNIT_TWICE"),
            ("no-longer-arises evidence the packet does not show",
             lambda a: a["no_longer_arises"].update(evidence_ids=["q8"]), "UNKNOWN_LABEL no_longer_arises"),
            ("a relation to an entry the packet does not show",
             lambda a: a["ledger_relations"].append({**a["ledger_relations"][0], "entry": "e9"}), "UNKNOWN_LABEL ledger_relations"),
            ("a ledger entry with no relation", lambda a: a["ledger_relations"].clear(), "ENTRY_UNJUDGED"),
            ("a ledger entry related twice", lambda a: a["ledger_relations"].append(dict(a["ledger_relations"][0])),
             "ENTRY_JUDGED_TWICE")):
        named(f"control: {name} is refused by name", edited(change), code)
    later = {"units": answer["units"], "matching_units": [], "ledger_relations": []}
    control("a later reference point's answer that judges its units only passes",
            not answer_problems(shown, later, first=False), f"{answer_problems(shown, later, first=False)}")
    named("control: a later call's answer that judges a ledger entry is refused (D12)",
          answer_problems(shown, {**later, "ledger_relations": answer["ledger_relations"]}, first=False), "FIELD_UNEXPECTED")

    # ---- which candidates are judged ----------------------------------------------------------------------------
    pop = ([{"candidate_id": f"k-f{n}", "source": "formed"} for n in range(3)]
           + [{"candidate_id": f"k-l{n:02d}", "source": "legacy"} for n in range(12)]
           + [{"candidate_id": "k-g0", "source": "g_cluster"}] + [{"candidate_id": f"k-r{n}", "source": "redundancy_hint"} for n in range(4)])
    every, none_left = judged_of(pop, {}, "r1")
    control("with no judged scope declared every candidate is judged and none is left out",
            every == sorted(k["candidate_id"] for k in pop) and none_left == {}, f"{none_left}")
    scoped = {"judge": {"candidate_kinds": {"formed": "all", "legacy": 3, "redundancy_hint": 0}}}
    picked, left = judged_of(pop, scoped, "r1")
    control("a declared scope judges all the formed, a sample of the legacy, and names every source it leaves out with "
            "its count and why", sum(i.startswith("k-f") for i in picked) == 3 and sum(i.startswith("k-l") for i in picked) == 3
            and not any(i.startswith(("k-g", "k-r")) for i in picked)
            and left == {"legacy": {"count": 9, "of": 12, "why": "a sample of 3 drawn from the run id"},
                         "g_cluster": {"count": 1, "of": 1, "why": "the declaration's judge.candidate_kinds leaves this source out"},
                         "redundancy_hint": {"count": 4, "of": 4, "why": "a sample of 0 drawn from the run id"}}, f"{left}")
    control("the sample is drawn from the run id: the same id draws the same, another id another",
            judged_of(pop, scoped, "r1")[0] == picked and judged_of(pop, scoped, "r2")[0] != picked)
    rows = [{"candidate_id": "k-f0", "quote_ok": False, "quote_problems": ["QUOTE_MISMATCH q-1"], "session_problems": []},
            {"candidate_id": "k-f1", "quote_ok": True, "quote_problems": [], "session_problems": ["SESSION_UNKNOWN s-9"]},
            {"candidate_id": "k-f2", "quote_ok": None, "quote_problems": [], "session_problems": []}]
    failed = check_failures(rows)
    control("S5's check failures are named with their codes and not judged",
            failed == {"k-f0": ["QUOTE_MISMATCH"], "k-f1": ["SESSION_UNKNOWN"]}
            and judged_of(pop, {}, "r1", failed)[0] == sorted(set(every) - {"k-f0", "k-f1"}), f"{failed}")
    said = refusal(lambda: judged_of(pop + [{"candidate_id": "k-x", "source": "planted"}], {}, "r1"))
    control("control: a source the judged scope has no key for is refused by name", said.startswith("SOURCE_UNDECLARED"), said)

    # ---- the packet and the dry stage over a golden run through S5 ------------------------------------------------
    control("the judge template is one packet.TEMPLATES lists, and its placeholders are the five blocks",
            TEMPLATE in packet.TEMPLATES and guarded(lambda: packet.template_fields(TEMPLATE), []) == sorted(BLOCKS),
            f"{packet.TEMPLATES}")
    form_text, judge_text = (guarded(lambda name=n: packet.template_text(name), "") for n in ("form", TEMPLATE))
    definitions = [line for line in form_text.splitlines() if re.match(r"^(\d\. `|   \S)", line)]
    control("the eight requirements are defined in the judge template exactly as the formation template defines them",
            definitions and "\n".join(definitions) in judge_text and len([d for d in definitions if re.match(r"^\d\. ", d)]) == 8,
            f"{len(definitions)} definition lines")
    control("the eight requirements of the template are the schema's", all(f"`{r}`" in judge_text for r in REQUIREMENTS))
    control("the judged scope's keys in run.json's schema are S5's sources", sorted(json.loads(
        (HERE / "schemas" / "run.schema.json").read_text(encoding="utf-8"))["properties"]["judge"]["properties"]
        ["candidate_kinds"]["properties"]) == sorted(SOURCES), f"{SOURCES}")
    said = refusal(lambda: seats_of({"seats": {"S6.A": "claude:claude-opus-5-5/high"}}))
    control("control: a declaration without Judge B's seat is SEAT_UNDECLARED", said.startswith("SEAT_UNDECLARED"), said)
    root = pathlib.Path(tempfile.mkdtemp(prefix="s6-"))
    try:
        seats_file = fx_seats(root)
        base = guarded(lambda: stage_retrieve.fx_gold(root / "base", stage_retrieve.fx_current(fx_library())), lambda e: e)
        if isinstance(base, Exception):
            failures.append(f"the golden run through S4 could not be made: {base!r}")
            base = None

        def copy_of(label, through_s5=True):
            where = root / f"c-{label}"
            shutil.copytree(base.parent, where)
            run_dir = where / base.name
            if through_s5:
                stage_retrieve.run(run_dir, "aa" * 8)
            return run_dir

        if base is not None:
            gold = copy_of("gold")
            made = guarded(lambda: run(gold, dry=True, seats_path=seats_file), lambda e: {"problem": repr(e)})
            record = guarded(lambda: records.read_json(records.record_path(gold, STAGE)), {})
            dry = guarded(lambda: records.read_json(gold / DRY_RECORD), {})
            control("golden: S6 dry over S5's population records its dry measure and stays partial",
                    record.get("status") == "partial" and [o["artifact"] for o in record.get("outputs", [])] == [DRY_RECORD]
                    and dry.get("dry") is True, f"{made}")
            checks = guarded(lambda: records.read_json(gold / "checks.json"), {"candidates": []})
            population = guarded(lambda: records.read_json(gold / "checked-candidates.json"), {"candidates": []})
            planted = guarded(lambda: records.read_json(gold / controls.CONTROLS_FILE), {"planted": []})
            failed_ids = {r["candidate_id"] for r in checks["candidates"] if r["quote_ok"] is False or r["session_problems"]}
            pop = dry.get("population", {})
            control("golden: every candidate S5's checks passed is judged; S5's failures - the altered quote and the "
                    "fabricated session among them - are rejected by check failure, by name; none is left out",
                    pop.get("judged") == len(population["candidates"]) - len(failed_ids) and len(failed_ids) >= 2
                    and set(pop.get("check_failed", {})) == failed_ids and pop.get("left_out") == {}
                    and {r["candidate_id"] for r in dry.get("packets", [])} == {k["candidate_id"] for k in population["candidates"]} - failed_ids,
                    f"{pop}")
            control("golden: Judge A's input is measured; Judge B's is not, its unmeasured allowance and capacity named (D13)",
                    all(isinstance(r["input_at_most"]["A"], int) and r["input_at_most"]["B"] is None for r in dry.get("packets", []))
                    and [c.split()[0] for c in dry.get("limits", {}).get("B", {}).get("unmeasured", [])]
                    == ["ALLOWANCE_UNMEASURED", "CAPACITY_UNDECLARED"] and dry.get("output_cap") == OUTPUT_CAP,
                    f"{dry.get('limits')}")
            lines = guarded(lambda: report_lines(made), [])
            control("golden: the report says what was judged, measured and not measured, in counts and codes",
                    any("candidates judged" in l for l in lines) and any("not computed: ALLOWANCE_UNMEASURED" in l for l in lines),
                    f"{lines}")
            # the packets themselves, built again as the stage builds them, under a stage admission of a copy
            again = copy_of("again")
            with records.run_stage(again, STAGE, INPUTS) as stage:
                again_summary, packets = guarded(lambda: build(again, stage.declaration, seats_file), lambda e: (repr(e), {}))
            built = dict(packets)
            control("golden: building again gives the packets dry.json measured, candidate by candidate",
                    isinstance(again_summary, dict) and [r["payload_sha256"] for r in again_summary["packets"]]
                    == [r["payload_sha256"] for r in dry.get("packets", [])], f"{again_summary if isinstance(again_summary, str) else ''}")
            by_id = {k["candidate_id"]: k for k in population["candidates"]}
            rows_of = {r["candidate_id"]: r for r in checks["candidates"]}
            units = {u["unit_id"]: u for u in records.read_json(gold / "inventory" / "current.json")["units"]}
            control("golden: each packet's payload is the one dry.json measured",
                    all(r["payload_sha256"] == packet.sha256_bytes(built[r["candidate_id"]][1].encode("utf-8"))
                        for r in dry.get("packets", []) if r["candidate_id"] in built) and built)
            leaked = sorted({cid for cid, (labels, text) in built.items()
                             for stored in labels.label_of if len(stored) > 6 and stored in text})
            control("golden: no stored id reaches a packet - every unit, entry, claim, quote, event and session is a label",
                    not leaked, f"{leaked[:3]}")
            push = next(((labels, text) for labels, text in built.values() if "u-push" in labels.units.values()), None)
            if push is None:
                failures.append("golden: no candidate retrieved u-push, the unit the fixture encloses and has mention others")
            else:
                labels, text = push
                _frame, blocks = blocks_of(text)
                # looked up by label without assuming one: a packet that shows a stored id fails a control, not the suite
                row = next((r for r in blocks["units"] if labels.units.get(r["unit_id"]) == "u-push"), {})
                context = {r["context_id"]: r for r in blocks["context"]}
                control("golden (a1_min): a unit's enclosing line is shown whole in <context> under its label, and the "
                        "file it mentions by its heading and count, its unresolved mention counted",
                        [labels.context.get(x) for x in row.get("context", [])] == ["u-front"]
                        and context.get(row["context"][0], {}).get("block") == "frontmatter"
                        and row.get("mentions") == [{"path": units["u-tests"]["path"], "headings": [units["u-tests"]["heading"]],
                                                     "units": 1}]
                        and row.get("unresolved_mentions") == 1, f"{row} {context}")
                control("golden: every unit S5 retrieved is in <units> once, in S5's order, and every entry in "
                        "<ledger_entries> once", [labels.units.get(r["unit_id"]) for r in blocks["units"]]
                        == [r["unit_id"] for r in labels.unit_rows]
                        and [labels.entries.get(r["entry_id"]) for r in blocks["entries"]] == [r["entry_id"] for r in labels.entry_rows])
                answer = {**fx_answer(units=tuple(labels.units), yes=(), entries=tuple(labels.entries)),
                          "matching_units": []}
                control("golden: an answer that judges the packet's own units and entries passes answer_problems",
                        not answer_problems(labels.shown(), answer), f"{answer_problems(labels.shown(), answer)[:3]}")
            shown_quotes, cited_quotes, with_cited = {}, {}, 0
            for cid, (labels, text) in built.items():
                _frame, blocks = blocks_of(text)
                cand = blocks["candidate"][0] if blocks["candidate"] else {}
                shown_quotes[cid] = ({q["evidence_id"] for c in blocks["claims"] for q in c["quotes"]}
                                     | {o.get("evidence_id") for ev in cand.get("events", []) for o in ev.get("origin", [])}
                                     | {q["evidence_id"] for q in cand.get("quotes", [])})
                cited_quotes[cid] = {q for req in (cand.get("admission") or {}).values() for q in req.get("evidence_ids") or []}
                with_cited += bool(cand.get("quotes"))
            control("golden: every quote a candidate's admission cites is shown with its text in the packet, one beyond "
                    "its claims and its own events among them", with_cited > 0
                    and all(cited_quotes[c] <= shown_quotes[c] for c in built), f"{with_cited}")
            beyond = next((labels for labels, _t in built.values() if labels.cited), None)
            if beyond is not None:
                said = refusal(lambda: JudgeLabels(beyond.candidate, rows_of[beyond.candidate["candidate_id"]],
                                                   beyond.unit_store, beyond.entry_store, stage_form.subject(gold), {}))
                control("control: a cited quote no evidence record holds is RECORD_INTEGRITY", said.startswith(
                    "RECORD_INTEGRITY") and "no evidence record holds" in said, said[:200])
            mismatch = copy_of("mismatch")
            with records.run_stage(mismatch, STAGE, INPUTS) as stage:
                where = mismatch / "checked-candidates.json"
                held_pop = records.read_json(where)
                held_pop["candidates"] = held_pop["candidates"][1:]
                where.chmod(0o600)
                where.write_text(json.dumps(held_pop), encoding="utf-8")
                said = refusal(lambda: build(mismatch, stage.declaration, seats_file))
                stage.record["status"] = "partial"
            control("control: checks.json and the population naming different candidates is SET_MISMATCH",
                    said.startswith("SET_MISMATCH S6"), said[:200])
            narrow_seats = fx_seats(root, capacity_a=1000, name="narrow-seats.json")
            tight = copy_of("tight")
            with records.run_stage(tight, STAGE, INPUTS) as stage:
                tight_summary, _p = guarded(lambda: build(tight, stage.declaration, narrow_seats), lambda e: ({"problem": repr(e)}, {}))
                stage.record["status"] = "partial"
            control("golden: a seat whose capacity a packet exceeds lists that packet by name (over_capacity)",
                    sorted((tight_summary.get("over_capacity") or {}).get("A", [])) == sorted(built) and built
                    and (tight_summary.get("over_capacity") or {}).get("B") == [], f"{tight_summary.get('over_capacity', tight_summary)}")
            # F27: a control's packet has a natural one's frame, blocks, rows and fields
            judged_controls = [e for e in planted["planted"] if "S6" in e["checked_at"] and e["candidate_id"] in built]
            pairs = []
            for entry in judged_controls:
                mine = by_id[entry["candidate_id"]]
                twin = next((k for k in population["candidates"] if k["candidate_id"] in built and k["candidate_id"] not in
                             {e["candidate_id"] for e in planted["planted"]} and k.get("event_ids") == mine.get("event_ids")), None)
                if twin is not None:
                    pairs.append((entry["kind"], packet_markers(built[entry["candidate_id"]][1], built[twin["candidate_id"]][1])))
            control("F27: every judged control's packet has its natural twin's frame, blocks, rows and fields",
                    len(pairs) == len(judged_controls) >= 4 and not any(problems for _k, problems in pairs), f"{pairs}")
            if built:
                some = next(iter(built.values()))[1]
                marked = some.replace('"named": ', '"planted": true, "named": ', 1)
                control("control: a field planted in one row of a packet is MARKER_FIELD", any(
                    p.startswith("MARKER_FIELD") for p in packet_markers(marked, some)), "")
                control("control: a line added outside the blocks is FRAME_DIFFERS",
                        packet_markers(some.replace("# Your task", "# Your task (a control)"), some) ==
                        ["FRAME_DIFFERS: the text outside the blocks is not the natural packet's"])
            # a declared scope, through the declaration
            from runlib import declare
            scoped = copy_of("scoped", through_s5=False)
            declare.amend(scoped, [("judge", {"candidate_kinds": {"formed": "all"}})], "judge the formed candidates only (WP-11)",
                          scope=["S5", "S6"])
            stage_retrieve.run(scoped, "aa" * 8)
            narrowed = guarded(lambda: run(scoped, dry=True, seats_path=seats_file), lambda e: {"problem": repr(e)})
            lifecycle = {k["source"] for k in population["candidates"] if k["source"] != "formed"}
            control("golden: a declared scope judges what it names and reports every source it leaves out by count",
                    set(narrowed.get("population", {}).get("left_out", {})) == lifecycle and lifecycle
                    and all(r["source"] == "formed" for r in narrowed.get("packets", [])), f"{narrowed.get('population', narrowed)}")
            # what is refused, by name, with nothing written
            # an inventory as S2 published one before the edges: a golden of its own, S4 run over it
            plain = stage_retrieve.fx_current([{k: v for k, v in u.items() if k != "edges"} for u in fx_library()])
            bare = guarded(lambda: stage_retrieve.fx_gold(root / "bare", plain), lambda e: e)
            said = refusal(lambda: (stage_retrieve.run(bare, "aa" * 8), run(bare, dry=True, seats_path=seats_file))) \
                if not isinstance(bare, Exception) else repr(bare)
            control("control: an inventory without per-unit edges is EDGES_ABSENT, and no dry measure is written",
                    said.startswith("EDGES_ABSENT") and not (pathlib.Path(str(bare)) / DRY_RECORD).exists(), said[:200])
            unrun = copy_of("no-s5", through_s5=False)
            said = refusal(lambda: run(unrun, dry=True, seats_path=seats_file))
            control("control: S6 over a run S5 has not run is refused by name (INPUT_INVALID S5)", "INPUT_INVALID S5" in said, said[:200])
            said = refusal(lambda: run(unrun))
            control("control: S6 with neither --dry nor a supervisor is JUDGE_UNSUPERVISED, before anything is recorded",
                    said.startswith("JUDGE_UNSUPERVISED") and not records.record_path(unrun, STAGE).exists(), said)

            # ---- the calls (J2a): a golden run of both judges through the golden hosts --------------------------------
            from runlib import declare
            called = copy_of("called", through_s5=False)
            declare.amend(called, [("budget.per_stage.S6", 20_000_000)], "S6's golden budget (WP-11 J2)", scope=["S5", "S6"])
            stage_retrieve.run(called, "aa" * 8)
            planner = root / "planner"
            shutil.copytree(called.parent, planner)
            replayed = records.fixture_root("replay") / "claude-runner" / "ctl-cfg-claude-md-001" / "host.json"
            clean_plan, packets = fx_judge_plan(planner / called.name, root / "plan-clean.json")
            judged_ids = sorted(packets)
            tainted, unjudged = judged_ids[0], judged_ids[-1]

            def defects(cid, who, row):
                if cid == tainted and who == "A":   # WP-03's planted user CLAUDE.md, loaded beside a schema-valid answer
                    row["context"] = str(replayed)
                if cid == unjudged and who == "B":  # an answer that leaves one unit unjudged, on both attempts
                    row["answer"]["units"] = row["answer"]["units"][1:]
            defect_plan, _p = fx_judge_plan(planner / called.name, root / "plan-defects.json", defects)
            first = guarded(lambda: run(called, supervisor(called, root / "cells-1", defect_plan)), lambda e: {"problem": repr(e)})
            record = guarded(lambda: records.read_json(records.record_path(called, STAGE)), {})
            rows = {r["candidate_id"]: r for r in first.get("calls", [])}
            seated = lambda cid, who: (rows.get(cid) or {}).get("seats", {}).get(who, {})
            control("golden (J2): every judged candidate goes to both judges, each an item of its own, and the calls that "
                    "end other than accepted leave the record partial", set(rows) == set(judged_ids) and len(judged_ids) >= 6
                    and first.get("counts", {}).get("accepted") == 2 * len(judged_ids) - 2 and record.get("status") == "partial",
                    f"{first.get('counts', first)}")
            taint = seated(tainted, "A")
            control("golden (J2, done-when 5): a judgment call whose capture shows an undeclared instruction loaded is "
                    "failed, though its answer is schema-valid and the stage's check was never asked",
                    taint.get("outcome") == "failed" and "CONTEXT_UNDECLARED" in taint.get("codes", [])
                    and all(a["stage_check"] is None for a in taint.get("attempts", [])) and taint.get("attempts")
                    and not (called / judgment_rel(item_of(tainted), "A")).exists(), f"{taint}")
            short = seated(unjudged, "B")
            control("golden (J2): an answer that leaves a unit unjudged fails the stage's check on both attempts, by name",
                    short.get("outcome") == "failed" and len(short.get("attempts", [])) == 2
                    and all(any(line.startswith("UNIT_UNJUDGED") for line in a["stage_check"] or [])
                            for a in short.get("attempts", [])), f"{short}")
            made = {d.name for d in (called / "calls").iterdir()} if (called / "calls").is_dir() else set()
            second = guarded(lambda: run(called, supervisor(called, root / "cells-2", clean_plan)), lambda e: {"problem": repr(e)})
            record = guarded(lambda: records.read_json(records.record_path(called, STAGE)), {})
            remade = {d.name for d in (called / "calls").iterdir()} - made if (called / "calls").is_dir() else set()
            control("golden (J2): run again, S6 reuses every accepted attempt and calls only the two items that were not "
                    "accepted; the record is complete", record.get("status") == "complete"
                    and second.get("counts", {}).get("reused") == 2 * len(judged_ids) - 2
                    and second.get("counts", {}).get("judged_by_both") == len(judged_ids)
                    and sorted(n.rsplit("-a", 1)[0].split(f"-{STAGE}-", 1)[1] for n in remade)
                    == sorted([item_of(tainted) + "-A", item_of(unjudged) + "-B"]), f"{second.get('counts', second)} {sorted(remade)}")
            kept = {(cid, who): guarded(lambda c=cid, w=who: records.read_json(called / judgment_rel(item_of(c), w)), {})
                    for cid in judged_ids for who in ("A", "B")}
            control("golden (J2, N#1): both judges of a candidate were sent its one payload - the payload hash S6 built, "
                    "equal in both judgments - and every call's packet hash is its own",
                    all(kept[(c, "A")].get("payload_sha256") == kept[(c, "B")].get("payload_sha256")
                        == packet.sha256_bytes(packets[c][1].encode("utf-8")) for c in judged_ids)
                    and len({k.get("packet_sha256") for k in kept.values()}) == len(kept), "")
            shown_cid = next((c for c in judged_ids if packets[c][0].units and packets[c][0].quotes and packets[c][0].entries),
                             judged_ids[1])
            labels0 = packets[shown_cid][0]
            judgment = kept[(shown_cid, "A")].get("judgment", {})
            control("golden (J2): a judgment is kept in the stores' ids - its units in S5's order by unit id, its quotes "
                    "by evidence id, its ledger relations by entry id",
                    [u["unit_id"] for u in judgment.get("units", [])] == [r["unit_id"] for r in labels0.unit_rows]
                    and [r["entry_id"] for r in judgment.get("ledger_relations", [])] == [r["entry_id"] for r in labels0.entry_rows]
                    and all(q in labels0.quotes.values() for m in judgment.get("matching_units", [])
                            for q in m["following_evidence_ids"]) and judgment.get("matching_units"),
                    f"{[u['unit_id'] for u in judgment.get('units', [])]} {[r['unit_id'] for r in labels0.unit_rows]} "
                    f"{[r['entry_id'] for r in judgment.get('ledger_relations', [])]} {[r['entry_id'] for r in labels0.entry_rows]} "
                    f"{judgment.get('matching_units')} {list(labels0.quotes.values())[:3]}")
            lines = guarded(lambda: report_lines(second), [])
            control("golden (J2): the report says what the calls did, in counts and codes",
                    any(l.startswith("calls (calibration tranche): accepted") for l in lines), f"{lines}")
            # the receipts, planted on copies of the accepted calls' own
            held = []
            for cid in judged_ids[:2]:
                for who in ("A", "B"):
                    k = kept[(cid, who)]
                    held.append((cid, k.get("seat"), k.get("call_id"),
                                 guarded(lambda c=k.get("call_id"): records.read_json(called / "calls" / c / "receipt.json"), {}),
                                 packet.sha256_bytes(packets[cid][1].encode("utf-8"))))
            held = [h for h in held if h[2]]
            if len(held) < 4:  # the calls these controls copy were not all accepted: named, and the copies not made
                failures.append(f"golden (J2): the receipt controls need four accepted calls, and {len(held)} were")
                held = [("k", "s", f"c{n}", {}, "") for n in range(4)]
            control("the accepted calls' receipts pass", not guarded(lambda: stage_receipts(held), ["RAISED"]),
                    f"{guarded(lambda: stage_receipts(held), ['RAISED'])}")
            stale = [*held[:3], (held[3][0], held[3][1], held[3][2], {**held[3][3], "packet_sha256": held[2][3].get("packet_sha256")},
                                 held[3][4])]
            control("control: two receipts carrying one packet hash is RECEIPT_STALE",
                    any(p.startswith("RECEIPT_STALE") for p in stage_receipts(stale)), f"{stage_receipts(stale)}")
            moved = [*held[:3], (held[3][0], held[3][1], held[3][2],
                                 {**held[3][3], "evidence": {**(held[3][3].get("evidence") or {}), "payload_sha256": "f" * 64}},
                                 held[3][4])]
            control("control: a receipt whose payload hash is not the payload S6 built is PACKET_DIVERGENCE",
                    sum(p.startswith("PACKET_DIVERGENCE") for p in stage_receipts(moved)) == 2, f"{stage_receipts(moved)}")
            # refused before anything is sent
            tight = copy_of("tight-called", through_s5=False)
            declare.amend(tight, [("budget.per_stage.S6", 20_000_000)], "S6's golden budget (WP-11 J2)", scope=["S5", "S6"])
            stage_retrieve.run(tight, "aa" * 8)
            said = refusal(lambda: run(tight, supervisor(tight, root / "cells-3", clean_plan, seats_path=narrow_seats)))
            control("control: a packet over a judge's capacity is JUDGE_OVER_CAPACITY S6 before any call is reserved",
                    said.startswith("JUDGE_OVER_CAPACITY S6")
                    and not any(f"-{STAGE}-" in d.name for d in (tight / "calls").iterdir()), said[:200])
            limits_a = second.get("limits", {}).get("A", {})
            some_call = kept[(judged_ids[0], "A")].get("call_id", "")
            sent = guarded(lambda: (called / "calls" / some_call / "packet.md").read_bytes(), b"")
            held_schema_bytes = packet.schema_bytes(schema())
            control("an accepted attempt's own packet is within Judge A's capacity",
                    bool(sent) and not attempt_problems(sent, limits_a, held_schema_bytes, "A"), "")
            control("control: an attempt's packet past the seat's capacity is JUDGE_OVER_CAPACITY by the attempt's bound",
                    any(p.startswith("JUDGE_OVER_CAPACITY A") for p in attempt_problems(
                        sent, {**limits_a, "capacity": 1000}, held_schema_bytes, "A")), "")
            moved_dir = root / "capacity-moved"
            shutil.copytree(called / "calls" / some_call, moved_dir)
            call_record = records.read_json(moved_dir / "call.json")
            call_record["bound"]["context_capacity"] = 999
            (moved_dir / "call.json").chmod(0o600)
            (moved_dir / "call.json").write_text(json.dumps(call_record), encoding="utf-8")
            said = refusal(lambda: check(packets[judged_ids[0]][0], limits_a.get("capacity"))(moved_dir))
            control("control: an attempt whose call record carries another capacity than S6 was admitted against is "
                    "CAPACITY_UNRECORDED", said.startswith("CAPACITY_UNRECORDED"), said[:200])
            # ---- done-when 4's decidable halves (J2b deferred, D-20261111-c4fa71) -------------------------------------
            # no cross-run reuse: the same inputs under another run id, an earlier run's judgments and reuse map in it
            nxt_root = root / "next"
            shutil.copytree(planner, nxt_root)
            nxt = nxt_root / f"{called.name}-next"
            (nxt_root / called.name).rename(nxt)
            shutil.copytree(called / "judgments", nxt / "judgments")
            earlier_map = nxt / "judgments" / "reuse.json"
            earlier_map.write_text(json.dumps({sha256_json([c, w]): judgment_rel(item_of(c), w) for c in judged_ids
                                               for w in ("A", "B")}), encoding="utf-8")
            planted_bytes = earlier_map.read_bytes()
            fresh = guarded(lambda: run(nxt, supervisor(nxt, root / "cells-5", clean_plan)), lambda e: {"problem": repr(e)})
            fresh_calls = sorted(d.name for d in (nxt / "calls").iterdir() if d.name.startswith(f"{nxt.name}-{STAGE}-"))
            control("done-when 4: a new run with the same inputs makes a fresh call for every judgment - an earlier run's "
                    "judgments and reuse map in its directory are ignored, and the map is left as it was",
                    fresh.get("counts", {}).get("reused") == 0 and fresh.get("counts", {}).get("accepted") == 2 * len(judged_ids)
                    and len(fresh_calls) == 2 * len(judged_ids) and earlier_map.read_bytes() == planted_bytes,
                    f"{fresh.get('counts', fresh)} {len(fresh_calls)}")
            # A's judgment never answers B: every A accepted and no B, then both
            only_a = copy_of("only-a", through_s5=False)
            declare.amend(only_a, [("budget.per_stage.S6", 20_000_000), ("judge", {"candidate_kinds": {"formed": "all"}})],
                          "S6's golden budget, the formed candidates only (WP-11 J2)", scope=["S5", "S6"])
            stage_retrieve.run(only_a, "aa" * 8)
            a_plan = root / "plan-a-only.json"
            seat_a = f"SEAT: {fresh.get('seats', {}).get('A')}"
            a_plan.write_text(json.dumps([r for r in json.loads(pathlib.Path(clean_plan).read_text(encoding="utf-8"))
                                          if r["match"][0] == seat_a]), encoding="utf-8")
            one = guarded(lambda: run(only_a, supervisor(only_a, root / "cells-6", a_plan)), lambda e: {"problem": repr(e)})
            two = guarded(lambda: run(only_a, supervisor(only_a, root / "cells-7", clean_plan)), lambda e: {"problem": repr(e)})
            a_rows, b_rows = ([row["seats"].get(w, {}) for row in got.get("calls", [])] for got, w in ((one, "A"), (two, "B")))
            control("done-when 4: A's accepted judgment never answers B - with every A accepted and no B, the next run calls "
                    "every B anew, and no B considers an attempt of A's",
                    a_rows and all(h.get("outcome") == "accepted" for h in a_rows)
                    and all(h.get("outcome") == "failed" for row in one.get("calls", []) for h in [row["seats"].get("B", {})])
                    and two.get("counts", {}).get("reused") == len(a_rows)
                    and all(h.get("outcome") == "accepted" and not h.get("reused")
                            and all("-B-a" in reason.split()[1] for reason in h.get("not_reused", [])) for h in b_rows),
                    f"{one.get('counts', one)} {two.get('counts', two)}")
            token = os.environ.pop("CLAUDE_RUN_TOKEN_FILE", None)
            try:
                said = refusal(lambda: supervisor(tight, root / "cells-4"))
            finally:
                if token is not None:
                    os.environ["CLAUDE_RUN_TOKEN_FILE"] = token
            control("control: a live supervisor without CLAUDE_RUN_TOKEN_FILE is TOKEN_FILE_UNSET", said.startswith(
                "TOKEN_FILE_UNSET S6"), said)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for failure in failures:
        print(f"stage_judge --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stage_judge --self-test: OK ({len(ran)} controls: done-when 8's two halves - the judgment schema's fields "
          "against §6.2's both ways and the reuse key's components against §6.2's, each with a planted drift; D12's key "
          "per candidate, unit and seat, changed by each component; done-when 1's one payload and one receipt per call "
          "with PACKET_DIVERGENCE and RECEIPT_STALE planted; D14's quotes and every unit, matching unit and ledger entry "
          "judged once, each refusal planted; D11's classes from the schema's enum; the judged scope and S5's check "
          "failures; the packet (a1_min) and the dry stage over a golden run through S5 - labels only, the enclosing line "
          "whole and the mentioned file by heading and count, F27's packet check with its planted field and frame, "
          "EDGES_ABSENT, JUDGE_UNSUPERVISED and INPUT_INVALID S5; the calls (J2) through the golden hosts - both judges per "
          "candidate, done-when 5's replayed undeclared instruction failed, a unit left unjudged failed by name, the "
          "re-run reusing every accepted attempt, one payload and one packet per receipt with RECEIPT_STALE and "
          "PACKET_DIVERGENCE planted, JUDGE_OVER_CAPACITY and TOKEN_FILE_UNSET; done-when 4's decidable halves - no "
          "reuse across runs, and A's judgment never answering B)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    print("usage: stage_judge.py --self-test (the stage runs as `distill.py judge --run-id ID`)", file=sys.stderr)
    sys.exit(2)
