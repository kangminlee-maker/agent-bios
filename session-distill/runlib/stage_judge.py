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

The absence sweeps (plan WP-11 J3a, design §6.2, done-when 6) follow the judgments in the same run. At a reference
point the absence policy reads as incomplete every absence is `unknown` and nothing is swept. Otherwise every judged
candidate no unit matches by both judges (`absent_candidates`) has its remaining units - the units S5 indexes less the
ones retrieved for it - cut into shards, several candidates to a group (`shard_plan`, `shard_problems`, run.json's
`sweeps`), each shard sent to the Claude-side and the OpenAI-side sweep with one payload bound to the inventory's hash,
and each answer held to exactly the pairs its packet lists (`sweep_problems`). `--dry` reports the sweep's upper bound:
every judged candidate as a gap over the catalog layer (`upper_bound`).

Judge B then reviews every absence claim the sweeps judged whole (plan WP-11 J3b, done-when 3, F10): its packet
carries every unit either sweep flagged and fifty units both found unrelated, drawn from the run id, each with both
sweeps' marks and reasons (`cross_stage`); the kept review is held to what the sweep results build
(`cross_review_problems`: CROSS_REVIEW_INCOMPLETE, CROSS_REVIEW_STALE). Every unit either sweep flagged or Judge B
marked a match returns to both judges in one judgment packet (plan WP-11 J3c, `reconsider_stage`); the claim is then
diagnosed again by derive, a disagreement making it disputed, and a judge's missing reconsideration is
RECONSIDERATION_MISSING.

  stage_judge.py --self-test
"""
import collections
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, controls, derive, gate, lifecycle_intake, packet, records, stage_form, stage_retrieve, validate  # noqa: E402
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

def answer_problems(shown, answer, first=True, reconsider=False):
    """What a schema-valid answer gets wrong against the packet it answered, each by name. `shown` is
    `{units: {label: text}, quotes: [labels], entries: [labels]}`; `first` is the candidate's first call, which also
    judges its requirements, class, matching units and ledger relations (D12), while a later reference point's call
    judges its units only. `reconsider` is a reconsideration (J3c), which judges its returned units and their matching
    units and no candidate-level field (FIELD_UNEXPECTED)."""
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
    if reconsider:
        out += [f"FIELD_UNEXPECTED {field}: a reconsideration judges its returned units only (design §6.2)"
                for field in RECONSIDER_REFUSED if field in answer]
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
        self.subject_of, self.evidence_store = subject_of, evidence   # what `returned_labels` builds from
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
        held = {} if "requirements" not in answer else {   # a reconsideration carries its units only (J3c)
            "requirements": answer["requirements"], "consequence_class": answer["consequence_class"],
            "no_longer_arises": {**later, "evidence_ids": quoted(later.get("evidence_ids") or [])}}
        return {**held,
                "units": [{"unit_id": self.units[r["unit"]], **{k: r[k] for k in ("situation", "action", "reason", "quote")}}
                          for r in answer["units"]],
                "matching_units": [{"unit_id": self.units[r["unit"]], "following": r["following"],
                                    "following_evidence_ids": quoted(r["following_evidence_ids"]),
                                    "contribution": r["contribution"],
                                    "contribution_evidence_ids": quoted(r["contribution_evidence_ids"])}
                                   for r in answer["matching_units"]],
                **({} if "ledger_relations" not in answer else {"ledger_relations": [
                    {"entry_id": self.entries[r["entry"]], "relation": r["relation"], "reason": r["reason"]}
                    for r in answer["ledger_relations"]]})}


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


def limits_of(seat, run_dir, declaration, seats_path=None, case=CASE, output_cap=OUTPUT_CAP):
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
    density = dispatch.measured_density(run_dir, seat, STAGE, case, (declaration or {}).get("density"))
    retry = dispatch.retry_share(run_dir, host, (declaration or {}).get("retry"))
    unmeasured = ([] if isinstance(allowance, int) else
                  [f"ALLOWANCE_UNMEASURED {seat}: seats.json holds no measured hermetic allowance for {host}"]) \
        + ([] if capacity is not None else [f"CAPACITY_UNDECLARED {seat}: {basis}"])
    return {"seat": seat, "capacity": capacity, "capacity_basis": basis, "allowance": allowance,
            "bytes_per_token": density["bytes_per_token"], "density_basis": density["basis"],
            "retry_margin": retry["margin"], "retries": retry["count"], "output_cap": output_cap, "unmeasured": unmeasured}


def at_most_of(size, limits):
    """Input tokens at most of a judgment call of `size` driver bytes under `limits` (`dispatch.input_at_most`), or None
    for a seat whose allowance or capacity is not measured."""
    from runlib import dispatch
    if limits["unmeasured"]:
        return None
    return dispatch.input_at_most(size, {"bytes_per_token": limits["bytes_per_token"]}, limits["allowance"],
                                  limits["output_cap"], limits["retry_margin"], limits["retries"])[1]


def beyond_capacity(size, limits):
    """Whether a call of `size` driver bytes, with room for its one retry's correction (S4's rule, stage_read's
    CORRECTION_ROOM) and the output cap, exceeds the seat's capacity; None when it cannot be told."""
    from runlib import stage_read
    at_most = at_most_of(size + stage_read.CORRECTION_ROOM, limits)
    return None if at_most is None else at_most + limits["output_cap"] > limits["capacity"]


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


# ---- the absence sweeps (plan WP-11 J3a, design §6.2) ----------------------------------------------------------

SWEEP_TEMPLATE = "sweep"
SWEEP_SCHEMA_PATH = HERE / "schemas" / "sweep.schema.json"
SWEEP_CASE = "sweep"   # a sweep call's class (dispatch.class_key)
SWEEP_SEAT_KEYS = {"a": "S6.sweep_a", "b": "S6.sweep_b"}   # lead decision E1: the Claude side and the OpenAI side
SWEEP_DEFAULTS = {"shard_units": 100, "candidates_per_shard": 5, "output_cap": 20_000}   # lead decision E2
# the density the dry upper bound reports tokens at: S4's declared one, at which J0 measured C2's packets (lead, J2a)
J0_DENSITY = 2.27
J0_DENSITY_BASIS = "S4's declared density, at which J0 measured C2's judgment packets (2026-11-11)"
UPPER_BOUND_LAYER = "catalog"   # lead, on J2a: the bound's remaining units are the catalog layer's
UPPER_BOUND_BASIS = ("every judged candidate taken as a gap, its remaining units the catalog layer's indexed units less "
                     "the ones S5 retrieved for it: a bound, not a count of gap candidates, which exist only after judging")
# what a lifecycle candidate's record names by id, shown to a sweep by the named texts instead (`sweep_view`)
LIFECYCLE_NAMED = ("candidate_id", "source", "target_entry", "entries", "target_unit", "target_units", "members")


def sweep_schema():
    return json.loads(SWEEP_SCHEMA_PATH.read_text(encoding="utf-8"))


def sweeps_of(declaration):
    """`(sizes, basis)`: the sweep sizes run.json declares (`sweeps.shard_units`, `candidates_per_shard`, `output_cap`),
    each absent one S6's own (SWEEP_DEFAULTS), and which each came from."""
    held = (declaration or {}).get("sweeps") or {}
    return ({k: held.get(k, v) for k, v in SWEEP_DEFAULTS.items()},
            {k: "declared" if k in held else "default" for k in SWEEP_DEFAULTS})


def sweep_seats(declaration):
    """`{a, b}`: the sweeps' seats as run.json declares them (`seats.S6.sweep_a`, `seats.S6.sweep_b`), SEAT_UNDECLARED
    otherwise."""
    held = (declaration or {}).get("seats") or {}
    missing = [key for key in SWEEP_SEAT_KEYS.values() if not held.get(key)]
    if missing:
        raise Refused(f"SEAT_UNDECLARED {missing}: S6's sweeps are seated by run.json, {list(SWEEP_SEAT_KEYS.values())}")
    return {side: held[key] for side, key in SWEEP_SEAT_KEYS.items()}


def sweep_layers(absence_doc):
    """The layers an absence sweep covers: every indexed layer under the `literal` policy, which reads the reference
    point's own flag, or the layers a `scoped` policy lists (`derive.absence`)."""
    if (absence_doc or {}).get("policy") == "scoped":
        return list(derive.table()["absence_completeness"]["layers"])
    return None


def absent_candidates(judged, judgments, sources):
    """`(absent, not judged by both)`: the judged candidates whose diagnosis at the current reference point, from both
    judges' units as derive reads them (`agreed`, `unit_diagnosis`, `candidate_diagnosis` at a complete point), is
    `gap` - an absence claim, which the sweep checks. A candidate either judge did not judge is not swept."""
    absent, not_both = [], []
    for cid in judged:
        held = judgments.get(cid) or {}
        if set(held) != set(SEAT_KEYS):
            not_both.append(cid)
            continue
        diagnosis, _row = derive.candidate_diagnosis(unit_diagnoses(held), True, lifecycle_of(sources[cid]))
        if diagnosis == "gap":
            absent.append(cid)
    return absent, not_both


def lifecycle_of(source):
    """The lifecycle `derive.candidate_diagnosis` reads a candidate under: none for a formed one, its source otherwise."""
    return None if source == "formed" else source


def unit_diagnoses(held):
    """`{unit id: diagnosis, or (disputed, [A's, B's])}` over both judges' judgments `{A: ..., B: ...}` of one packet,
    as derive reads them (`agreed`, `unit_diagnosis`)."""
    a, b = ({u["unit_id"]: u for u in held[who]["units"]} for who in ("A", "B"))
    units = {}
    for uid in a:
        pair = (a[uid], b.get(uid) or {})
        values = [derive.agreed(pair[0].get(f), pair[1].get(f)) for f in ("situation", "action")]
        diagnosis = derive.unit_diagnosis(*values)
        units[uid] = (diagnosis, [derive.unit_diagnosis(x["situation"], x["action"]) for x in pair]) \
            if diagnosis == derive.DISPUTED else diagnosis
    return units


def remaining_of(index, retrieved, layers):
    """A candidate's remaining units: the units S5 indexes (one per text in each layer, `UnitIndex`) in `layers` (None:
    every layer), less the ones retrieved for it, a copy counted as the unit that stands for it."""
    taken = {index.rep_of.get(u, u) for u in retrieved}
    return sorted(rep for rep in index.copies if (layers is None or index.layer_of[rep] in layers) and rep not in taken)


def shard_plan(remaining, candidates_per_shard, shard_units):
    """The sweep's groups and shards (lead decisions E2, E3): the candidates `candidates_per_shard` at a time in id
    order, and each group's remaining units, the union of its candidates', `shard_units` at a time in unit id order; a
    shard names for each candidate the units of it that are that candidate's remaining ones, and a candidate with none
    in a shard is not in it."""
    ids, groups = sorted(remaining), []
    for g, start in enumerate(range(0, len(ids), candidates_per_shard), 1):
        members = ids[start:start + candidates_per_shard]
        union = sorted(set().union(*(remaining[c] for c in members)))
        shards = []
        for n, at in enumerate(range(0, len(union), shard_units), 1):
            inside = set(union[at:at + shard_units])
            pairs = {c: [u for u in remaining[c] if u in inside] for c in members}
            shards.append({"shard": f"s{n:03d}", "units": union[at:at + shard_units],
                           "pairs": {c: us for c, us in pairs.items() if us}})
        groups.append({"group": f"g{g:03d}", "candidates": members, "shards": shards})
    return groups


def shard_problems(groups, remaining):
    """Done-when 6's set accounting: every candidate in exactly one group, and each of its remaining units in exactly
    one shard of that group and nothing else (SET_MISMATCH)."""
    out, seen = [], collections.Counter(c for g in groups for c in g["candidates"])
    if set(seen) != set(remaining) or any(n > 1 for n in seen.values()):
        out.append(f"SET_MISMATCH sweep groups: {sorted(set(remaining) - set(seen))[:3]} in none, "
                   f"{sorted(c for c, n in seen.items() if n > 1)[:3]} in more than one")
    for g in groups:
        for c in g["candidates"]:
            got = collections.Counter(u for sh in g["shards"] for u in sh["pairs"].get(c, []))
            want = set(remaining.get(c, []))
            twice, missing, extra = (sorted(u for u, n in got.items() if n > 1), sorted(want - set(got)),
                                     sorted(set(got) - want))
            if twice or missing or extra:
                out.append(f"SET_MISMATCH sweep {g['group']} {c}: remaining units in no shard {missing[:3]}, in two "
                           f"{twice[:3]}, not remaining {extra[:3]}")
    return out


def sweep_view(candidate, entries, units):
    """What a sweep is shown of a candidate: a formed one's lesson, type, situation, action and exception; a lifecycle
    one's record without its ids, with the texts of the ledger entries and units it names. A name the stores do not hold
    is counted, as S5 counts a named unit it does not hold (`retrieve_units`' absent): an inventory taken again since
    the intake can drop a unit a hint named."""
    if candidate["source"] == "formed":
        return {k: candidate.get(k) for k in ("lesson", "type", "situation", "action", "exception")}
    life = candidate.get("lifecycle") or {}
    named_entries = stage_retrieve.as_list(life.get("target_entry")) + stage_retrieve.as_list(life.get("entries"))
    named_units = stage_retrieve.as_list(life.get("target_unit")) + stage_retrieve.as_list(life.get("target_units"))
    return {"source": candidate["source"], **{k: v for k, v in sorted(life.items()) if k not in LIFECYCLE_NAMED},
            "entry_texts": [lifecycle_intake.entry_text(entries[i]) for i in named_entries if i in entries],
            "unit_texts": [units[u]["text"] for u in named_units if u in units],
            "names_not_held": sum(1 for i in named_entries if i not in entries) + sum(1 for u in named_units if u not in units)}


class SweepLabels:
    """What one sweep packet labels: its candidates k1, ... in id order and its units n1, ... in the shard's order, and
    the pairs it lists - each candidate with the units of the shard that are its remaining ones (E3)."""

    def __init__(self, shard, candidates, units, entries):
        self.shard, self.unit_store, self.entry_store = shard, units, entries
        self.candidates = {f"k{n}": cid for n, cid in enumerate(sorted(shard["pairs"]), 1)}
        self.units = {f"n{n}": uid for n, uid in enumerate(shard["units"], 1)}
        of_unit = {uid: label for label, uid in self.units.items()}
        self.listed = {(k, of_unit[u]) for k, cid in self.candidates.items() for u in shard["pairs"][cid]}
        self.views = {k: sweep_view(candidates[cid], entries, units) for k, cid in self.candidates.items()}

    def candidates_text(self):
        of_unit = {uid: label for label, uid in self.units.items()}
        return "\n".join(json.dumps({"candidate": k, **self.views[k],
                                     "units": [of_unit[u] for u in self.shard["pairs"][cid]]}, ensure_ascii=False)
                         for k, cid in self.candidates.items())

    def units_text(self):
        return "\n".join(json.dumps({"unit": label, "layer": self.unit_store[uid]["layer"],
                                     "path": self.unit_store[uid].get("path"),
                                     "heading": self.unit_store[uid].get("heading") or "",
                                     "text": self.unit_store[uid]["text"]}, ensure_ascii=False)
                         for label, uid in self.units.items())

    def resolve(self, answer):
        """An accepted sweep answer in the stores' ids."""
        return [{"candidate_id": self.candidates[r["candidate"]], "unit_id": self.units[r["unit"]],
                 **{k: r[k] for k in ("situation", "action", "reason")}} for r in answer["pairs"]]


def sweep_payload(labels, inventory_sha256):
    """One shard's sweep payload, the same for both sweeps (N#1), bound to the inventory it was cut from: the
    inventory's hash is in the payload, so a moved inventory is a new payload and no earlier attempt answers it."""
    return packet.render(SWEEP_TEMPLATE, {"candidates": labels.candidates_text(), "units": labels.units_text(),
                                          "inventory": f"sha256:{inventory_sha256}"})


def sweep_problems(labels, answer):
    """What a schema-valid sweep answer gets wrong against its packet: every listed pair judged exactly once
    (SWEEP_PAIR_MISSING, SWEEP_PAIR_TWICE) and no other (SWEEP_PAIR_UNLISTED, E3), by labels the packet shows
    (UNKNOWN_LABEL)."""
    out, seen = [], {}
    for n, row in enumerate(answer.get("pairs") or []):
        pair, where = (row["candidate"], row["unit"]), f"pairs[{n}] {row['candidate']} {row['unit']}"
        if pair[0] not in labels.candidates or pair[1] not in labels.units:
            out.append(f"UNKNOWN_LABEL {where}: this packet shows no such candidate or unit")
        elif pair not in labels.listed:
            out.append(f"SWEEP_PAIR_UNLISTED {where}: the packet does not list this unit for this candidate (E3)")
        elif pair in seen:
            out.append(f"SWEEP_PAIR_TWICE {where}: judged at pairs[{seen[pair]}] already")
        else:
            seen[pair] = n
    out += [f"SWEEP_PAIR_MISSING {k} {u}: the packet lists it and the answer does not judge it"
            for k, u in sorted(labels.listed - set(seen))]
    return out


def sweep_check(labels):
    """The stage's check of a sweep attempt, as `Supervisor.item(stage_check=)` asks it."""
    from runlib import stage_read

    def judged(call_dir):
        return sweep_problems(labels, stage_read.answer_of(call_dir))
    return judged


def sweep_rel(group, shard, side):
    return f"sweeps/{group}/{shard}/{side}.json"


def kept_sweep(run_dir, rel, inventory_sha256):
    """A kept sweep result, refused by name when it was cut from another inventory than the one S6 reads now
    (SWEEP_INVENTORY_MOVED, done-when 6)."""
    held = records.read_json(pathlib.Path(run_dir) / rel)
    if held.get("inventory_sha256") != inventory_sha256:
        raise Refused(f"SWEEP_INVENTORY_MOVED {rel}: cut from inventory {str(held.get('inventory_sha256'))[:12]}, and S6 "
                      f"reads {inventory_sha256[:12]}; its shard is swept again")
    return held


def sweep_context(run_dir, declaration):
    """What a sweep plan reads: S5's checks and population, S2's current units, the ledger's entries and S5's index."""
    checks = records.read_json(run_dir / "checks.json")
    population = records.read_json(run_dir / "checked-candidates.json")
    units = records.read_json(run_dir / "inventory" / "current.json")["units"]
    ledger, _read = lifecycle_intake.ledger_of(declaration)
    return {"checks": checks, "by_id": {k["candidate_id"]: k for k in population["candidates"]},
            "rows": {r["candidate_id"]: r for r in checks["candidates"]}, "units": {u["unit_id"]: u for u in units},
            "entries": {e["id"]: e for e in ledger["entries"]}, "index": stage_retrieve.UnitIndex(units)}


def sweep_packets(context, groups, inventory_sha256):
    """`[(group, shard, labels, payload)]` of every shard with a pair to judge."""
    out = []
    for g in groups:
        for sh in g["shards"]:
            if sh["pairs"]:
                labels = SweepLabels(sh, context["by_id"], context["units"], context["entries"])
                out.append((g["group"], sh["shard"], labels, sweep_payload(labels, inventory_sha256)))
    return out


def upper_bound(run_dir, declaration, judged, seats_path=None):
    """The sweep's work at its largest (lead, on J2a), for a dry run: every judged candidate as a gap, its remaining
    units the catalog layer's indexed units less its retrieved ones. Groups, shards, packets, payload and driver bytes,
    input tokens at J0's density and output at the cap - counts only, labelled as the bound."""
    context = sweep_context(run_dir, declaration)
    sizes, basis = sweeps_of(declaration)
    seats = sweep_seats(declaration)
    remaining = {cid: remaining_of(context["index"], [r["unit_id"] for r in context["rows"][cid]["retrieved_units"]],
                                   [UPPER_BOUND_LAYER]) for cid in judged}
    groups = shard_plan(remaining, sizes["candidates_per_shard"], sizes["shard_units"])
    inventory = packet.sha256_bytes((run_dir / "inventory" / "current.json").read_bytes())
    schema_bytes = packet.schema_bytes(sweep_schema())
    payload_bytes, driver = 0, {side: 0 for side in seats}
    built = sweep_packets(context, groups, inventory)
    for group, shard, _labels, text in built:
        payload_bytes += len(text.encode("utf-8"))
        for side, seat in seats.items():
            item = f"sweep-{group}-{shard}-{side}"
            made = packet.build(f"{run_dir.resolve().name}-{STAGE}-{item}-a1", STAGE, seat, text, schema_bytes)
            driver[side] += bound.driver_bytes(made, schema_bytes)[0]
    calls = len(built) * len(seats)
    return {"basis": UPPER_BOUND_BASIS, "layer": UPPER_BOUND_LAYER, "sizes": sizes, "sizes_basis": basis, "seats": seats,
            "candidates": len(remaining), "remaining_units": sum(len(v) for v in remaining.values()),
            "groups": len(groups), "shards": sum(len(g["shards"]) for g in groups), "packets": calls,
            "pairs": sum(len(us) for _g, _s, labels, _t in built for us in labels.shard["pairs"].values()),
            "payload_bytes": payload_bytes, "driver_bytes": driver,
            "input_tokens_at_j0_density": {side: int(math.ceil(v / J0_DENSITY)) for side, v in driver.items()},
            "density": J0_DENSITY, "density_basis": J0_DENSITY_BASIS, "output_tokens_at_most": calls * sizes["output_cap"]}


def absence_claims(judged, absent, not_both, sources, absence, layers):
    """The judges' absence claims, counted whether or not they are swept: the candidates both judges judged whose agreed
    unit diagnoses touch no covering row (`absent_candidates`), by name and per candidate kind beside the number of that
    kind judged by both, with the reference point's state and every layer's status. Under the literal policy no
    reference point is complete while a layer has no producer, so nothing is swept, and this count is the measured share
    the lead's D-20261111-eaa2a8 names as the condition for reopening the scoped policy; it costs no call."""
    both = [cid for cid in judged if cid not in set(not_both)]
    kinds = sorted({sources[cid] for cid in judged})
    return {"count": len(absent), "candidates": sorted(absent), "judged_by_both": len(both),
            "by_kind": {kind: {"claims": sum(1 for cid in absent if sources[cid] == kind),
                               "judged_by_both": sum(1 for cid in both if sources[cid] == kind)} for kind in kinds},
            "not_judged_by_both": sorted(not_both), "swept": absence.get("complete") is True,
            "reference": {"point": "current", "policy": absence.get("policy"),
                          "complete": absence.get("complete") is True, "layers": dict(sorted(layers.items()))}}


def sweep_stage(run_dir, stage, supervisor, declaration, judged, judgments, sources, caps, tranche):
    """The absence sweeps over S6's judgments (plan WP-11 J3a, done-when 6): the judges' absence claims are counted
    first (`absence_claims`), at every reference point; at one the absence policy reads as incomplete, every absence is
    `unknown` and nothing is swept; otherwise each absence claim's remaining units are cut into shards (`shard_plan`,
    held to `shard_problems`), and each shard is sent to both sweeps with one payload bound to the inventory hash, each
    answer checked (`sweep_problems`) and kept under sweeps/<group>/<shard>/<a|b>.json. Returns the summary's `sweeps`
    section and the sweeps' receipts. `absent` names the claims a sweep stands behind, so it stays empty where none
    runs: a derivation waits for the sweeps of every candidate it lists."""
    checks = records.read_json(run_dir / "checks.json")
    absence = checks.get("absence") or {}
    sizes, basis = sweeps_of(declaration)
    section = {"reference": "current", "policy": absence.get("policy"), "complete": absence.get("complete") is True,
               "unknown_layers": absence.get("unknown_layers") or [], "sizes": sizes, "sizes_basis": basis,
               "absent": [], "not_judged_by_both": [], "groups": [], "calls": []}
    absent, not_both = absent_candidates(judged, judgments, sources)
    statuses = current_point(records.read_json(run_dir / "inventory" / "current.json"))["layers"]
    section["claims"] = absence_claims(judged, absent, not_both, sources, absence, statuses)
    if not section["complete"]:
        section["why"] = ("absence unknown: the reference point is incomplete under the " + str(absence.get("policy"))
                          + " policy, so no absence claim stands and nothing is swept")
        return section, []
    seats = sweep_seats(declaration)
    context = sweep_context(run_dir, declaration)
    layers = sweep_layers(absence)
    remaining = {cid: remaining_of(context["index"], [r["unit_id"] for r in context["rows"][cid]["retrieved_units"]],
                                   layers) for cid in absent}
    groups = shard_plan(remaining, sizes["candidates_per_shard"], sizes["shard_units"])
    problems = shard_problems(groups, remaining)
    if problems:
        raise Refused("\n".join(problems))
    inventory = packet.sha256_bytes((run_dir / "inventory" / "current.json").read_bytes())
    held_schema = sweep_schema()
    schema_bytes = packet.schema_bytes(held_schema)
    receipts = []
    section.update(absent=absent, not_judged_by_both=not_both, layers=layers, inventory_sha256=inventory,
                   groups=[{"group": g["group"], "candidates": g["candidates"],
                            "shards": [{"shard": sh["shard"], "units": len(sh["units"]),
                                        "pairs": sum(len(us) for us in sh["pairs"].values())} for sh in g["shards"]]}
                           for g in groups])
    limits = {side: limits_of(seat, run_dir, declaration, supervisor.seats_path, case=SWEEP_CASE,
                              output_cap=sizes["output_cap"]) for side, seat in seats.items()}
    built = sweep_packets(context, groups, inventory)
    over_capacity(run_dir.resolve().name, [(f"sweep-{group}-{shard}-{side}", side, seat, text)
                                           for group, shard, _labels, text in built for side, seat in seats.items()],
                  limits, schema_bytes, "SWEEP_OVER_CAPACITY", "the run declares a smaller sweeps.shard_units")
    for group, shard, labels, text in built:
        payload_sha256 = packet.sha256_bytes(text.encode("utf-8"))
        row = {"group": group, "shard": shard, "seats": {}}
        for side, seat in seats.items():
            out = supervisor.item(STAGE, f"sweep-{group}-{shard}-{side}", seat, text, held_schema, case_type=SWEEP_CASE,
                                  caps=caps, view_window=False, tranche=tranche, max_output_tokens=sizes["output_cap"],
                                  stage_check=sweep_check(labels), resume=True,
                                  context_capacity=limits[side]["capacity"],
                                  packet_check=lambda made, bounds=limits[side], side=side: attempt_problems(
                                      made, bounds, schema_bytes, f"sweep {side}", "SWEEP_OVER_CAPACITY"))
            held = call_row(out)
            if out["outcome"] == "accepted":
                call_dir = pathlib.Path(out["accepted"])
                call_id = records.read_json(call_dir / "call.json")["call_id"]
                receipt = records.read_json(call_dir / "receipt.json")
                rel = sweep_rel(group, shard, side)
                records.write_json(run_dir, run_dir / rel, {
                    "group": group, "shard": shard, "side": side, "seat": seat, "call_id": call_id,
                    "inventory_sha256": inventory, "payload_sha256": payload_sha256,
                    "packet_sha256": receipt.get("packet_sha256"),
                    "pairs": labels.resolve(gate.accepted(call_dir, judged=True))})
                stage.output(rel)
                receipts.append((f"sweep/{group}/{shard}", seat, call_id, receipt, payload_sha256,
                                 corrected_sha256(call_dir, text)))
                held.update(call_id=call_id, result=rel)
            row["seats"][side] = held
        section["calls"].append(row)
    return section, receipts


# ---- Judge B's cross-review of an absence claim (plan WP-11 J3b, done-when 3, F10) --------------------------------

CROSS_TEMPLATE = "cross_review"
CROSS_SCHEMA_PATH = HERE / "schemas" / "cross_review.schema.json"
CROSS_CASE = "cross_review"   # a cross-review call's class (dispatch.class_key)
NEGATIVES = 50   # design §6.2: fifty negatives, drawn by code from the run id


def cross_schema():
    return json.loads(CROSS_SCHEMA_PATH.read_text(encoding="utf-8"))


def sweep_marks(results):
    """`{candidate id: {unit id: {side: {situation, action, reason}}}}` over kept sweep results (`kept_sweep`)."""
    marks = {}
    for held in results:
        for pair in held["pairs"]:
            marks.setdefault(pair["candidate_id"], {}).setdefault(pair["unit_id"], {})[held["side"]] = {
                k: pair[k] for k in ("situation", "action", "reason")}
    return marks


def flags_of(marks):
    """The units either sweep marked as a partial match - a situation or an action yes - in unit id order."""
    return sorted(u for u, sides in marks.items() if any("yes" in (m["situation"], m["action"]) for m in sides.values()))


def negatives_of(marks, seed, cid, n=NEGATIVES):
    """`n` of the units both sweeps marked as no match, drawn by code: the first by sha256 of the seed (the run id),
    the candidate and the unit. Fewer when fewer are there."""
    both_no = [u for u, sides in marks.items() if len(sides) == len(SWEEP_SEAT_KEYS)
               and all(m["situation"] == m["action"] == "no" for m in sides.values())]
    return sorted(both_no, key=lambda u: hashlib.sha256(f"{seed}\x00{cid}\x00{u}".encode("utf-8")).hexdigest())[:n]


class CrossLabels:
    """One cross-review packet's labels: the candidate k1, and its flagged and sampled units n1, ... in unit id order,
    each with both sweeps' marks."""

    def __init__(self, candidate, marks, flags, negatives, units, entries):
        self.candidate, self.marks, self.unit_store = candidate, marks, units
        self.flags, self.negatives = list(flags), list(negatives)
        self.units = {f"n{n}": u for n, u in enumerate(sorted(set(flags) | set(negatives)), 1)}
        self.view = sweep_view(candidate, entries, units)

    def candidate_text(self):
        return json.dumps({"candidate": "k1", **self.view}, ensure_ascii=False)

    def units_text(self):
        return "\n".join(json.dumps({"unit": label, "layer": self.unit_store[uid]["layer"],
                                     "path": self.unit_store[uid].get("path"),
                                     "heading": self.unit_store[uid].get("heading") or "",
                                     "text": self.unit_store[uid]["text"],
                                     "sweeps": {side: self.marks[uid][side] for side in sorted(self.marks[uid])}},
                                    ensure_ascii=False) for label, uid in self.units.items())

    def resolve(self, answer):
        return [{"unit_id": self.units[r["unit"]], **{k: r[k] for k in ("situation", "action", "reason")}}
                for r in answer["verdicts"]]


def cross_payload(labels):
    """One absence claim's cross-review payload (`packets/cross_review.md`)."""
    return packet.render(CROSS_TEMPLATE, {"candidate": labels.candidate_text(), "units": labels.units_text()})


def cross_problems(labels, answer):
    """What a schema-valid cross-review gets wrong against its packet: every unit shown judged exactly once
    (CROSS_UNIT_MISSING, CROSS_UNIT_TWICE), by a label the packet shows (UNKNOWN_LABEL)."""
    out, seen = [], {}
    for n, row in enumerate(answer.get("verdicts") or []):
        where = f"verdicts[{n}] {row['unit']}"
        if row["unit"] not in labels.units:
            out.append(f"UNKNOWN_LABEL {where}: this packet shows no unit so labelled")
        elif row["unit"] in seen:
            out.append(f"CROSS_UNIT_TWICE {where}: judged at verdicts[{seen[row['unit']]}] already")
        else:
            seen[row["unit"]] = n
    out += [f"CROSS_UNIT_MISSING {label}: the packet shows it and the review does not judge it"
            for label in labels.units if label not in seen]
    return out


def cross_check(labels):
    """The stage's check of a cross-review attempt, as `Supervisor.item(stage_check=)` asks it."""
    from runlib import stage_read

    def judged(call_dir):
        return cross_problems(labels, stage_read.answer_of(call_dir))
    return judged


def cross_rel(item):
    return f"cross_review/{item}.json"


def cross_review_problems(record, flags, negatives, payload_sha256):
    """Done-when 3 over a kept cross-review against what the sweep results give now: every partial flag either sweep
    raised and the drawn negatives in it (CROSS_REVIEW_INCOMPLETE), and its payload the one those results build
    (CROSS_REVIEW_STALE: a sweep's mark or reason changed after the review was sent)."""
    cid = record.get("candidate_id")
    out = []
    missing = sorted(set(flags) - set(record.get("partial_flags") or []))
    if missing:
        out.append(f"CROSS_REVIEW_INCOMPLETE {cid}: partial flags no review carries {missing[:5]}")
    if list(record.get("seeded_negatives") or []) != list(negatives):
        out.append(f"CROSS_REVIEW_INCOMPLETE {cid}: its {len(record.get('seeded_negatives') or [])} negatives are not the "
                   f"{len(negatives)} drawn from the run id")
    if record.get("payload_sha256") != payload_sha256:
        out.append(f"CROSS_REVIEW_STALE {cid}: its payload {str(record.get('payload_sha256'))[:12]} is not the one the "
                   f"sweep results build now ({payload_sha256[:12]})")
    return out


def cross_stage(run_dir, stage, supervisor, declaration, swept, item_of_cid, caps, tranche):
    """Judge B's cross-review of every absence claim the sweeps judged whole (plan WP-11 J3b, done-when 3): its packet
    carries every unit either sweep flagged and NEGATIVES units both marked as none, drawn from the run id, each with both
    sweeps' marks and reasons; the review judges each unit once (`cross_problems`) and is kept under
    cross_review/<item>.json, held to what the sweep results give (`cross_review_problems`). A claim whose sweeps did not
    all finish is not reviewed, and is named. Returns the summary's `cross_review` section and the calls' receipts."""
    section = {"seat": None, "reviewed": [], "not_reviewed": [], "calls": [], "negatives": NEGATIVES}
    if not swept.get("complete") or not swept.get("absent"):
        section["why"] = "no absence claim was swept" if swept.get("complete") else swept.get("why")
        return section, []
    seat = seats_of(declaration)["B"]
    section["seat"] = seat
    context = sweep_context(run_dir, declaration)
    inventory = swept["inventory_sha256"]
    results, finished = [], {}
    for row in swept["calls"]:
        for side, held in row["seats"].items():
            if held["outcome"] == "accepted":
                results.append(kept_sweep(run_dir, held["result"], inventory))
    marks = sweep_marks(results)
    run_id = run_dir.resolve().name
    held_schema = cross_schema()
    receipts = []
    todo = []
    for g in swept["groups"]:
        for cid in g["candidates"]:
            mine = marks.get(cid) or {}
            whole = [u for u, sides in mine.items() if len(sides) == len(SWEEP_SEAT_KEYS)]
            shards = [r for r in swept["calls"] if r["group"] == g["group"]]
            if any(h["outcome"] != "accepted" for r in shards for h in r["seats"].values()) or len(whole) != len(mine):
                section["not_reviewed"].append({"candidate_id": cid, "why": "a sweep of its group did not finish"})
                continue
            flags, negatives = flags_of(mine), negatives_of(mine, run_id, cid)
            if not flags and not negatives:
                section["not_reviewed"].append({"candidate_id": cid, "why": "no remaining unit to review"})
                continue
            labels = CrossLabels(context["by_id"][cid], mine, flags, negatives, context["units"], context["entries"])
            todo.append((cid, flags, negatives, labels, cross_payload(labels)))
    # every cross-review packet is held to Judge B's capacity before the first is sent (Codex WP-11 r1 #3)
    schema_bytes = packet.schema_bytes(held_schema)
    limits = limits_of(seat, run_dir, declaration, supervisor.seats_path, case=CROSS_CASE)
    over_capacity(run_id, [(f"{item_of_cid(cid)}-X", "B", seat, text) for cid, _f, _n, _l, text in todo], {"B": limits},
                  schema_bytes, "CROSS_OVER_CAPACITY", "a claim with this many flagged units is reviewed by a seat with "
                                                      "more context")
    for cid, flags, negatives, labels, text in todo:
        payload_sha256 = packet.sha256_bytes(text.encode("utf-8"))
        item = f"{item_of_cid(cid)}-X"
        out = supervisor.item(STAGE, item, seat, text, held_schema, case_type=CROSS_CASE, caps=caps,
                              view_window=False, tranche=tranche, max_output_tokens=OUTPUT_CAP,
                              stage_check=cross_check(labels), resume=True, context_capacity=limits["capacity"],
                              packet_check=lambda made: attempt_problems(made, limits, schema_bytes, "B",
                                                                         "CROSS_OVER_CAPACITY"))
        held = call_row(out)
        if out["outcome"] == "accepted":
            call_dir = pathlib.Path(out["accepted"])
            call_id = records.read_json(call_dir / "call.json")["call_id"]
            receipt = records.read_json(call_dir / "receipt.json")
            rel = cross_rel(item_of_cid(cid))
            record = {"candidate_id": cid, "seat": seat, "call_id": call_id, "inventory_sha256": inventory,
                      "seed": run_id, "payload_sha256": payload_sha256, "packet_sha256": receipt.get("packet_sha256"),
                      "partial_flags": flags, "seeded_negatives": negatives,
                      "verdicts": labels.resolve(gate.accepted(call_dir, judged=True))}
            problems = cross_review_problems(record, flags, negatives, payload_sha256)
            if problems:
                raise Refused("\n".join(problems))
            records.write_json(run_dir, run_dir / rel, record)
            stage.output(rel)
            receipts.append((f"cross/{cid}", seat, call_id, receipt, payload_sha256, corrected_sha256(call_dir, text)))
            held.update(call_id=call_id, result=rel)
            section["reviewed"].append(cid)
        section["calls"].append({"candidate_id": cid, "flags": len(flags), "negatives": len(negatives), **held})
    return section, receipts


# ---- the reconsiderations (plan WP-11 J3c, done-when 3, design §6.2) ----------------------------------------------

RECONSIDER = "R"   # a reconsideration's item is `<item>-R<judge>`
RECONSIDER_TEMPLATE = "reconsider"
RECONSIDER_SCHEMA_PATH = HERE / "schemas" / "reconsider.schema.json"
RECONSIDER_CASE = "reconsider"   # a reconsideration call's class (dispatch.class_key)
RECONSIDER_FIELDS = ("units", "matching_units")
# what a reconsideration does not answer: the candidate was judged by its first call, and admission reads that one
RECONSIDER_REFUSED = ("requirements", "consequence_class", "no_longer_arises", "ledger_relations")
RECONSIDER_COMMENT = ("design §6.2: a unit either sweep or Judge B flagged returns to both judges; plan WP-11 J3c. The "
                      "judge schema's `units` and `matching_units` and the definitions they reach, nothing else: the "
                      "candidate is not judged again. Projected from judge.schema.json (stage_judge.reconsider_projection), "
                      "and held equal to it by stage_judge's self-test.")


def reconsider_schema():
    return json.loads(RECONSIDER_SCHEMA_PATH.read_text(encoding="utf-8"))


def reconsider_projection(held=None):
    """What `schemas/reconsider.schema.json` must be: the judge schema's `units` and `matching_units` with the
    definitions they reach, closed, and no candidate-level field."""
    judge = held if held is not None else schema()
    defs = judge.get("$defs") or {}
    keep, todo = set(), [judge["properties"][f] for f in RECONSIDER_FIELDS]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/") and ref.split("/")[-1] not in keep:
                keep.add(ref.split("/")[-1])
                todo.append(defs[ref.split("/")[-1]])
            todo += list(node.values())
        elif isinstance(node, list):
            todo += node
    return {"$schema": judge.get("$schema"), "$comment": RECONSIDER_COMMENT, "title": "S6 reconsideration",
            "type": "object", "additionalProperties": False, "required": list(RECONSIDER_FIELDS),
            "properties": {f: judge["properties"][f] for f in RECONSIDER_FIELDS},
            "$defs": {k: defs[k] for k in sorted(keep)}}


def reconsider_payload(labels):
    """A reconsideration's payload both judges are sent (N#1): `packets/reconsider.md` with the candidate, its claims,
    the returned units and their context."""
    return packet.render(RECONSIDER_TEMPLATE, {"candidate": labels.candidate_text(), "claims": labels.claims_text(),
                                               "units": labels.units_text(), "context": labels.context_text()})


def reconsideration_rel(item, who):
    """Where one judge's reconsideration of a candidate is kept (plan WP-11: `reconsiderations/<candidate>/{A,B}.json`)."""
    return f"reconsiderations/{item}/{who}.json"


def returned_of(record):
    """The units a kept cross-review returns to both judges (design §6.2): every flag either sweep raised and every
    unit Judge B marked a match, in unit id order."""
    return sorted(set(record.get("partial_flags") or [])
                  | {v["unit_id"] for v in record.get("verdicts") or [] if "yes" in (v["situation"], v["action"])})


def returned_labels(labels, unit_ids):
    """The judgment packet's labels for a reconsideration: the same candidate, claims and quotes, the returned units in
    place of the retrieved ones, and no ledger entry, since the candidate's first judgment related every one S5
    retrieved."""
    return JudgeLabels(labels.candidate, {"retrieved_units": [{"unit_id": u} for u in unit_ids], "ledger_entries": []},
                       labels.unit_store, labels.entry_store, labels.subject_of, labels.evidence_store)


def reconsideration_problems(cid, returned, held):
    """Done-when 3: every returned unit reconsidered by both judges. RECONSIDERATION_MISSING for a judge with no
    accepted reconsideration, or one that judges other units than the cross-review returned."""
    out = []
    for who in SEAT_KEYS:
        judgment = held.get(who)
        if judgment is None:
            out.append(f"RECONSIDERATION_MISSING {cid} {who}: the {len(returned)} units its cross-review returned have no "
                       f"accepted reconsideration by Judge {who}")
            continue
        judged = sorted(u["unit_id"] for u in judgment.get("units") or [])
        if judged != sorted(returned):
            out.append(f"RECONSIDERATION_MISSING {cid} {who}: Judge {who}'s reconsideration judges {len(judged)} units "
                       f"and its cross-review returned {len(returned)}; not judged {sorted(set(returned) - set(judged))[:5]}")
    return out


def reconsidered_diagnosis(original, held, lifecycle):
    """`(diagnosis, row id)` of an absence claim once both judges reconsidered the returned units: derive's candidate
    diagnosis at a complete reference point over the units of its first judgments and the reconsidered ones. A unit
    both now find matching contradicts the claim; one they disagree on that could reach a row before the gap makes it
    `unknown` by `disputed` (O4)."""
    units = unit_diagnoses(original)
    if held:
        units.update(unit_diagnoses(held))
    return derive.candidate_diagnosis(units, True, lifecycle)


def reconsider_stage(run_dir, stage, supervisor, declaration, summary, packets, judgments, crossed, caps, tranche):
    """Both judges' reconsideration of every absence claim Judge B reviewed (plan WP-11 J3c, done-when 3): the returned
    units (`returned_of`) go to Judge A and Judge B in one packet (`reconsider_payload`, N#1) asking for those units and
    their matching units only (`reconsider_schema`; `check` refuses a candidate-level field by FIELD_UNEXPECTED), kept
    under reconsiderations/<item>/<A|B>.json, and the claim is diagnosed again
    (`reconsidered_diagnosis`). A claim nothing returned keeps its gap without a call; one missing a judge's
    reconsideration is named (`reconsideration_problems`) and not diagnosed. Returns the summary's `reconsiderations`
    section and the calls' receipts."""
    section = {"reconsidered": [], "not_reconsidered": [], "missing": [], "calls": []}
    held_schema = reconsider_schema()
    schema_bytes = packet.schema_bytes(held_schema)
    limits = {}
    sources = {r["candidate_id"]: r["source"] for r in summary["packets"]}
    receipts = []
    for cid in crossed.get("reviewed") or []:
        item = item_of(cid)
        returned = returned_of(records.read_json(run_dir / cross_rel(item)))
        lifecycle = lifecycle_of(sources[cid])
        if not returned:
            diagnosis, row_id = reconsidered_diagnosis(judgments[cid], {}, lifecycle)
            section["reconsidered"].append({"candidate_id": cid, "returned": 0, "diagnosis": diagnosis, "row": row_id})
            continue
        labels = returned_labels(packets[cid][0], returned)
        text = reconsider_payload(labels)
        payload_sha256 = packet.sha256_bytes(text.encode("utf-8"))
        row, held = {"candidate_id": cid, "item": item, "returned": len(returned), "seats": {}}, {}
        for who, seat in summary["seats"].items():
            if who not in limits:
                limits[who] = limits_of(seat, run_dir, declaration, supervisor.seats_path, case=RECONSIDER_CASE)
            bounds = limits[who]
            out = supervisor.item(STAGE, f"{item}-{RECONSIDER}{who}", seat, text, held_schema, case_type=RECONSIDER_CASE,
                                  caps=caps, view_window=False, tranche=tranche, max_output_tokens=OUTPUT_CAP,
                                  stage_check=check(labels, bounds["capacity"], reconsider=True), resume=True,
                                  context_capacity=bounds["capacity"],
                                  packet_check=lambda built, bounds=bounds, who=who: attempt_problems(
                                      built, bounds, schema_bytes, who))
            call = call_row(out)
            if out["outcome"] == "accepted":
                call_dir = pathlib.Path(out["accepted"])
                call_id = records.read_json(call_dir / "call.json")["call_id"]
                receipt = records.read_json(call_dir / "receipt.json")
                rel = reconsideration_rel(item, who)
                held[who] = labels.resolve(gate.accepted(call_dir, judged=True))
                records.write_json(run_dir, run_dir / rel, {
                    "candidate_id": cid, "item": item, "judge": who, "seat": seat, "call_id": call_id,
                    "payload_sha256": payload_sha256, "packet_sha256": receipt.get("packet_sha256"),
                    "returned": returned, "judgment": held[who]})
                stage.output(rel)
                receipts.append((f"reconsider/{cid}", seat, call_id, receipt, payload_sha256,
                                 corrected_sha256(call_dir, text)))
                call.update(call_id=call_id, reconsideration=rel)
            row["seats"][who] = call
        section["calls"].append(row)
        problems = reconsideration_problems(cid, returned, held)
        if problems:
            section["missing"] += problems
            section["not_reconsidered"].append({"candidate_id": cid, "why": "RECONSIDERATION_MISSING"})
            continue
        diagnosis, row_id = reconsidered_diagnosis(judgments[cid], held, lifecycle)
        section["reconsidered"].append({"candidate_id": cid, "returned": len(returned), "diagnosis": diagnosis,
                                        "row": row_id})
    return section, receipts


# ---- the derivations (plan WP-11 J4a, design §4's S6 row, §6.4) -------------------------------------------------

DERIVATIONS = "judgments/derivations.json"
TEST_STATE = "untested: s8_deferred"   # release 1 runs no S8 (D-20261111-818391)
DELIVERY_WAITING = "delivery_assembly_waiting"   # lead decision D3: S5b assembles it, and S6 does not read it yet
UNIT_OUTCOMES_NONE = ("unit outcomes are read at the release reference point (design §6.4), and S6 judges the current "
                      "point only until S5 retrieves at a release point (D-20261111-c4fa71): S7 receives no unit outcome in "
                      "release 1")
ARC_UNDETERMINED = ("an arc retrospective the owner confirms in the review (design §7.4) is the only producer, and the "
                    "review comes after S6; derive is given arc_confirmed false, so a type G candidate is eligible by "
                    "its lineage count alone (D-20261111-f122c0)")


G_TYPES = tuple(next(r for r in derive.table()["promotion"] if r["id"] == "type_g")["types"])


def marks_of(judgment):
    """A judgment's requirement marks as derive reads them: `{requirement: mark}`."""
    return {name: held["mark"] for name, held in (judgment.get("requirements") or {}).items()}


def judged_units(held):
    """`{unit id: {A: {situation, action, following, contribution}, B: ...}}` over both judges' judgments of one packet:
    a matching unit's following and contribution from its `matching_units` row, None for a unit that does not match."""
    out = {}
    for who, judgment in held.items():
        matching = {m["unit_id"]: m for m in judgment.get("matching_units") or []}
        for u in judgment["units"]:
            m = matching.get(u["unit_id"]) or {}
            out.setdefault(u["unit_id"], {})[who] = {"situation": u["situation"], "action": u["action"],
                                                     "following": m.get("following"), "contribution": m.get("contribution")}
    return out


def current_point(current):
    """The current reference point as derive reads one: S2's completeness flag and its layers' statuses."""
    return {"complete": (current.get("reference") or {}).get("complete") is True,
            "layers": {row["layer"]: row["status"] for row in current.get("layers") or []}}


def derivation_input(candidate, source, row, first, again, point):
    """`derive.unit_outcome`'s judgment for one candidate: its type and lifecycle, both judges' requirement marks,
    class and no_longer_arises from their first judgments, the current point's units - the ones S5 retrieved and the
    ones reconsidered (`again`, may be empty) - S5's checks passed (it was judged), and its counted lineages. No release
    point: S6 judges the current one only until S5 retrieves at a release point (D-20261111-c4fa71). No arc
    confirmation has a producer in S6, so it is False."""
    units = judged_units(first)
    units.update(judged_units(again) if again else {})
    return {"candidate": {"candidate_id": candidate["candidate_id"], "type": candidate.get("type"),
                          "lifecycle": lifecycle_of(source)},
            "judges": {who: {"requirements": marks_of(first[who]), "consequence_class": first[who].get("consequence_class"),
                             "no_longer_arises": (first[who].get("no_longer_arises") or {}).get("value") is True}
                       for who in SEAT_KEYS},
            "points": {"current": {**point, "units": units}},
            "checks_pass": True, "lineages": (row.get("recurrence") or {}).get("count", 0),
            "arc_confirmed": False}   # undetermined, not false: ARC_UNDETERMINED


def reconsiderations_of(run_dir, candidate_id, again):
    """Both judges' reconsiderations of `candidate_id` that the S6 invocation whose `reconsiderations` section is `again`
    accepted, `{A: judgment, B: judgment}`; {} when it reconsidered nothing of that candidate. A file is read only when
    the section lists the candidate reconsidered with returned units, and it must name the call the section accepted
    for its judge: RECONSIDERATION_STALE otherwise. Codex WP-11 r1 #2: the files were read because they existed, so a
    claim whose cross-review later returned nothing, or a file another invocation left, was derived from them."""
    done = next((r for r in (again or {}).get("reconsidered") or [] if r["candidate_id"] == candidate_id), None)
    if done is None or not done.get("returned"):
        return {}
    row = next((r for r in (again or {}).get("calls") or [] if r["candidate_id"] == candidate_id), {})
    held, problems = {}, []
    for who in SEAT_KEYS:
        rel = reconsideration_rel(item_of(candidate_id), who)
        accepted = ((row.get("seats") or {}).get(who) or {}).get("call_id")
        path = pathlib.Path(run_dir) / rel
        record = records.read_json(path) if path.is_file() else {}
        if accepted is None or record.get("call_id") != accepted:
            problems.append(f"RECONSIDERATION_STALE {candidate_id} {who}: {rel} names the call "
                            f"{record.get('call_id')}, and the invocation that reconsidered it accepted {accepted}")
        else:
            held[who] = record["judgment"]
    if problems:
        raise Refused("\n".join(problems))
    return held


def derivation_given(run_dir, candidate, source, check_row, first, point, again):
    """`derive.unit_outcome`'s input for one candidate both judges judged: `derivation_input` over their first
    judgments and the reconsiderations the invocation whose `reconsiderations` section is `again` accepted for it
    (`reconsiderations_of`). The one place it is assembled: S6's `derive_stage` and S10's adjudication
    (`given_from_run`, plan WP-20 K5) both call it, so a recomputation with the owner's values reads exactly what S6
    read."""
    return derivation_input(candidate, source, check_row, first,
                            reconsiderations_of(run_dir, candidate["candidate_id"], again), point)


def given_artifacts(run_dir, candidate_id):
    """The per-candidate S6 outputs `given_from_run` reads: both judges' judgments, and their reconsiderations when
    S6's summary says it reconsidered the candidate with returned units. A caller declares them as inputs so the shared
    record checks hold them to S6's record."""
    item = item_of(candidate_id)
    again = (records.read_json(pathlib.Path(run_dir) / SUMMARY).get("reconsiderations") or {})
    done = any(r["candidate_id"] == candidate_id and r.get("returned") for r in again.get("reconsidered") or [])
    return [judgment_rel(item, who) for who in SEAT_KEYS] + ([reconsideration_rel(item, who) for who in SEAT_KEYS]
                                                             if done else [])


GIVEN_INPUTS = ("checked-candidates.json", "checks.json", "inventory/current.json")   # with SUMMARY and DERIVATIONS


def given_from_run(run_dir, candidate_id):
    """`derivation_given` for one candidate from what S6 left on disk: the candidate (S5's checked-candidates.json),
    its S5 row (checks.json), its source (S6's judgments/judge.json), the current point (S2's inventory/current.json)
    and both judges' first judgments (`judgment_rel`); the reconsiderations `derivation_given` reads itself."""
    run_dir = pathlib.Path(run_dir)
    population = {k["candidate_id"]: k for k in records.read_json(run_dir / "checked-candidates.json")["candidates"]}
    rows = {r["candidate_id"]: r for r in records.read_json(run_dir / "checks.json")["candidates"]}
    summary = records.read_json(run_dir / SUMMARY)
    sources = {r["candidate_id"]: r["source"] for r in summary["packets"]}
    point = current_point(records.read_json(run_dir / "inventory" / "current.json"))
    # each first judgment must be the one the summary's call accepted, as each reconsideration must be (Codex WP-11 r1
    # #2, the same hole in this reader): a file an earlier invocation left is not what S6 derived from
    calls = next((r for r in summary.get("calls") or [] if r["candidate_id"] == candidate_id), {})
    first, stale = {}, []
    for who in SEAT_KEYS:
        rel = judgment_rel(item_of(candidate_id), who)
        record = records.read_json(run_dir / rel)
        accepted = ((calls.get("seats") or {}).get(who) or {}).get("call_id")
        if accepted is None or record.get("call_id") != accepted:
            stale.append(f"JUDGMENT_STALE {candidate_id} {who}: {rel} names the call {record.get('call_id')}, and S6's "
                         f"summary accepted {accepted}")
        first[who] = record["judgment"]
    if stale:
        raise Refused("\n".join(stale))
    return derivation_given(run_dir, population[candidate_id], sources[candidate_id], rows[candidate_id], first, point,
                            summary.get("reconsiderations") or {})


def derive_stage(run_dir, summary, judgments, swept, again):
    """The derivations of every candidate both judges judged (design §4's S6 row: code derives diagnosis, delivery
    state, kind, admission and promotion eligibility; §6.4 through `derive.unit_outcome`). An absence claim whose sweeps,
    cross-review and reconsiderations did not all finish is not derived and is named, since its gap is not checked; so
    is a candidate a judge did not judge. Delivery is not read (lead decision D3): every (session, unit) pair a unit
    outcome would need is counted as DELIVERY_WAITING. Returns the document `judgments/derivations.json` holds, its
    `verdicts` in the shape `controls.evaluate` reads."""
    population = {k["candidate_id"]: k for k in records.read_json(run_dir / "checked-candidates.json")["candidates"]}
    rows = {r["candidate_id"]: r for r in records.read_json(run_dir / "checks.json")["candidates"]}
    point = current_point(records.read_json(run_dir / "inventory" / "current.json"))
    sources = {r["candidate_id"]: r["source"] for r in summary["packets"]}
    finished = {r["candidate_id"] for r in again.get("reconsidered") or []}
    verdicts, not_derived, waiting = {}, [], 0
    for cid in sorted(sources):
        first = judgments.get(cid) or {}
        if set(first) != set(SEAT_KEYS):
            not_derived.append({"candidate_id": cid, "why": "a judge's call did not finish"})
            continue
        if cid in (swept.get("absent") or []) and cid not in finished:
            not_derived.append({"candidate_id": cid, "why": "its absence claim's sweeps, cross-review and "
                                                           "reconsiderations did not all finish"})
            continue
        given = derivation_given(run_dir, population[cid], sources[cid], rows[cid], first, point, again)
        outcome = derive.unit_outcome(given, {}, TEST_STATE)
        matched = [u for u, d in (outcome["unit_diagnosis"].get("current") or {}).items() if d != "no match"]
        waiting += len(population[cid].get("sessions") or []) * len(matched)
        verdicts[cid] = {"outcome": outcome, "requirements": {who: given["judges"][who]["requirements"] for who in SEAT_KEYS},
                         "lineages": given["lineages"],
                         **({"arc_confirmation": "undetermined"} if given["candidate"]["type"] in G_TYPES else {})}
    tally = collections.Counter
    g_rows = [v for v in verdicts.values() if "arc_confirmation" in v]
    bar = next(r for r in derive.table()["promotion"] if r["id"] == "type_g")["independent_lineages_at_least"]
    return {"stage": STAGE, "test": TEST_STATE, "points": {"release": "absent (D-20261111-c4fa71)", "current": point},
            "unit_outcomes": {"state": "none", "candidates": len(verdicts), "why": UNIT_OUTCOMES_NONE},
            "arc_confirmation": {"state": "undetermined", "passed_as": False, "g_candidates": len(g_rows),
                                 "g_below_lineage_bar": sum(1 for v in g_rows if v["lineages"] < bar),
                                 "lineage_bar": bar, "why": ARC_UNDETERMINED},
            "delivery": {"state": DELIVERY_WAITING, "pairs": waiting,
                         "why": "S5b assembles delivery evidence (lead decision D3); S6 reads it once a wiring commit "
                                "makes it S6's input"},
            "verdicts": verdicts, "not_derived": not_derived,
            "counts": {"derived": len(verdicts), "not_derived": len(not_derived),
                       "admission": dict(tally(v["outcome"]["admission"]["admission"] for v in verdicts.values())),
                       "kind": dict(tally(v["outcome"]["kind"]["kind"] for v in verdicts.values())),
                       "current": dict(tally(v["outcome"]["candidate_diagnosis"]["current"]["diagnosis"]
                                             for v in verdicts.values())),
                       "eligible": sum(1 for v in verdicts.values() if v["outcome"]["eligible"]["eligible"])}}


# ---- design §3.2's gate controls (plan WP-11 J4b, lead decision D5) -----------------------------------------------

GATE_VERDICTS = "judgments/gate-verdicts.json"
GATE_PLANTS = "judgments/gate-controls"
# the judge whose accepted call each control is planted on: the host whose failure it is (tables/controls.json `design`)
GATE_HOSTS = {"truncated_output": "A", "aborted_stream": "B", "incomplete_frame": "B", "refusal": "A",
              "nonzero_exit": "A", "stale_receipt": "A", "mismatched_result_hash": "A", "inherited_profile": "B",
              "contaminated_working_directory": "A", "unattested_model": "A"}
GATE_UNSEALED = ("stale_receipt", "mismatched_result_hash")   # the receipt is the defect, so it is not sealed again
PLANTED_TEXT = "Planted by S6's gate control: an instruction no manifest declares.\n"


def edit_json(path, edit):
    held = json.loads(path.read_text(encoding="utf-8"))
    edit(held)
    path.write_text(json.dumps(held, ensure_ascii=False), encoding="utf-8")


def edit_frames(path, edit):
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    path.write_text("".join(json.dumps(r) + "\n" for r in edit(recs)), encoding="utf-8")


def contaminated_context(host):
    """The effective context a contaminated working directory leaves (design §3.2): an instruction file in the working
    directory, one in its parent and one in the configuration home, a memory file and a skill, none declared."""
    cwd = pathlib.PurePosixPath(host.get("cwd") or "/cell/work")
    digest = hashlib.sha256(PLANTED_TEXT.encode("utf-8")).hexdigest()
    rows = [("Project", cwd / "CLAUDE.md"), ("Project", cwd.parent / "CLAUDE.md"),
            ("User", cwd.parent / "config" / "CLAUDE.md"), ("AutoMem", cwd.parent / "memory" / "MEMORY.md")]
    held = dict(host.get("context") or {})
    return {**held, "instructions": list(held.get("instructions") or []) + [
        {"kind": kind, "path": str(path), "sha256": digest} for kind, path in rows],
        "skills": sorted(set(held.get("skills") or []) | {"planted-gate-skill"})}


def plant(kind, call_dir, other):
    """Plant one §3.2 gate control into a copy of an accepted call (`call_dir`); `other` is the other judge's accepted
    call, whose receipt a stale receipt is."""
    host, result, frames = call_dir / "capture" / "host.json", call_dir / "result.json", call_dir / "capture" / "frames.jsonl"
    if kind == "truncated_output":
        edit_json(host, lambda h: h["assistant"][-1].update(stop_reason="max_tokens"))
    elif kind == "refusal":
        edit_json(host, lambda h: h["assistant"][-1].update(stop_reason="refusal"))
        edit_json(result, lambda r: r.update(stop_reason="refusal"))
    elif kind == "aborted_stream":
        edit_frames(frames, lambda recs: [r for r in recs if r.get("type") != "response.completed"])
    elif kind == "incomplete_frame":
        last = lambda recs: [r for r in recs if r.get("type") == "response.completed"][-1]
        edit_frames(frames, lambda recs: [dict(r, type="response.incomplete", response=dict(
            r.get("response") or {}, incomplete_details={"reason": "max_output_tokens"})) if r is last(recs) else r
            for r in recs])
    elif kind == "nonzero_exit":
        edit_json(call_dir / "call.json", lambda c: c.update(exit_status=1))
    elif kind == "stale_receipt":
        shutil.copyfile(other / "receipt.json", call_dir / "receipt.json")
    elif kind == "mismatched_result_hash":
        result.write_bytes(result.read_bytes() + b"\n")
    elif kind == "inherited_profile":
        edit_json(host, lambda h: h.update(profile="inherited"))
    elif kind == "contaminated_working_directory":
        edit_json(host, lambda h: h.update(context=contaminated_context(h)))
    elif kind == "unattested_model":
        edit_json(host, lambda h: h["assistant"][-1].update(model="claude-haiku-5-5"))
    else:
        raise Refused(f"GATE_CONTROL_UNKNOWN {kind}: S6 plants {sorted(GATE_HOSTS)}")
    if kind not in GATE_UNSEALED:
        seal(call_dir)


def seal(call_dir):
    """The planted call's receipt made again from the directory, as the dispatcher's is (`gate.receipt_evidence` and
    the hashes the gate recomputes), so the planted defect is the only one the gate finds."""
    c = gate.Call(call_dir)
    edit_json(call_dir / "receipt.json", lambda r: r.update(
        packet_sha256=hashlib.sha256(c.packet).hexdigest(), result_sha256=hashlib.sha256(c.result_bytes).hexdigest(),
        exit_status=c.call.get("exit_status"),
        evidence={k: "" if v is None else v for k, v in gate.receipt_evidence(call_dir).items()}))


def verdict_of(call_dir):
    held = gate.accept(call_dir)
    return {"ok": held["ok"], "codes": held["codes"], "failures": held["failures"], "call_id": held["call_id"]}


def gate_stage(run_dir, calls):
    """Design §3.2's ten gate controls (D5): one accepted Judge A call and one accepted Judge B call - the first
    candidate both judges' calls were accepted for - are copied under judgments/gate-controls/<kind>/, each control
    planted on its own host's copy, and the gate judges every copy; the originals are the clean counterparts. Returns
    the document `judgments/gate-verdicts.json` holds: `gate_verdicts` in the shape `controls.evaluate` reads."""
    rows = [r for r in calls if all(h["outcome"] == "accepted" for h in r["seats"].values())]
    out = {"stage": STAGE, "source": None, "gate_verdicts": {}}
    planted_root = run_dir / GATE_PLANTS
    if planted_root.is_dir():
        shutil.rmtree(planted_root)
    if not rows:
        out["why"] = "no candidate has both judges' calls accepted, so no call is copied"
        return out
    source = {who: run_dir / "calls" / rows[0]["seats"][who]["call_id"] for who in SEAT_KEYS}
    out["source"] = {who: d.name for who, d in source.items()}
    clean = {who: verdict_of(d) for who, d in source.items()}
    for kind in [row["kind"] for row in controls.table()["gate"]]:
        who = GATE_HOSTS.get(kind)
        if who is None:
            raise Refused(f"GATE_CONTROL_UNKNOWN {kind}: tables/controls.json names a gate control S6 has no host for")
        copy = planted_root / kind / source[who].name
        shutil.copytree(source[who], copy)
        plant(kind, copy, source["B" if who == "A" else "A"])
        out["gate_verdicts"][kind] = {"host": who, "planted": {**verdict_of(copy), "at": str(copy.relative_to(run_dir))},
                                      "clean": clean[who]}
    return out


# ---- the calls ------------------------------------------------------------------------------------------------

SUMMARY = "judgments/judge.json"
OUTCOMES = ("accepted", "failed", "not_done", "deferred", "budget_stopped")


def judgment_rel(item, who):
    """Where one judge's judgment of a candidate is kept: under the candidate's item name, since a candidate id may hold
    any character (`item_of`)."""
    return f"judgments/{item}/{who}.json"


def check(labels, capacity, reconsider=False):
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
        return answer_problems(shown, stage_read.answer_of(call_dir), first=True, reconsider=reconsider)
    return judged


def attempt_problems(built, limits, schema_bytes, who, code="JUDGE_OVER_CAPACITY"):
    """The bound on one attempt's packet as `Supervisor.item(packet_check=)` asks it, built under the call id its
    reservation gave it and, on a retry, carrying its correction: `code` (JUDGE_OVER_CAPACITY for a judgment, and the
    sweep's and the cross-review's own) when it and the output cap exceed the seat's capacity. A seat whose capacity is
    not measured is not bounded here (D13)."""
    from runlib import stage_read
    size = bound.driver_bytes(built, schema_bytes)[0]
    beyond = beyond_capacity(max(size - stage_read.CORRECTION_ROOM, 0), limits)
    return [f"{code} {who}: this attempt's packet of {size} driver bytes with the output cap exceeds the "
            f"seat's capacity {limits['capacity']}"] if beyond else []


def over_capacity(run_id, built, limits, schema_bytes, code, advice):
    """Before any call of a kind is made: every packet of `built` (`[(item, side, seat, text)]`) whose first attempt,
    with room for its retry's correction and the output cap, exceeds its seat's capacity (`limits[side]`), refused by
    `code` naming them and what the run can change. Codex WP-11 r1 #3: the sweeps and the cross-review were sent with
    no capacity bound at all, and a shard's unit count does not bound its bytes."""
    over = []
    for item, side, seat, text in built:
        made = packet.build(f"{run_id}-{STAGE}-{item}-a1", STAGE, seat, text, schema_bytes)
        size = bound.driver_bytes(made, schema_bytes)[0]
        if beyond_capacity(size, limits[side]):
            over.append(f"{item} ({size} driver bytes, {seat} capacity {limits[side]['capacity']})")
    if over:
        raise Refused(f"{code} S6: {len(over)} packets exceed their seat's capacity with the output cap and a retry's "
                      f"correction ({'; '.join(over[:3])}); {advice}")


# the frame gate.correction puts around the failure lines of the one corrective retry, read from the gate itself
CORRECTION_HEAD, CORRECTION_TAIL = (lambda t: (t[:t.index("- X\n")], t[t.index("- X\n") + 3:]))(
    gate.correction({"failures": ["X"]}))


def corrected_sha256(call_dir, text):
    """The payload hash the receipt of the attempt in `call_dir` is due to carry when that attempt was the one corrective
    retry of `text`: dispatch sends the payload, a newline and `gate.correction` (Supervisor.item), and records the
    payload's own hash as the call's (`call.json` `payload_sha256`). The sent payload's hash when it is exactly that and
    the call says it was made for `text`; None otherwise, so a receipt is then held to the payload S6 built and nothing
    else. Codex WP-11 r1 #1: a successful retry carried its correction's hash and was refused PACKET_DIVERGENCE."""
    held = gate.Call(call_dir)
    sent = packet.split(held.packet)[1]
    base = text.encode("utf-8")
    if sent is None or held.call.get("payload_sha256") != packet.sha256_bytes(base) \
            or not sent.startswith(base + b"\n"):
        return None
    rest = sent[len(base) + 1:].decode("utf-8", "replace")
    framed = rest.startswith(CORRECTION_HEAD) and rest.endswith(CORRECTION_TAIL) \
        and len(rest) > len(CORRECTION_HEAD) + len(CORRECTION_TAIL)
    return packet.sha256_bytes(sent) if framed else None


def stage_receipts(calls):
    """N#1 over the accepted calls: each candidate's two receipts carry the payload S6 built for it and one payload hash
    between them (PACKET_DIVERGENCE), and no two receipts of the stage one packet hash (RECEIPT_STALE). `calls` are
    `(candidate id, seat, call id, receipt, payload sha256[, corrected sha256])`: an attempt that was the corrective
    retry of that payload (`corrected_sha256`) carries its correction's hash, and is held to that one and read as the
    payload S6 built when the seats are compared, because the correction is the gate's answer to that seat's own
    attempt and not a second judgment payload."""
    out, by_candidate = [], {}
    for cid, seat, call_id, receipt, built, *rest in calls:
        corrected = rest[0] if rest else None
        got = (receipt.get("evidence") or {}).get("payload_sha256")
        if corrected is not None and got == corrected:
            receipt = {**receipt, "evidence": {**(receipt.get("evidence") or {}), "payload_sha256": built}}
        elif got != built:
            out.append(f"PACKET_DIVERGENCE {call_id}: its receipt carries the payload hash {str(got)[:12]}, and S6 built "
                       f"{str(built)[:12]} for {cid}")
        by_candidate.setdefault(cid, {})[call_id] = (seat, receipt)
    for held in by_candidate.values():
        out += [p for p in receipt_problems(held) if not p.startswith("RECEIPT_STALE")]
    out += [p for p in receipt_problems({c: (s, r) for _cid, s, c, r, _b, *_rest in calls}) if p.startswith("RECEIPT_STALE")]
    return out


RECEIPT_KINDS = ("sweep", "cross", "reconsider")   # a receipt key's prefix; any other key is a judgment's candidate id


def receipt_counts(calls):
    """How many receipts of each kind `stage_receipts` was given: `{judge, sweep, cross, reconsider}`. It cannot see a
    receipt missing from its list, so the run records what it held to N#1 and a control compares that with the calls
    accepted."""
    kinds = collections.Counter(key.split("/", 1)[0] if key.split("/", 1)[0] in RECEIPT_KINDS else "judge"
                                for key, *_rest in calls)
    return {kind: kinds.get(kind, 0) for kind in ("judge",) + RECEIPT_KINDS}


# S6's golden host: dispatch's (FAKE_HOST) for both hosts, with what its Codex branch does not do
JUDGE_HOST = r'''
"""S6's golden host. It runs dispatch's golden host (FAKE_HOST) and adds two things: a Codex call is answered from the
plan, as FAKE_HOST's Claude branch answers one; and a plan row's `context` names a replayed capture (WP-03's planted
working directories) whose effective context replaces the one the host reports. A row `auto: sweep` answers a sweep
packet from the packet itself: every pair it lists, a partial match (situation yes) where the unit's text holds the
row's `partial_where`, its first pair left out with `drop_first`; `auto: cross` answers a cross-review the same way,
every unit it shows, and with `flag_first_negative` marks the first unit both sweeps found unrelated a match; `auto:
reconsider` answers a reconsideration from itself: every unit it returns, the first a match with `yes_first`, and the
row's `extra` fields added. argv: fake-host host mode spec-json."""
import json, os, pathlib, subprocess, sys
fake, host, mode, spec = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
packet = sys.stdin.buffer.read()
text = packet.decode("utf-8")
call_id = text.splitlines()[0].split(": ", 1)[1]
plan = json.loads(pathlib.Path(spec["answers"]).read_text())
row = next((r for r in plan if all(t in text for t in r["match"])), None)
def block(tag):
    body = text.split("<" + tag + ">\n", 1)[1].split("\n</" + tag + ">", 1)[0]
    return [json.loads(line) for line in body.splitlines()]
if row is not None and row.get("auto") == "sweep":  # every pair the packet lists, a partial match where the text says
    units = {u["unit"]: u["text"] for u in block("units")}
    flagged = lambda u: bool(row.get("partial_where")) and row["partial_where"] in units[u]
    pairs = [{"candidate": c["candidate"], "unit": u, "situation": "yes" if flagged(u) else "no", "action": "no",
              "reason": "a partial match" if flagged(u) else "unrelated"} for c in block("candidates") for u in c["units"]]
    row = {**row, "answer": {"pairs": pairs[1:] if row.get("drop_first") else pairs}}
if row is not None and row.get("auto") == "cross":  # every unit shown, a match where the text says or on the first negative
    shown = block("units")
    first_negative = next((u["unit"] for u in shown if all(m["situation"] == m["action"] == "no"
                                                            for m in u["sweeps"].values())), None) \
        if row.get("flag_first_negative") else None
    flagged = lambda u: (bool(row.get("partial_where")) and row["partial_where"] in u["text"]) or u["unit"] == first_negative
    row = {**row, "answer": {"verdicts": [{"unit": u["unit"], "situation": "yes" if flagged(u) else "no",
                                           "action": "no", "reason": "a match" if flagged(u) else "unrelated"}
                                          for u in shown][(1 if row.get("drop_first") else 0):]}}
def rows_of(tag):
    body = text.split("<" + tag + ">\n", 1)[1].split("\n</" + tag + ">", 1)[0]
    return [] if body.strip() == "none" else [json.loads(line) for line in body.splitlines()]
if row is not None and row.get("auto") == "reconsider":  # every returned unit, the first a match with yes_first
    units, quotes = rows_of("units"), [q["evidence_id"] for c in rows_of("claims") for q in c.get("quotes", [])][:1]
    yes = [u["unit_id"] for u in units][:1] if row.get("yes_first") else []
    row = {**row, "answer": {"units": [
        {"unit": u["unit_id"], "situation": "yes" if u["unit_id"] in yes else "no",
         "action": "yes" if u["unit_id"] in yes else "no", "reason": "one line",
         "quote": u["text"][:12] if u["unit_id"] in yes else ""} for u in units],
        "matching_units": [{"unit": u, "following": "followed", "following_evidence_ids": quotes, "contribution": "helped",
                            "contribution_evidence_ids": quotes} for u in yes], **(row.get("extra") or {})}}
if row is not None and row.get("auto") in ("sweep", "cross", "reconsider"):
    held = pathlib.Path(os.environ["DISTILL_CELL"]) / "judge-host-plan.json"
    held.write_text(json.dumps([{"match": row["match"], "answer": row["answer"]}]))
    spec = {**spec, "answers": str(held)}
done = subprocess.run([sys.executable, fake, host, mode, json.dumps(spec)], input=packet, stdout=subprocess.PIPE)
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
            summary["sweep_upper_bound"] = upper_bound(run_dir, declaration, sorted(packets), seats_path)
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
        calls, receipts, judgments = [], [], {}
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
                    judgment = labels.resolve(gate.accepted(call_dir, judged=True))
                    judgments.setdefault(cid, {})[who] = judgment
                    records.write_json(run_dir, run_dir / rel, {
                        "candidate_id": cid, "item": item, "judge": who, "seat": seat, "call_id": call_id,
                        "payload_sha256": measured["payload_sha256"], "packet_sha256": receipt.get("packet_sha256"),
                        "judgment": judgment})
                    stage.output(rel)
                    receipts.append((cid, seat, call_id, receipt, measured["payload_sha256"],
                                     corrected_sha256(call_dir, text)))
                    held.update(call_id=call_id, judgment=rel)
                row["seats"][who] = held
            calls.append(row)
        sources = {r["candidate_id"]: r["source"] for r in summary["packets"]}
        swept, sweep_receipts = sweep_stage(run_dir, stage, supervisor, declaration, sorted(packets), judgments, sources,
                                            caps, tranche)
        crossed, cross_receipts = cross_stage(run_dir, stage, supervisor, declaration, swept, item_of, caps, tranche)
        again, again_receipts = reconsider_stage(run_dir, stage, supervisor, declaration, summary, packets, judgments,
                                                 crossed, caps, tranche)
        held_receipts = receipts + sweep_receipts + cross_receipts + again_receipts
        problems = stage_receipts(held_receipts)
        if problems:
            raise Refused("\n".join(problems))
        derived = derive_stage(run_dir, summary, judgments, swept, again)
        records.write_json(run_dir, run_dir / DERIVATIONS, derived)
        stage.output(DERIVATIONS)
        gated = gate_stage(run_dir, calls)
        records.write_json(run_dir, run_dir / GATE_VERDICTS, gated)
        stage.output(GATE_VERDICTS)
        outcomes = [held["outcome"] for row in calls for held in row["seats"].values()]
        swept_outcomes = [held["outcome"] for row in swept["calls"] for held in row["seats"].values()]
        swept["counts"] = {**{o: swept_outcomes.count(o) for o in OUTCOMES},
                           "reused": sum(1 for row in swept["calls"] for held in row["seats"].values() if held["reused"])}
        crossed_outcomes = [row["outcome"] for row in crossed["calls"]]
        crossed["counts"] = {**{o: crossed_outcomes.count(o) for o in OUTCOMES},
                             "reused": sum(1 for row in crossed["calls"] if row["reused"])}
        again_outcomes = [held["outcome"] for row in again["calls"] for held in row["seats"].values()]
        again["counts"] = {**{o: again_outcomes.count(o) for o in OUTCOMES},
                           "reused": sum(1 for row in again["calls"] for held in row["seats"].values() if held["reused"])}
        summary.update(dry=False, calls=calls, sweeps=swept, cross_review=crossed, reconsiderations=again,
                       receipts_checked=receipt_counts(held_receipts),
                       gate_controls={"file": GATE_VERDICTS, "source": gated["source"],
                                      "planted": len(gated["gate_verdicts"]),
                                      "planted_rejected": sorted(k for k, v in gated["gate_verdicts"].items()
                                                                 if v["planted"]["ok"] is False),
                                      "clean_accepted": all(v["clean"]["ok"] for v in gated["gate_verdicts"].values()),
                                      **({"why": gated["why"]} if "why" in gated else {})},
                       derivations={"file": DERIVATIONS, "counts": derived["counts"], "delivery": derived["delivery"],
                                    "unit_outcomes": derived["unit_outcomes"],
                                    "arc_confirmation": derived["arc_confirmation"]},
                       interrupted=interrupted, tranche=tranche,
                       counts={**{o: outcomes.count(o) for o in OUTCOMES},
                               "reused": sum(1 for row in calls for held in row["seats"].values() if held["reused"]),
                               "judged_by_both": sum(1 for row in calls
                                                     if all(h["outcome"] == "accepted" for h in row["seats"].values()))},
                       density_table=dispatch.measured_table(run_dir))
        records.write_json(run_dir, run_dir / SUMMARY, summary)
        stage.output(SUMMARY)
        if any(o != "accepted" for o in outcomes + swept_outcomes + crossed_outcomes + again_outcomes) \
                or crossed["not_reviewed"] or again["missing"]:
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
        sw = summary["sweeps"]
        cl = sw.get("claims") or {}
        lines.append(f"absence claims ({'swept' if cl.get('swept') else 'not swept'}): {cl.get('count')} of "
                     f"{cl.get('judged_by_both')} candidates judged by both - "
                     + ", ".join(f"{k} {v['claims']} of {v['judged_by_both']}" for k, v in (cl.get("by_kind") or {}).items())
                     + "; current point " + ("complete" if (cl.get("reference") or {}).get("complete") else "incomplete")
                     + f" under the {(cl.get('reference') or {}).get('policy')} policy, layers "
                     + ", ".join(f"{k}={v}" for k, v in ((cl.get("reference") or {}).get("layers") or {}).items()))
        if not sw["complete"]:
            lines.append(f"sweeps: none - {sw['why']}")
        else:
            c = sw["counts"]
            lines.append(f"sweeps ({sw['policy']} policy): {len(sw['absent'])} absence claims in {len(sw['groups'])} groups, "
                         f"{sum(len(g['shards']) for g in sw['groups'])} shards; calls " + ", ".join(f"{o} {c[o]}" for o in OUTCOMES)
                         + f"; {c['reused']} answered by an earlier accepted attempt; {len(sw['not_judged_by_both'])} "
                           "candidates not swept because a judge did not judge them")
            cr = summary["cross_review"]
            lines.append(f"cross-review by Judge B: {len(cr['reviewed'])} absence claims reviewed, {len(cr['not_reviewed'])} "
                         f"not; calls " + ", ".join(f"{o} {cr['counts'][o]}" for o in OUTCOMES))
            dv = summary["derivations"]["counts"]
            lines.append(f"derivations: {dv['derived']} candidates derived, {dv['not_derived']} not; admission "
                         + ", ".join(f"{k} {n}" for k, n in sorted(dv["admission"].items())) + "; current diagnosis "
                         + ", ".join(f"{k} {n}" for k, n in sorted(dv["current"].items())) + f"; {dv['eligible']} eligible; "
                         f"{summary['derivations']['delivery']['pairs']} (session, unit) pairs {DELIVERY_WAITING}; no unit "
                         f"outcome for {summary['derivations']['unit_outcomes']['candidates']} candidates (release not "
                         f"judged); arc confirmation undetermined for {summary['derivations']['arc_confirmation']['g_candidates']} "
                         "type G candidates")
            gc = summary["gate_controls"]
            lines.append(f"gate controls: {gc['planted']} planted on copies of accepted calls, {len(gc['planted_rejected'])} "
                         f"rejected by the gate; clean counterparts accepted: {gc['clean_accepted']}")
            rc = summary["reconsiderations"]
            after = collections.Counter(r["diagnosis"] for r in rc["reconsidered"])
            lines.append(f"reconsidered by both judges: {len(rc['reconsidered'])} absence claims (" + ", ".join(
                f"{d} {n}" for d, n in sorted(after.items())) + f"), {len(rc['not_reconsidered'])} missing a "
                "reconsideration; calls " + ", ".join(f"{o} {rc['counts'][o]}" for o in OUTCOMES))
    else:
        b = summary["sweep_upper_bound"]
        lines.append(f"sweep upper bound ({b['basis']}): {b['groups']} groups, {b['shards']} shards, {b['packets']} calls, "
                     f"{b['pairs']} pairs, {b['payload_bytes']} payload bytes; input "
                     + ", ".join(f"{side} {n}" for side, n in b["input_tokens_at_j0_density"].items())
                     + f" tokens at {b['density']} bytes a token; output at most {b['output_tokens_at_most']} tokens")
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


WIDE_TOPICS = ("release", "budget", "review", "schema", "ledger", "window")


def fx_library(wide=0):
    """S5's fixture library with what S2's inventory now publishes of each unit (D-20261111-92d81a): its heading, its
    block and its edges. One unit is enclosed by a frontmatter line of its file (a reference unit S5 does not index), and
    reaches a unit of another file and an unresolved mention. `wide` adds that many catalog units, each its own text, so
    an absence claim has more than NEGATIVES units both sweeps find unrelated (J3b)."""
    front = lifecycle_intake.fx_unit("u-front", "description: when a push reaches a shared remote", cls="reference",
                                     path="claude/guides/u-push.md")
    extra = [lifecycle_intake.fx_unit(f"u-wide-{n:03d}", f"Note step {n} of the {WIDE_TOPICS[n % len(WIDE_TOPICS)]} "
                                                         "routine in its dated log.") for n in range(1, wide + 1)]
    units = [dict(u) for u in lifecycle_intake.FX_LIBRARY] + [front] + extra
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


def fx_seats(root, capacity_a=None, name="seats.json", capacities=None, codex_allowance=None):
    """A seats file as D13 leaves the judges' seats until their first live calls: seats.json's own, with Judge A's
    capacity and Claude's allowance measured and Judge B's host allowance and seat capacity not; `capacity_a` replaces
    Judge A's capacity. `capacities` (`{seat: tokens}`) declares a capacity for other seats at their host's version, and
    `codex_allowance` measures the Codex host's, so a sweep's or a cross-review's seat can be bounded in a control."""
    held = json.loads(gate.SEATS.read_text(encoding="utf-8"))
    if capacity_a is not None:
        held["seat_capacity"]["claude:claude-opus-5-5/high"]["context_capacity"] = capacity_a
    held["hosts"]["codex"]["host_allowance"] = {"hermetic": {"allowance_tokens": None, "measured": False,
                                                             "basis": "unmeasured: D13"}}
    held["seat_capacity"].pop("codex:gpt-6-astra/xhigh", None)
    for seat, tokens in (capacities or {}).items():
        held["seat_capacity"][seat] = {"context_capacity": tokens, "basis": "planted by a control",
                                       "host_version": held["hosts"][seat.partition(":")[0]]["version"]}
    if codex_allowance is not None:
        held["hosts"]["codex"]["host_allowance"] = {"hermetic": {"allowance_tokens": codex_allowance, "measured": True,
                                                                 "basis": "planted by a control"}}
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
    control("the sweep template is one packet.TEMPLATES lists, and its placeholders are the candidates, the inventory and "
            "the units", SWEEP_TEMPLATE in packet.TEMPLATES
            and guarded(lambda: packet.template_fields(SWEEP_TEMPLATE), []) == ["candidates", "inventory", "units"],
            f"{packet.TEMPLATES}")
    control("the cross-review template is one packet.TEMPLATES lists, and its placeholders are the candidate and the units",
            CROSS_TEMPLATE in packet.TEMPLATES and guarded(lambda: packet.template_fields(CROSS_TEMPLATE), []) == ["candidate", "units"],
            f"{packet.TEMPLATES}")
    control("the reconsideration template is one packet.TEMPLATES lists, and its placeholders are the candidate, its "
            "claims, the context and the units", RECONSIDER_TEMPLATE in packet.TEMPLATES
            and guarded(lambda: packet.template_fields(RECONSIDER_TEMPLATE), []) == ["candidate", "claims", "context", "units"],
            f"{packet.TEMPLATES}")
    # ---- the reconsideration's shape (J3c): units and matching units only ------------------------------------------
    held_rs, projected = guarded(reconsider_schema, {}), guarded(reconsider_projection, None)
    control("J3c: reconsider.schema.json is the judge schema's units and matching units with the definitions they reach, "
            "closed, and nothing else", held_rs == projected and projected is not None
            and sorted(held_rs.get("properties", {})) == sorted(RECONSIDER_FIELDS)
            and held_rs.get("additionalProperties") is False and held_rs.get("required") == list(RECONSIDER_FIELDS))
    drifted = json.loads(json.dumps(schema()))
    drifted["$defs"]["unit_judgment"].setdefault("properties", {})["confidence"] = {"type": "string"}
    control("control: a field added to the judge schema's unit judgment makes the reconsideration schema stale",
            guarded(lambda: reconsider_projection(drifted), None) != held_rs)
    control("control: a candidate-level field added to reconsider.schema.json is not its projection",
            {**held_rs, "properties": {**held_rs.get("properties", {}), "requirements": schema()["properties"]["requirements"]}}
            != projected)
    sample_r = {"units": [{"unit": "n1", "situation": "no", "action": "no", "reason": "one line", "quote": ""}],
                "matching_units": []}
    rs_validator = guarded(lambda: validate.compile_schema(held_rs), None)
    control("J3c: the reconsideration schema takes a units-only answer and refuses one carrying a candidate-level field",
            rs_validator is not None and not validate.violations(rs_validator, sample_r)
            and all(validate.violations(rs_validator, {**sample_r, f: fx_answer()[f]}) for f in RECONSIDER_REFUSED))
    shown_r = {"units": {"n1": "Feed the zebra at noon."}, "quotes": ["q1"], "entries": []}
    control("J3c: a units-only reconsideration answer is no problem", not answer_problems(shown_r, sample_r, reconsider=True))
    for field in RECONSIDER_REFUSED:
        named(f"control: a reconsideration answering `{field}` is FIELD_UNEXPECTED",
              answer_problems(shown_r, {**sample_r, field: fx_answer()[field]}, reconsider=True), "FIELD_UNEXPECTED")
    judge_md, recon_md = (guarded(lambda n=n: packet.template_text(n), "") for n in (TEMPLATE, RECONSIDER_TEMPLATE))
    unit_rules = [t[t.find("For every unit in <units>, exactly once"):t.find("`text`; otherwise the empty string.")]
                  for t in (judge_md, recon_md)]
    control("J3c: the reconsideration asks for each unit's judgment in the judgment packet's own words",
            unit_rules[0] and unit_rules[0] == unit_rules[1] and "For the candidate" not in recon_md
            and "<ledger_entries>" not in recon_md)
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
            dv_first = guarded(lambda: records.read_json(called / DERIVATIONS), {})
            control("J4a: a candidate a judge's call did not finish for is not derived, and is named",
                    sorted(r["candidate_id"] for r in dv_first.get("not_derived", [])
                           if r["why"] == "a judge's call did not finish") == sorted({tainted, unjudged})
                    and not {tainted, unjudged} & set(dv_first.get("verdicts", {}))
                    and len(dv_first.get("verdicts", {})) == len(judged_ids) - 2, f"{dv_first.get('not_derived')}")
            made = {d.name for d in (called / "calls").iterdir()} if (called / "calls").is_dir() else set()
            given_seen, kept_given = {}, globals()["derivation_given"]

            def recording(run_dir, candidate, *rest):
                held = kept_given(run_dir, candidate, *rest)
                given_seen[candidate["candidate_id"]] = json.loads(json.dumps(held))
                return held
            globals()["derivation_given"] = recording   # S6's own derivation, its inputs kept as it made them
            try:
                second = guarded(lambda: run(called, supervisor(called, root / "cells-2", clean_plan)),
                                 lambda e: {"problem": repr(e)})
            finally:
                globals()["derivation_given"] = kept_given
            dv_second = guarded(lambda: records.read_json(called / DERIVATIONS), {})
            from_disk = {cid: guarded(lambda cid=cid: given_from_run(called, cid), lambda e: {"problem": repr(e)})
                         for cid in given_seen}
            differs = sorted(cid for cid in given_seen if from_disk[cid] != given_seen[cid])
            control("K5: S6's derivation and a recomputation from S6's own files on disk get identical inputs for "
                    "every candidate S6 derived", bool(given_seen) and set(given_seen) == set(dv_second.get("verdicts", {}))
                    and not differs, f"{len(given_seen)} derived, differing {differs[:3]}")
            replayed = sorted(cid for cid in given_seen if guarded(lambda cid=cid: derive.unit_outcome(
                from_disk[cid], {}, TEST_STATE), {}) != dv_second.get("verdicts", {}).get(cid, {}).get("outcome"))
            control("K5: and derive.unit_outcome over the input from disk reproduces each stored outcome",
                    bool(given_seen) and not replayed, f"not reproduced {replayed[:3]}")
            # the golden's two judges answer alike, so a seat read in place of the other would pass the comparison
            # above: B's file is changed in a copy and must reach B's side of the input, and only B's
            seat_root = root / "k5-seats"
            some_cid = sorted(given_seen)[0] if given_seen else None
            seat_marks = {}
            if some_cid is not None:
                for rel in GIVEN_INPUTS + (SUMMARY,) + tuple(given_artifacts(called, some_cid)):
                    (seat_root / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(called / rel, seat_root / rel)
                b_rel = judgment_rel(item_of(some_cid), "B")
                b_held = records.read_json(seat_root / b_rel)
                name = sorted(b_held["judgment"]["requirements"])[0]
                b_held["judgment"]["requirements"][name]["mark"] = "uncertain"
                (seat_root / b_rel).write_text(json.dumps(b_held), encoding="utf-8")
                seated = guarded(lambda: given_from_run(seat_root, some_cid), {})
                seat_marks = {who: ((seated.get("judges") or {}).get(who) or {}).get("requirements", {}).get(name)
                              for who in SEAT_KEYS}
            control("K5: each judge's side of the input is read from that judge's own file",
                    seat_marks.get("B") == "uncertain" and seat_marks.get("A") not in (None, "uncertain"), f"{seat_marks}")
            control("K5: given_artifacts names both judges' judgment files, each an output S6's record holds",
                    bool(given_seen) and all(set(given_artifacts(called, cid)) <= {o["artifact"] for o in guarded(
                        lambda: records.read_json(records.record_path(called, STAGE)), {}).get("outputs", [])}
                        and len(given_artifacts(called, cid)) >= 2 for cid in given_seen), "")
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
            # a retry's due hash, over call directories made here: only the payload S6 built, a newline and the gate's own
            # correction frame give one (Codex WP-11 r1 #1)
            def sent_as(name, body, made_for="base payload"):
                d = root / "sent" / name
                d.mkdir(parents=True, exist_ok=True)
                (d / "packet.md").write_bytes(packet.build("c-a2", STAGE, "s", body))
                (d / "call.json").write_text(json.dumps({"payload_sha256": packet.sha256_bytes(made_for.encode("utf-8"))}),
                                             encoding="utf-8")
                return guarded(lambda: corrected_sha256(d, "base payload"), "RAISED")
            fixed = "base payload\n" + gate.correction({"failures": ["UNIT_UNJUDGED u1"]})
            control("Codex WP-11 r1 #1: a retry's due hash is given for the payload and the gate's correction, and not for "
                    "the payload with anything else after it, nor for a call made for another payload",
                    sent_as("framed", fixed) == packet.sha256_bytes(fixed.encode("utf-8"))
                    and sent_as("other-tail", "base payload\nsomething else entirely\n") is None
                    and sent_as("head-only", "base payload\n" + CORRECTION_HEAD) is None
                    and sent_as("other-base", fixed, made_for="another payload") is None
                    and sent_as("first", "base payload") is None)
            # ---- design §3.2's gate controls (J4b, D5) ---------------------------------------------------------------
            gated = guarded(lambda: records.read_json(called / GATE_VERDICTS), {})
            gv = gated.get("gate_verdicts", {})
            table_gate = {row["kind"]: row["code"] for row in controls.table()["gate"]}
            control("J4b: every gate control the table declares has a host S6 plants it on, and S6 plants no other",
                    set(GATE_HOSTS) == set(table_gate) and len(table_gate) == 10, f"{sorted(set(GATE_HOSTS) ^ set(table_gate))}")
            source_g = gated.get("source") or {}
            control("J4b (D5): the ten gate controls are planted on copies of one accepted Judge A call and one accepted "
                    "Judge B call, each on its own host's copy under judgments/gate-controls/<kind>/",
                    sorted(gv) == sorted(table_gate) and all(
                        v["host"] == GATE_HOSTS[k] and v["planted"]["call_id"] == source_g.get(v["host"])
                        and v["planted"]["at"] == f"{GATE_PLANTS}/{k}/{source_g.get(v['host'])}"
                        and (called / v["planted"]["at"]).is_dir() for k, v in gv.items())
                    and f"-{STAGE}-" in source_g.get("A", "") and "-A-a" in source_g.get("A", "")
                    and "-B-a" in source_g.get("B", ""), f"{source_g}")
            control("J4b (§3.2): the gate rejects every planted copy by the code the table gives it, and accepts both "
                    "originals as the clean counterparts", gv and all(
                        v["planted"]["ok"] is False and table_gate[k] in v["planted"]["codes"] and v["clean"]["ok"] is True
                        for k, v in gv.items()), f"{[(k, v['planted']['codes']) for k, v in gv.items()]}")
            control("J4b: a planted call whose receipt is not itself the defect is sealed again, so the gate finds no "
                    "receipt disagreement in it", gv and all(
                        not any(line.startswith("RECORD_INTEGRITY receipt") for line in v["planted"]["failures"])
                        for k, v in gv.items() if k not in GATE_UNSEALED), "")
            originals_ok = all(guarded(lambda who=who: gate.accept(called / "calls" / source_g[who])["ok"], False)
                               for who in ("A", "B")) if source_g else False
            control("J4b: planting leaves the original calls as they were", originals_ok)
            evaluated = guarded(lambda: controls.evaluate({"incomplete": [], "planted": [], "gate": [
                {"kind": k, "code": c} for k, c in table_gate.items()]}, {}, gv, [], {}), {"problems": ["RAISED"]})
            control("J4b (D4): controls.evaluate reads S6's gate verdicts and finds every gate control given its verdict",
                    not evaluated["problems"] and len(evaluated.get("gate", [])) == 10
                    and all(g["ok"] for g in evaluated["gate"]), f"{evaluated.get('problems')}")
            no_pair = root / "no-pair"
            no_pair.mkdir()
            alone = guarded(lambda: gate_stage(no_pair, [{"seats": {"A": {"outcome": "accepted"}, "B": {"outcome": "failed"}}}]),
                            {})
            control("J4b: with no candidate both judges' calls were accepted for, nothing is planted and the verdicts say why",
                    alone.get("gate_verdicts") == {} and alone.get("source") is None and "no candidate" in alone.get("why", ""),
                    f"{alone}")
            control("J4b: the run summary counts the planted controls the gate rejected",
                    second.get("gate_controls", {}).get("planted") == 10
                    and second.get("gate_controls", {}).get("planted_rejected") == sorted(table_gate)
                    and second.get("gate_controls", {}).get("clean_accepted") is True, f"{second.get('gate_controls')}")
            unbudgeted = copy_of("unbudgeted")
            said = refusal(lambda: run(unbudgeted, supervisor(unbudgeted, root / "cells-ub", clean_plan)))
            control("control: a run that declares no budget.per_stage.S6 is refused BUDGET_UNDECLARED S6 at the first "
                    "reservation, before any S6 call", said.startswith("BUDGET_UNDECLARED S6")
                    and not any(f"-{STAGE}-" in d.name for d in (unbudgeted / "calls").iterdir()), said[:200])
            dv_called = guarded(lambda: records.read_json(called / DERIVATIONS), {})
            gap_row = next(r for r in derive.table()["candidate_diagnosis"] if not r.get("lifecycle") and r["if_any_unit"] is None)
            currents = [v["outcome"]["candidate_diagnosis"]["current"] for v in dv_called.get("verdicts", {}).values()]
            control("J4a: at an incomplete current point no candidate is a gap - a candidate no unit matches is the gap "
                    "row's incomplete answer", dv_called.get("points", {}).get("current", {}).get("complete") is False
                    and currents and not any(c["diagnosis"] == "gap" for c in currents)
                    and any(c["row"] == gap_row["id"] and c["diagnosis"] == gap_row["incomplete"] for c in currents),
                    f"{collections.Counter((c['diagnosis'], c['row']) for c in currents)}")
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
                    bool(sent) and not guarded(lambda: attempt_problems(sent, limits_a, held_schema_bytes, "A"), ["RAISED"]), "")
            control("control: an attempt's packet past the seat's capacity is JUDGE_OVER_CAPACITY by the attempt's bound",
                    any(p.startswith("JUDGE_OVER_CAPACITY A") for p in guarded(lambda: attempt_problems(
                        sent, {**limits_a, "capacity": 1000}, held_schema_bytes, "A"), [])), "")
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
            # ---- the absence sweeps (J3a, done-when 6) --------------------------------------------------------------
            sw_second = second.get("sweeps") or {}
            control("done-when 6: at a reference point the absence policy reads as incomplete, no absence claim stands and "
                    "nothing is swept", sw_second.get("complete") is False and sw_second.get("calls") == []
                    and sw_second.get("absent") == [] and "absence unknown" in sw_second.get("why", ""), f"{sw_second}")
            # the expectation is read from the judgments on disk, not through absent_candidates: a candidate whose every
            # unit both judges marked situation no and action no is an absence claim whatever the policy
            claims = sw_second.get("claims") or {}

            def marked_none(cid):
                held = [guarded(lambda w=w: records.read_json(called / judgment_rel(item_of(cid), w))["judgment"], None)
                        for w in SEAT_KEYS]
                return all(held) and all(u.get("situation") == "no" and u.get("action") == "no"
                                         for h in held for u in h["units"])
            planted_claims = sorted(c for c in judged_ids if marked_none(c))
            inventory_layers = {row["layer"]: row["status"] for row in
                                guarded(lambda: records.read_json(called / "inventory" / "current.json"), {}).get("layers") or []}
            control("J3a (D-20261111-eaa2a8): at an incomplete point the judges' absence claims are still named and "
                    "counted per candidate kind beside the number judged, with the point's state and every layer's "
                    "status, and no sweep is called", bool(planted_claims)
                    and claims.get("candidates") == planted_claims and claims.get("count") == len(planted_claims)
                    and sum(v.get("claims", 0) for v in (claims.get("by_kind") or {}).values()) == len(planted_claims)
                    and claims.get("swept") is False and (claims.get("reference") or {}).get("complete") is False
                    and (claims.get("reference") or {}).get("layers") == inventory_layers and bool(inventory_layers)
                    and sw_second.get("calls") == [] and sw_second.get("absent") == [], f"{claims} {planted_claims}")
            ub = dry.get("sweep_upper_bound") or {}
            index = stage_retrieve.UnitIndex(records.read_json(gold / "inventory" / "current.json")["units"])
            dry_judged = [r["candidate_id"] for r in dry.get("packets", [])]
            # computed here from the index itself, not through remaining_of, so a revert of it cannot move both sides
            ub_remaining = {c: sorted(rep for rep in index.copies if index.layer_of[rep] == "catalog"
                                      and rep not in {index.rep_of.get(r["unit_id"], r["unit_id"])
                                                      for r in rows_of[c]["retrieved_units"]}) for c in dry_judged}
            ub_groups = shard_plan(ub_remaining, SWEEP_DEFAULTS["candidates_per_shard"], SWEEP_DEFAULTS["shard_units"])
            with_pairs = sum(1 for g in ub_groups for sh in g["shards"] if sh["pairs"])
            control("dry: the sweep's upper bound is every judged candidate as a gap over the catalog layer less its "
                    "retrieved units, labelled as the bound, in groups, shards, calls, pairs, bytes and tokens at J0's density",
                    ub.get("basis") == UPPER_BOUND_BASIS and ub.get("candidates") == len(dry_judged)
                    and ub.get("groups") == len(ub_groups) == math.ceil(len(dry_judged) / SWEEP_DEFAULTS["candidates_per_shard"])
                    and ub.get("packets") == 2 * with_pairs and ub.get("pairs") == sum(len(v) for v in ub_remaining.values())
                    and all(ub.get("input_tokens_at_j0_density", {}).get(side) == math.ceil(ub["driver_bytes"][side] / J0_DENSITY)
                            for side in ("a", "b")) and ub.get("output_tokens_at_most") == ub.get("packets", 0) * 20_000,
                    f"{ub}")
            # a golden run whose current reference point is complete, three formed candidates judged with no unit that
            # matches, so they and the candidates S5 retrieved nothing for are absence claims
            whole = guarded(lambda: stage_retrieve.fx_gold(root / "whole",
                                                           stage_retrieve.fx_current(fx_library(wide=70), complete=True)),
                            lambda e: e)
            if isinstance(whole, Exception):
                failures.append(f"the complete golden run could not be made: {whole!r}")
            else:
                declare.amend(whole, [("budget.per_stage.S6", 20_000_000),
                                      ("sweeps", {"shard_units": 40, "candidates_per_shard": 3})],
                              "S6's golden budget and small shards (WP-11 J3a)", scope=["S5", "S6"])
                stage_retrieve.run(whole, "aa" * 8)
                whole_plan_root = root / "whole-planner"
                shutil.copytree(whole.parent, whole_plan_root)
                made_gaps = []

                def no_match(cid, who, row):
                    if cid in made_gaps or (len(made_gaps) < 3 and cid.startswith("k-") and row["answer"]["units"]):
                        if cid not in made_gaps:
                            made_gaps.append(cid)
                        for u in row["answer"]["units"]:
                            u.update(situation="no", action="no", quote="")
                        row["answer"]["matching_units"] = []
                # done-when 2 (J4a): the next candidate both judges mark `bounded` uncertain, the one after both mark
                # `consequence` unmet; every other requirement of every candidate both mark met
                planted_marks = {}

                def plan_edit(cid, who, row):
                    no_match(cid, who, row)
                    if cid not in made_gaps and (cid in planted_marks or len(planted_marks) < 2):
                        mark = planted_marks.setdefault(cid, ("uncertain", "bounded") if not planted_marks
                                                        else ("unmet", "consequence"))
                        row["answer"]["requirements"][mark[1]] = {"mark": mark[0], "reason": "planted"}
                whole_plan, whole_packets = fx_judge_plan(whole_plan_root / whole.name, root / "plan-whole.json", plan_edit)
                # each sweep flags its own unit, so a flag is what either raised, not both (J3b)
                sweep_rows = [{"match": [f"SEAT: {seat}"], "auto": "sweep", "partial_where": where}
                              for seat, where in (("claude:claude-sonnet-5-5/medium", "glob"),
                                                  ("codex:gpt-6-luna/medium", "Note step 3 of"))]
                # Judge B's cross-review: every unit judged, a match on the first unit neither sweep flagged (J3b, J3c)
                sweep_rows.append({"match": ["SEAT: codex:gpt-6-astra/xhigh", "Two checkers then"], "auto": "cross",
                                   "flag_first_negative": True})
                # the reconsiderations (J3c): the first claim's first returned unit both judges now find matching, the
                # second's only Judge A, every other's none
                claims_known = sorted(c for c, (labels, _t) in whole_packets.items() if c in made_gaps or not labels.units)
                recon_of = {n: c for n, c in enumerate(claims_known[:3])}
                if len(recon_of) == 3:
                    sweep_rows += [{"match": [f"-{STAGE}-{item_of(recon_of[0])}-{RECONSIDER}{who}-a"], "auto": "reconsider",
                                    "yes_first": True} for who in ("A", "B")]
                    sweep_rows.append({"match": [f"-{STAGE}-{item_of(recon_of[1])}-{RECONSIDER}A-a"], "auto": "reconsider",
                                       "yes_first": True})
                sweep_rows += [{"match": [f"-{RECONSIDER}{who}-a"], "auto": "reconsider"} for who in ("A", "B")]
                judge_rows = json.loads(pathlib.Path(whole_plan).read_text(encoding="utf-8"))
                pathlib.Path(whole_plan).write_text(json.dumps(judge_rows + sweep_rows), encoding="utf-8")
                # the same run before any S6 call, for the corrective-retry runs below (Codex WP-11 r1 #1)
                retry_base = root / "retry-base"
                shutil.copytree(whole.parent, retry_base)
                defect_sweep_plan = root / "plan-whole-defect.json"
                defect_sweep_plan.write_text(json.dumps(
                    judge_rows + [{"match": [f"-{STAGE}-sweep-g001-s001-b-a"], "auto": "sweep", "drop_first": True}] + sweep_rows),
                    encoding="utf-8")
                swept_run = guarded(lambda: run(whole, supervisor(whole, root / "cells-8", defect_sweep_plan)),
                                    lambda e: {"problem": repr(e)})
                sw = swept_run.get("sweeps") or {}
                first_record = guarded(lambda: records.read_json(records.record_path(whole, STAGE)), {})
                dropped = next((row["seats"].get("b", {}) for row in sw.get("calls", [])
                                if (row["group"], row["shard"]) == ("g001", "s001")), {})
                control("J3a: a sweep answer that leaves a listed pair out fails the stage's check on both attempts, by name, "
                        "and leaves the record partial", dropped.get("outcome") == "failed" and len(dropped.get("attempts", [])) == 2
                        and all(any(line.startswith("SWEEP_PAIR_MISSING") for line in a["stage_check"] or [])
                                for a in dropped.get("attempts", [])) and first_record.get("status") == "partial",
                        f"{dropped} {first_record.get('status')}")
                first_cross = swept_run.get("cross_review") or {}
                g001 = next((g["candidates"] for g in sw.get("groups", []) if g["group"] == "g001"), [])
                control("J3b: an absence claim whose group's sweeps did not all finish is not cross-reviewed, and is named",
                        g001 and sorted(r["candidate_id"] for r in first_cross.get("not_reviewed", [])
                                        if r["why"] == "a sweep of its group did not finish") == sorted(g001)
                        and not set(g001) & set(first_cross.get("reviewed", [])), f"{first_cross.get('not_reviewed')} {g001}")
                # the second run: the sweeps whole, and one absence claim's cross-review leaving a unit out
                cross_defect = root / "plan-whole-cross-defect.json"
                cross_defect.write_text(json.dumps(judge_rows + [
                    {"match": [f"-{STAGE}-{item_of(claims_known[0])}-X-a"], "auto": "cross", "drop_first": True}] + sweep_rows),
                    encoding="utf-8")
                swept_run = guarded(lambda: run(whole, supervisor(whole, root / "cells-8b", cross_defect)),
                                    lambda e: {"problem": repr(e)})
                second_record = guarded(lambda: records.read_json(records.record_path(whole, STAGE)), {})
                short_cross = next((r for r in (swept_run.get("cross_review") or {}).get("calls", [])
                                    if r["candidate_id"] == claims_known[0]), {})
                control("J3b: a cross-review that leaves a unit it was shown unjudged fails the stage's check on both attempts, "
                        "by name, and leaves the record partial", short_cross.get("outcome") == "failed"
                        and len(short_cross.get("attempts", [])) == 2
                        and all(any(line.startswith("CROSS_UNIT_MISSING") for line in a["stage_check"] or [])
                                for a in short_cross.get("attempts", [])) and second_record.get("status") == "partial",
                        f"{short_cross} {second_record.get('status')}")
                sw = swept_run.get("sweeps") or {}
                whole_rows = {r["candidate_id"]: r for r in records.read_json(whole / "checks.json")["candidates"]}
                expected = sorted(c for c, (labels, _t) in whole_packets.items() if c in made_gaps or not labels.units)
                control("J3a: the absence claims are the judged candidates no unit matches by both judges - the three planted "
                        "and every one S5 retrieved nothing for", sw.get("complete") is True and sw.get("absent") == expected
                        and len(made_gaps) == 3, f"{sw.get('absent')} {expected}")
                whole_index = stage_retrieve.UnitIndex(records.read_json(whole / "inventory" / "current.json")["units"])
                inventory_hash = packet.sha256_bytes((whole / "inventory" / "current.json").read_bytes())
                want = {c: sorted(rep for rep in whole_index.copies
                                  if rep not in {whole_index.rep_of.get(r["unit_id"], r["unit_id"])
                                                 for r in whole_rows[c]["retrieved_units"]}) for c in expected}
                kept_sw = {}
                for g in sw.get("groups", []):
                    for sh in g["shards"]:
                        for side in ("a", "b"):
                            rel = sweep_rel(g["group"], sh["shard"], side)
                            if (whole / rel).exists():
                                kept_sw[(g["group"], sh["shard"], side)] = guarded(lambda r=rel: kept_sweep(whole, r, inventory_hash), {})
                judged_pairs = {side: collections.Counter((p["candidate_id"], p["unit_id"]) for (g, sh, sd), k in kept_sw.items()
                                                          if sd == side for p in k.get("pairs", [])) for side in ("a", "b")}
                control("J3a (done-when 6): each sweep judged every absence claim's remaining units exactly once - every unit "
                        "S5 indexes less the ones retrieved for it - and nothing else",
                        all(set(judged_pairs[side]) == {(c, u) for c, us in want.items() for u in us}
                            and all(n == 1 for n in judged_pairs[side].values()) for side in ("a", "b")) and want,
                        f"{sum(judged_pairs['a'].values())} {sum(len(v) for v in want.values())}")
                shards_made = [(g, sh) for (g, sh, sd) in kept_sw if sd == "a"]
                control("J3a (N#1, done-when 6): both sweeps of a shard were sent one payload bound to the inventory's hash, "
                        "each call its own packet", shards_made and all(
                            kept_sw[(g, sh, "a")].get("payload_sha256") == kept_sw.get((g, sh, "b"), {}).get("payload_sha256")
                            and kept_sw[(g, sh, "a")].get("inventory_sha256") == inventory_hash for g, sh in shards_made)
                        and len({k.get("packet_sha256") for k in kept_sw.values()}) == len(kept_sw)
                        and sw.get("counts", {}).get("accepted") == 2 * len(shards_made), f"{sw.get('counts')}")
                # the third run: Judge B's reconsideration of the first claim answers the candidate's requirements too
                recon_defect = root / "plan-whole-recon-defect.json"
                recon_defect.write_text(json.dumps(judge_rows + [
                    {"match": [f"-{STAGE}-{item_of(claims_known[0])}-{RECONSIDER}B-a"], "auto": "reconsider",
                     "yes_first": True, "extra": {"requirements": fx_answer()["requirements"]}}] + sweep_rows), encoding="utf-8")
                again_sw = guarded(lambda: run(whole, supervisor(whole, root / "cells-9", recon_defect)),
                                   lambda e: {"problem": repr(e)})
                third_record = guarded(lambda: records.read_json(records.record_path(whole, STAGE)), {})
                third_dv = guarded(lambda: records.read_json(whole / DERIVATIONS), {})
                control("J4a: an absence claim whose reconsideration did not finish is not derived, and is named",
                        [r["candidate_id"] for r in third_dv.get("not_derived", [])] == [claims_known[0]]
                        and claims_known[0] not in third_dv.get("verdicts", {}) and len(third_dv.get("verdicts", {})) > 1,
                        f"{third_dv.get('not_derived')}")
                third_again = again_sw.get("reconsiderations") or {}
                third_calls = {r["candidate_id"]: r for r in third_again.get("calls", [])}
                c0_b = third_calls.get(claims_known[0], {}).get("seats", {}).get("B", {})
                control("J3c: a reconsideration Judge B answers with the candidate's requirements is refused by the schema on "
                        "both attempts, the claim is named RECONSIDERATION_MISSING and not diagnosed, and the record is "
                        "partial while every other call is accepted",
                        c0_b.get("outcome") == "failed" and len(c0_b.get("attempts", [])) == 2
                        and "SCHEMA_INVALID" in " ".join(map(str, c0_b.get("codes", [])))
                        and any(m.startswith(f"RECONSIDERATION_MISSING {claims_known[0]} B") for m in third_again.get("missing", []))
                        and [r["candidate_id"] for r in third_again.get("not_reconsidered", [])] == [claims_known[0]]
                        and claims_known[0] not in [r["candidate_id"] for r in third_again.get("reconsidered", [])]
                        and third_record.get("status") == "partial"
                        and not (again_sw.get("cross_review") or {}).get("not_reviewed")
                        and all(h["outcome"] == "accepted" for c, r in third_calls.items() for w, h in r["seats"].items()
                                if (c, w) != (claims_known[0], "B")),
                        f"{c0_b.get('outcome')} {third_again.get('missing')} {third_record.get('status')}")
                fourth = guarded(lambda: run(whole, supervisor(whole, root / "cells-10", whole_plan)), lambda e: {"problem": repr(e)})
                record = guarded(lambda: records.read_json(records.record_path(whole, STAGE)), {})
                control("J3a: run again after the defect, only the failed sweep is called anew; run once more, every sweep is "
                        "answered by its accepted attempt and the record is complete",
                        record.get("status") == "complete" and sw.get("counts", {}).get("reused") == 2 * len(shards_made) - 1
                        and (again_sw.get("sweeps") or {}).get("counts", {}).get("reused") == 2 * len(shards_made),
                        f"{sw.get('counts')} {(again_sw.get('sweeps') or {}).get('counts', again_sw)} {record.get('status')}")
                fourth_calls = {r["candidate_id"]: r for r in (fourth.get("reconsiderations") or {}).get("calls", [])}
                control("J3c: run once more, only the unanswered reconsideration is called anew and accepted; every other is "
                        "answered by its accepted attempt",
                        fourth_calls.get(claims_known[0], {}).get("seats", {}).get("B", {}).get("outcome") == "accepted"
                        and not fourth_calls.get(claims_known[0], {}).get("seats", {}).get("B", {}).get("reused")
                        and all(h.get("reused") for c, r in fourth_calls.items() for w, h in r["seats"].items()
                                if (c, w) != (claims_known[0], "B")) and len(fourth_calls) >= 3,
                        f"{[(c[:12], {w: (h.get('outcome'), h.get('reused')) for w, h in r['seats'].items()}) for c, r in fourth_calls.items()]}")
                again_cross = {r["candidate_id"]: r for r in (again_sw.get("cross_review") or {}).get("calls", [])}
                control("J3b: run once more, only the failed cross-review is called anew and accepted; every other is answered "
                        "by its accepted attempt", again_cross.get(claims_known[0], {}).get("outcome") == "accepted"
                        and not again_cross.get(claims_known[0], {}).get("reused")
                        and all(r.get("reused") for c, r in again_cross.items() if c != claims_known[0]) and len(again_cross) > 1,
                        f"{[(c[:12], r.get('outcome'), r.get('reused')) for c, r in again_cross.items()]}")
                # Codex WP-11 r1 #1: in each of the four call kinds one attempt fails its check and its one corrective retry,
                # sent with the gate's correction, is accepted; the run completes, and a run after it answers every call
                # from those attempts. The first attempts are planted by call id, so the retries meet the ordinary rows.
                retried = retry_base / whole.name
                judged_one = next((c for c in sorted(whole_packets) if c not in made_gaps and whole_packets[c][0].units), None)
                seat_a = f"SEAT: {fresh.get('seats', {}).get('A')}"
                normal = next((r for r in judge_rows if judged_one and r["match"] == [seat_a, whole_packets[judged_one][1]]), None)
                planted_first = {
                    "judge": f"-{STAGE}-{item_of(judged_one or '')}-A-a1",
                    "sweep": f"-{STAGE}-sweep-g001-s001-b-a1",
                    "cross": f"-{STAGE}-{item_of(claims_known[1] if len(claims_known) > 1 else '')}-X-a1",
                    "reconsider": f"-{STAGE}-{item_of(recon_of.get(0, ''))}-{RECONSIDER}A-a1"}
                retry_rows = ([{"match": [planted_first["judge"]], "answer": {**normal["answer"],
                                                                             "units": normal["answer"]["units"][1:]}}]
                              if normal else []) + [
                    {"match": [planted_first["sweep"]], "auto": "sweep", "drop_first": True},
                    {"match": [planted_first["cross"]], "auto": "cross", "drop_first": True},
                    {"match": [planted_first["reconsider"]], "auto": "reconsider", "yes_first": True,
                     "extra": {"requirements": fx_answer()["requirements"]}}]
                retry_plan = root / "plan-whole-retry.json"
                retry_plan.write_text(json.dumps(retry_rows + judge_rows + sweep_rows), encoding="utf-8")
                fifth = guarded(lambda: run(retried, supervisor(retried, root / "cells-11", retry_plan)),
                                lambda e: {"problem": repr(e)})
                fifth_record = guarded(lambda: records.read_json(records.record_path(retried, STAGE)), {})
                attempts_of = {kind: sorted(d.name for d in (retried / "calls").iterdir()
                                            if (retried / "calls").is_dir() and d.name.endswith(frag[:-1] + "2")
                                            and (retried / "calls" / d.name / "receipt.json").is_file())
                               for kind, frag in planted_first.items()}
                control("Codex WP-11 r1 #1: an attempt that fails its check in each of the four call kinds is retried once "
                        "with the gate's correction, the retry is accepted and its receipt passes N#1, and the run completes",
                        normal is not None and len(recon_of) == 3 and "problem" not in fifth
                        and fifth_record.get("status") == "complete" and all(len(v) == 1 for v in attempts_of.values()),
                        f"{str(fifth.get('problem'))[:300]} {fifth_record.get('status')} {attempts_of}")
                retry_dir = retried / "calls" / attempts_of["judge"][0] if attempts_of.get("judge") else None
                text_one = whole_packets[judged_one][1] if judged_one else ""
                due = guarded(lambda: corrected_sha256(retry_dir, text_one), "RAISED") if retry_dir else None
                receipt_one = guarded(lambda: records.read_json(retry_dir / "receipt.json"), {}) if retry_dir else {}
                control("Codex WP-11 r1 #1: a retry's due hash is its receipt's only when what was sent is the payload S6 "
                        "built and the gate's correction; another payload, or the first attempt, is held to S6's own hash",
                        due is not None and due == (receipt_one.get("evidence") or {}).get("payload_sha256")
                        and guarded(lambda: corrected_sha256(retry_dir, text_one.replace("\n", " \n", 1)), "RAISED") is None
                        and guarded(lambda: corrected_sha256(pathlib.Path(str(retry_dir)[:-1] + "1"), text_one), "RAISED")
                        is None, f"{due} {(receipt_one.get('evidence') or {}).get('payload_sha256')}")
                # Codex WP-11 r1 #2: what derive reads of S6's files is what the summary says this invocation accepted, on
                # a copy of the run whose files are then made stale
                stale_root = root / "stale-copy"
                shutil.copytree(whole.parent, stale_root)
                stale = stale_root / whole.name
                c0 = claims_known[0] if claims_known else ""
                kept_summary = guarded(lambda: records.read_json(stale / SUMMARY), {})

                def current_of(given):
                    return guarded(lambda: derive.unit_outcome(given, {}, TEST_STATE)["candidate_diagnosis"]["current"]
                                   ["diagnosis"], "RAISED")
                as_reconsidered = current_of(guarded(lambda: given_from_run(stale, c0), {}))
                shrunk = json.loads(json.dumps(kept_summary))
                for r in (shrunk.get("reconsiderations") or {}).get("reconsidered") or []:
                    if r["candidate_id"] == c0:
                        r["returned"] = 0
                (stale / SUMMARY).chmod(0o600)
                (stale / SUMMARY).write_text(json.dumps(shrunk), encoding="utf-8")
                as_returned_none = current_of(guarded(lambda: given_from_run(stale, c0), {}))
                control("Codex WP-11 r1 #2: a claim this invocation reconsidered with nothing returned is derived from its "
                        "first judgments alone, though an earlier invocation's reconsiderations of it are still on disk",
                        as_reconsidered == "covered" and as_returned_none == "gap"
                        and all((stale / reconsideration_rel(item_of(c0), w)).is_file() for w in SEAT_KEYS),
                        f"{as_reconsidered} {as_returned_none}")
                (stale / SUMMARY).write_text(json.dumps(kept_summary), encoding="utf-8")
                foreign = stale / reconsideration_rel(item_of(c0), "B")
                held_b = guarded(lambda: records.read_json(foreign), {})
                foreign.chmod(0o600)
                foreign.write_text(json.dumps({**held_b, "call_id": "another-run-S6-x-a1"}), encoding="utf-8")
                said = refusal(lambda: given_from_run(stale, c0))
                control("Codex WP-11 r1 #2: a reconsideration file naming another call than the one the invocation accepted "
                        "is RECONSIDERATION_STALE, never derived from", said.startswith(f"RECONSIDERATION_STALE {c0} B"),
                        said[:200])
                foreign.write_text(json.dumps(held_b), encoding="utf-8")
                other = next((c for c in sorted(whole_packets) if c not in claims_known), "")
                first_a = stale / judgment_rel(item_of(other), "A")
                held_a = guarded(lambda: records.read_json(first_a), {})
                first_a.chmod(0o600)
                first_a.write_text(json.dumps({**held_a, "call_id": "another-run-S6-y-a1"}), encoding="utf-8")
                said = refusal(lambda: given_from_run(stale, other))
                control("Codex WP-11 r1 #2: a first judgment file naming another call than the summary's is JUDGMENT_STALE "
                        "to S10's reader", said.startswith(f"JUDGMENT_STALE {other} A"), said[:200])
                # Codex WP-11 r1 #3: the sweeps and Judge B's cross-review are held to their seats' capacity, every packet
                # before the first call of its kind and each attempt as it is sent; a seat nobody measured is not bounded
                # (D13). Driven with a supervisor that records what it is asked, over a copy of the swept run.
                cap_root = root / "cap-copy"
                shutil.copytree(whole.parent, cap_root)
                capped = cap_root / whole.name
                judged_w = sorted(whole_packets)
                judgments_w = {c: {w: guarded(lambda c=c, w=w: records.read_json(capped / judgment_rel(item_of(c), w))
                                              ["judgment"], {}) for w in SEAT_KEYS} for c in judged_w}
                sources_w = {r["candidate_id"]: r["source"]
                             for r in guarded(lambda: records.read_json(capped / SUMMARY), {}).get("packets", [])}
                swept_w = guarded(lambda: records.read_json(capped / SUMMARY), {}).get("sweeps") or {}

                class Asked:
                    def __init__(self, seats_path):
                        self.seats_path, self.items = seats_path, []

                    def item(self, stage_, item, seat, text, schema_, **kw):
                        self.items.append((item, seat, kw))
                        return {"item": item, "outcome": "failed", "codes": ["NOT_SENT"], "attempts": []}

                def asked(kind, seats_file):
                    sup = Asked(seats_file)
                    said = ""
                    with records.run_stage(capped, STAGE, INPUTS) as stg:
                        try:
                            if kind == "sweep":
                                sweep_stage(capped, stg, sup, stg.declaration, judged_w, judgments_w, sources_w, {},
                                            "calibration")
                            else:
                                cross_stage(capped, stg, sup, stg.declaration, swept_w, item_of, {}, "calibration")
                        except Refused as exc:
                            said = str(exc)
                        stg.record["status"] = "partial"
                    return said, sup.items
                sweep_seat, cross_seat = "claude:claude-sonnet-5-5/medium", "codex:gpt-6-astra/xhigh"
                huge = packet.build("c-a2", STAGE, "s", "x" * 8_000_000)
                said_s, asked_s = asked("sweep", fx_seats(root, name="sweep-tight.json", capacities={sweep_seat: 3000}))
                control("Codex WP-11 r1 #3: a sweep shard over its seat's capacity is SWEEP_OVER_CAPACITY before any sweep "
                        "is sent", said_s.startswith("SWEEP_OVER_CAPACITY S6") and asked_s == [], f"{said_s[:200]} {len(asked_s)}")
                said_s, asked_s = asked("sweep", fx_seats(root, name="sweep-room.json", capacities={sweep_seat: 150_000}))
                side_a = [kw for item, seat, kw in asked_s if seat == sweep_seat]
                side_b = [kw for item, seat, kw in asked_s if seat != sweep_seat]
                control("Codex WP-11 r1 #3: within capacity every sweep is sent with its seat's capacity and an attempt bound "
                        "that refuses an oversized attempt, and the unmeasured Codex sweep seat is not bounded (D13)",
                        not said_s and side_a and side_b and all(kw.get("context_capacity") == 150_000 for kw in side_a)
                        and all(any(x.startswith("SWEEP_OVER_CAPACITY sweep a") for x in kw.get("packet_check", lambda m: [])(huge))
                                for kw in side_a)
                        and all(kw.get("context_capacity") is None and kw.get("packet_check", lambda m: [])(huge) == [] for kw in side_b),
                        f"{said_s[:200]} {[kw.get('context_capacity') for kw in side_a]} "
                        f"{[guarded(lambda kw=kw: kw.get('packet_check', lambda m: [])(huge), ['RAISED'])[:1] for kw in side_a]} "
                        f"{[kw.get('context_capacity') for kw in side_b]} "
                        f"{[guarded(lambda kw=kw: kw.get('packet_check', lambda m: [])(huge), ['RAISED'])[:1] for kw in side_b]}")
                said_c, asked_c = asked("cross", fx_seats(root, name="cross-tight.json", capacities={cross_seat: 3000},
                                                         codex_allowance=5000))
                control("Codex WP-11 r1 #3: a cross-review packet over Judge B's capacity is CROSS_OVER_CAPACITY before any "
                        "cross-review is sent", said_c.startswith("CROSS_OVER_CAPACITY S6") and asked_c == [],
                        f"{said_c[:200]} {len(asked_c)}")
                said_c, asked_c = asked("cross", fx_seats(root, name="cross-room.json", capacities={cross_seat: 150_000},
                                                         codex_allowance=5000))
                control("Codex WP-11 r1 #3: within capacity every cross-review is sent with Judge B's capacity and an attempt "
                        "bound that refuses an oversized attempt", not said_c and asked_c
                        and all(kw.get("context_capacity") == 150_000
                                and any(x.startswith("CROSS_OVER_CAPACITY B") for x in kw.get("packet_check", lambda m: [])(huge))
                                for _i, _s, kw in asked_c), f"{said_c[:200]} {len(asked_c)}")
                sixth = guarded(lambda: run(retried, supervisor(retried, root / "cells-12", whole_plan)),
                                lambda e: {"problem": repr(e)})
                sixth_reused = [h.get("reused") for row in sixth.get("calls", []) for h in row["seats"].values()] + [
                    h.get("reused") for row in (sixth.get("sweeps") or {}).get("calls", []) for h in row["seats"].values()] + [
                    row.get("reused") for row in (sixth.get("cross_review") or {}).get("calls", [])] + [
                    h.get("reused") for row in (sixth.get("reconsiderations") or {}).get("calls", [])
                    for h in row["seats"].values()]
                control("Codex WP-11 r1 #1: run again, every call is answered by its accepted attempt, the retried ones "
                        "included, and the receipts still pass", "problem" not in sixth and sixth_reused
                        and all(sixth_reused), f"{str(sixth.get('problem'))[:300]} {sixth_reused.count(None)}")
                # ---- Judge B's cross-review (J3b, done-when 3) --------------------------------------------------------
                cr = again_sw.get("cross_review") or {}
                pop_b = {k["candidate_id"]: k for k in records.read_json(whole / "checked-candidates.json")["candidates"]}
                units_b = {u["unit_id"]: u for u in records.read_json(whole / "inventory" / "current.json")["units"]}
                entries_b = whole_packets[next(iter(whole_packets))][0].entry_store
                marks_w = {}
                for (g, sh, side), k in kept_sw.items():   # from the kept sweep files, not through sweep_marks
                    for pr in k.get("pairs", []):
                        marks_w.setdefault(pr["candidate_id"], {}).setdefault(pr["unit_id"], {})[side] = pr
                want_flags = {c: sorted(u for u, sides in m.items() if any("yes" in (x["situation"], x["action"])
                                                                            for x in sides.values())) for c, m in marks_w.items()}
                both_no = {c: [u for u, sides in m.items() if len(sides) == 2
                               and all(x["situation"] == x["action"] == "no" for x in sides.values())] for c, m in marks_w.items()}
                want_neg = {c: sorted(us, key=lambda u, c=c: hashlib.sha256(f"{whole.name}\x00{c}\x00{u}".encode("utf-8"))
                                      .hexdigest())[:50] for c, us in both_no.items()}
                crossed_kept = {c: guarded(lambda c=c: records.read_json(whole / cross_rel(item_of(c))), {}) for c in expected}
                control("J3b (done-when 3): every absence claim is reviewed by Judge B, its packet carrying every unit either "
                        "sweep flagged and the fifty units both found unrelated that the run id draws, with both sweeps' reasons",
                        sorted(cr.get("reviewed", [])) == expected and all(
                            crossed_kept[c].get("partial_flags") == want_flags.get(c, [])
                            and crossed_kept[c].get("seeded_negatives") == want_neg.get(c, [])
                            and crossed_kept[c].get("seat") == "codex:gpt-6-astra/xhigh"
                            and len(crossed_kept[c].get("verdicts", [])) == len(set(want_flags.get(c, [])) | set(want_neg.get(c, [])))
                            for c in expected), f"{cr.get('reviewed')} {expected}")
                full = [c for c in expected if len(both_no.get(c, [])) > 50]
                flagged_claims = [c for c in expected if want_flags.get(c)]
                one_side = [c for c in flagged_claims if any(len({s for s, x in marks_w[c][u].items()
                                                                     if "yes" in (x["situation"], x["action"])}) == 1
                                                              for u in want_flags[c])]
                control("J3b: a claim with more than fifty units both sweeps found unrelated is shown exactly fifty; the "
                        "fixture holds such a claim, and a claim with a unit only one sweep flagged",
                        full and all(len(crossed_kept[c].get("seeded_negatives", [])) == 50 for c in full) and one_side,
                        f"{[len(both_no.get(c, [])) for c in expected]} {len(flagged_claims)}")
                few = {f"u{n}": {side: {"situation": "no", "action": "no", "reason": "r"} for side in ("a", "b")} for n in range(7)}
                few["u-flag"] = {"a": {"situation": "yes", "action": "no", "reason": "r"},
                                 "b": {"situation": "no", "action": "no", "reason": "r"}}
                control("J3b: a claim with fewer than fifty units both sweeps found unrelated is shown every one of them, and "
                        "a unit one sweep flagged is a flag, not a negative",
                        sorted(negatives_of(few, "r1", "k-a")) == sorted(f"u{n}" for n in range(7)) and flags_of(few) == ["u-flag"])
                if full:
                    c = full[0]
                    marks_c = {u: {side: {k: x[k] for k in ("situation", "action", "reason")} for side, x in sides.items()}
                               for u, sides in marks_w[c].items()}
                    control("J3b (done-when 3): another seed draws another sample",
                            negatives_of(marks_c, "another-run", c) != negatives_of(marks_c, whole.name, c)
                            and negatives_of(marks_c, whole.name, c) == want_neg[c])
                if flagged_claims:
                    c = flagged_claims[0]
                    rec = {"partial_flags": [], "seeded_negatives": [], **crossed_kept[c]}
                    marks_c = {u: {side: {k: x[k] for k in ("situation", "action", "reason")} for side, x in sides.items()}
                               for u, sides in marks_w[c].items()}
                    flags_c, neg_c = flags_of(marks_c), negatives_of(marks_c, whole.name, c)
                    labels_c = CrossLabels(pop_b[c], marks_c, flags_c, neg_c, units_b, entries_b)
                    built_sha = packet.sha256_bytes(cross_payload(labels_c).encode("utf-8"))
                    control("J3b: a kept cross-review is the one the kept sweep results build", not cross_review_problems(
                        rec, flags_c, neg_c, built_sha), f"{cross_review_problems(rec, flags_c, neg_c, built_sha)}")
                    named("control (done-when 3): a cross-review missing one partial flag is CROSS_REVIEW_INCOMPLETE",
                          cross_review_problems({**rec, "partial_flags": rec["partial_flags"][1:]}, flags_c, neg_c, built_sha),
                          "CROSS_REVIEW_INCOMPLETE")
                    named("control: a cross-review whose negatives are another sample is CROSS_REVIEW_INCOMPLETE",
                          cross_review_problems({**rec, "seeded_negatives": rec["seeded_negatives"][::-1]}, flags_c, neg_c,
                                                built_sha) if len(neg_c) > 1 else ["CROSS_REVIEW_INCOMPLETE vacuous"],
                          "CROSS_REVIEW_INCOMPLETE")
                    corrupted = json.loads(json.dumps(marks_c))
                    some_neg = (neg_c or flags_c)[0]
                    corrupted[some_neg]["a"]["reason"] = "a reason changed after the review"
                    stale_sha = packet.sha256_bytes(cross_payload(CrossLabels(
                        pop_b[c], corrupted, flags_c, neg_c, units_b, entries_b)).encode("utf-8"))
                    named("control (done-when 3): one sampled reason changed in the sweep results is CROSS_REVIEW_STALE by "
                          "the payload hash", cross_review_problems(rec, flags_c, neg_c, stale_sha), "CROSS_REVIEW_STALE")
                    good = {"verdicts": [{"unit": u, "situation": "no", "action": "no", "reason": "unrelated"}
                                         for u in labels_c.units]}
                    control("J3b: a cross-review judging every unit shown once passes", not cross_problems(labels_c, good))
                    for name, answer, code in (
                            ("a unit shown and not judged", {"verdicts": good["verdicts"][1:]}, "CROSS_UNIT_MISSING"),
                            ("a unit judged twice", {"verdicts": good["verdicts"] + good["verdicts"][:1]}, "CROSS_UNIT_TWICE"),
                            ("a unit the packet does not show", {"verdicts": good["verdicts"] + [{**good["verdicts"][0], "unit": "n999"}]},
                             "UNKNOWN_LABEL")):
                        named(f"control: in a cross-review, {name} is refused by name", cross_problems(labels_c, answer), code)
                    text_c = cross_payload(labels_c)
                    control("J3b: the cross-review packet shows each unit with both sweeps' marks and reasons, and no stored id",
                            all(f'"sweeps": {{"a": ' in line and '"b": ' in line for line in text_c.split("<units>\n", 1)[1]
                                .split("\n</units>", 1)[0].splitlines()) and c not in text_c
                            and not any(u in text_c for u in labels_c.units.values()), "")
                # ---- the reconsiderations (J3c, done-when 3) ----------------------------------------------------------
                rc = fourth.get("reconsiderations") or {}
                kept_rc = {(c, who): guarded(lambda c=c, who=who: records.read_json(
                    whole / reconsideration_rel(item_of(c), who)), {}) for c in expected for who in ("A", "B")}
                b_matched = {c: sorted(v["unit_id"] for v in crossed_kept[c].get("verdicts", [])
                                       if "yes" in (v["situation"], v["action"])) for c in expected}
                want_returned = {c: sorted(set(want_flags.get(c, [])) | set(b_matched[c])) for c in expected}
                control("J3c (done-when 3): every unit either sweep flagged or Judge B marked a match returns to both judges, "
                        "each reconsideration judging exactly those units",
                        all(kept_rc[(c, who)].get("returned") == want_returned[c] and want_returned[c]
                            and sorted(u["unit_id"] for u in kept_rc[(c, who)].get("judgment", {}).get("units", []))
                            == want_returned[c] for c in expected for who in ("A", "B")),
                        f"{[(c[:12], len(want_returned[c]), len(kept_rc[(c, 'A')].get('returned') or [])) for c in expected]}")
                control("J3c: the fixture returns a unit only Judge B marked, and the first claim's first returned unit is one "
                        "only one sweep flagged",
                        any(set(b_matched[c]) - set(want_flags.get(c, [])) for c in expected)
                        and want_returned[claims_known[0]][:1]
                        and len({side for side, x in marks_w.get(claims_known[0], {}).get(want_returned[claims_known[0]][0], {}).items()
                                 if "yes" in (x["situation"], x["action"])}) == 1,
                        f"{b_matched} {want_flags}")
                control("J3c (N#1): both judges' reconsiderations of a claim carry one payload and two packets",
                        all(kept_rc[(c, "A")].get("payload_sha256") and kept_rc[(c, "A")].get("payload_sha256")
                            == kept_rc[(c, "B")].get("payload_sha256")
                            and kept_rc[(c, "A")].get("packet_sha256") != kept_rc[(c, "B")].get("packet_sha256") for c in expected))
                c0_labels = guarded(lambda: returned_labels(whole_packets[claims_known[0]][0], want_returned[claims_known[0]]), None)
                c0_text = guarded(lambda: reconsider_payload(c0_labels), "") if c0_labels is not None else ""
                control("J3c: a reconsideration shows the candidate, its claims and the returned units with their context, no "
                        "ledger entry and no candidate-level question, and its payload is the one kept",
                        c0_labels is not None and list(c0_labels.units.values()) == want_returned[claims_known[0]]
                        and not c0_labels.entries and "<ledger_entries>" not in c0_text and "<units>" in c0_text
                        and not any(f"`{f}`" in c0_text for f in RECONSIDER_REFUSED)
                        and packet.sha256_bytes(c0_text.encode("utf-8")) == kept_rc[(claims_known[0], "A")].get("payload_sha256")
                        and claims_known[0] not in c0_text, "")
                c0_kept = [kept_rc[(claims_known[0], who)].get("judgment") or {} for who in ("A", "B")]
                control("J3c: a kept reconsideration holds the returned units and their matching units only, and a unit both "
                        "judges now find matching carries its following and contribution",
                        all(sorted(k) == sorted(RECONSIDER_FIELDS) for k in c0_kept)
                        and all(k["matching_units"] and k["matching_units"][0].get("following") == "followed"
                                and k["matching_units"][0]["unit_id"] == want_returned[claims_known[0]][0] for k in c0_kept),
                        f"{[sorted(k) for k in c0_kept]}")
                after = {r["candidate_id"]: (r["diagnosis"], r["row"]) for r in rc.get("reconsidered", [])}
                control("J3c (O4): a gap claim contradicted by a unit only one sweep flagged is reconsidered by both judges - "
                        "both now matching, it is no gap; one only, it is disputed; neither, the gap stands",
                        after.get(claims_known[0], ("gap",))[0] not in ("gap", "unknown")
                        and after.get(claims_known[1]) == ("unknown", derive.DISPUTED)
                        and after.get(claims_known[2], ("",))[0] == "gap" and not rc.get("missing"), f"{after}")
                held_a = kept_rc[(claims_known[1], "A")].get("judgment")
                held_b = kept_rc[(claims_known[1], "B")].get("judgment")
                if held_a and held_b:
                    returned_1 = want_returned[claims_known[1]]
                    named("control (done-when 3): a claim missing Judge B's reconsideration is RECONSIDERATION_MISSING",
                          reconsideration_problems(claims_known[1], returned_1, {"A": held_a}), "RECONSIDERATION_MISSING")
                    named("control: a reconsideration judging fewer units than were returned is RECONSIDERATION_MISSING",
                          reconsideration_problems(claims_known[1], returned_1,
                                                   {"A": held_a, "B": {**held_b, "units": held_b["units"][1:]}}),
                          "RECONSIDERATION_MISSING")
                    control("J3c: both judges reconsidering every returned unit is no problem",
                            not reconsideration_problems(claims_known[1], returned_1, {"A": held_a, "B": held_b}))
                # a claim whose cross-review returns nothing keeps its gap without a call
                c2 = claims_known[2]
                quiet = root / "nothing-returned"
                (quiet / "cross_review").mkdir(parents=True, exist_ok=True)
                (quiet / cross_rel(item_of(c2))).write_text(json.dumps({**crossed_kept[c2], "partial_flags": [], "verdicts": [
                    {**v, "situation": "no", "action": "no"} for v in crossed_kept[c2].get("verdicts", [])]}), encoding="utf-8")
                firsts = {who: guarded(lambda who=who: records.read_json(whole / judgment_rel(item_of(c2), who))["judgment"], {})
                          for who in ("A", "B")}
                quiet_section = guarded(lambda: reconsider_stage(
                    quiet, None, None, None, {"packets": [{"candidate_id": c2, "source": pop_b[c2]["source"]}], "seats": {}, "limits": {}},
                    {c2: whole_packets[c2]}, {c2: firsts}, {"reviewed": [c2]}, {}, "calibration"), lambda e: ({"problem": repr(e)}, []))
                control("J3c: a claim its cross-review returns nothing for keeps its gap, with no reconsideration call",
                        quiet_section[0].get("reconsidered") == [{"candidate_id": c2, "returned": 0, "diagnosis": "gap",
                                                                  "row": quiet_section[0]["reconsidered"][0]["row"]}]
                        and not quiet_section[0].get("calls") and not quiet_section[1] if quiet_section[0].get("reconsidered")
                        else False, f"{quiet_section[0]}")
                # ---- the derivations (J4a) ----------------------------------------------------------------------------
                dv = guarded(lambda: records.read_json(whole / DERIVATIONS), {})
                verd = dv.get("verdicts", {})
                judged_whole = sorted(whole_packets)
                admitted_of = {c: v["outcome"]["admission"] for c, v in verd.items()}
                uncertain_c, unmet_c = (list(planted_marks) + [None, None])[:2]
                control("J4a (done-when 2, O4): both judges uncertain on a requirement is disputed, not admitted; both unmet "
                        "is rejected; both met on every requirement is admitted",
                        len(planted_marks) == 2 and admitted_of.get(uncertain_c) == {"admission": "disputed", "row": "disputed"}
                        and admitted_of.get(unmet_c, {}).get("admission") == "rejected"
                        and all(a == {"admission": "admitted", "row": "admitted"} for c, a in admitted_of.items()
                                if c not in planted_marks) and len(admitted_of) > 2, f"{planted_marks} {admitted_of}")
                control("J4a: every candidate both judges judged is derived, and no other",
                        sorted(verd) == judged_whole and not dv.get("not_derived"), f"{len(verd)} {len(judged_whole)}")
                firsts_w = {c: {who: guarded(lambda c=c, who=who: records.read_json(
                    whole / judgment_rel(item_of(c), who))["judgment"], {}) for who in ("A", "B")} for c in judged_whole}
                control("J4a: a derivation reads both judges' requirement marks from their first judgments and the "
                        "candidate's lineages from S5's recurrence count",
                        all(verd.get(c, {}).get("requirements", {}).get(who) == {n: m["mark"] for n, m in
                                                                                  firsts_w[c][who].get("requirements", {}).items()}
                            and firsts_w[c][who].get("requirements") for c in judged_whole for who in ("A", "B"))
                        and all(verd.get(c, {}).get("lineages") == (whole_rows[c].get("recurrence") or {}).get("count")
                                for c in judged_whole) and any(verd.get(c, {}).get("lineages") for c in judged_whole),
                        "")
                after_rc = {r["candidate_id"]: r["diagnosis"] for r in rc.get("reconsidered", [])}
                control("J4a: a reconsidered absence claim is derived with its reconsidered units - its current diagnosis is "
                        "the reconsideration's", after_rc and all(
                            verd.get(c, {}).get("outcome", {}).get("candidate_diagnosis", {}).get("current", {}).get("diagnosis")
                            == d for c, d in after_rc.items()), f"{after_rc}")
                control("J4a: no release point is judged, so every derivation's release diagnosis is unknown by `absent`, it "
                        "has no unit outcome, and it names its test state",
                        verd and all(v["outcome"]["candidate_diagnosis"]["release"] == {"diagnosis": "unknown", "row": "absent",
                                                                                         "absence": None}
                                     and v["outcome"]["unit_outcomes"] == [] and v["outcome"]["test"] == "untested: s8_deferred"
                                     for v in verd.values()))
                want_pairs = 0
                for c in judged_whole:
                    pairs_c = {}
                    for who in ("A", "B"):
                        for u in firsts_w[c][who].get("units", []):
                            pairs_c.setdefault(u["unit_id"], {})[who] = u
                        again_c = guarded(lambda c=c, who=who: records.read_json(
                            whole / reconsideration_rel(item_of(c), who))["judgment"], {})
                        for u in again_c.get("units", []):
                            pairs_c.setdefault(u["unit_id"], {})[who] = u
                    matched_c = [u for u, pr in pairs_c.items() if derive.unit_diagnosis(
                        derive.agreed(pr.get("A", {}).get("situation"), pr.get("B", {}).get("situation")),
                        derive.agreed(pr.get("A", {}).get("action"), pr.get("B", {}).get("action"))) != "no match"]
                    want_pairs += len(pop_b[c].get("sessions") or []) * len(matched_c)
                control("J4a (D3): delivery is not read; every (session, unit) pair a matching unit would need is counted as "
                        "delivery_assembly_waiting", dv.get("delivery", {}).get("state") == "delivery_assembly_waiting"
                        and dv.get("delivery", {}).get("pairs") == want_pairs and want_pairs > 0,
                        f"{dv.get('delivery')} {want_pairs}")
                control("J4a: the derivations say by name that no unit outcome is derived, why, and for how many candidates",
                        dv.get("unit_outcomes", {}).get("state") == "none"
                        and dv.get("unit_outcomes", {}).get("candidates") == len(verd) and len(verd) > 0
                        and "D-20261111-c4fa71" in dv.get("unit_outcomes", {}).get("why", "")
                        and fourth.get("derivations", {}).get("unit_outcomes") == dv.get("unit_outcomes"),
                        f"{dv.get('unit_outcomes')}")
                g_ids = sorted(c for c in verd if pop_b[c].get("type") in G_TYPES)
                bar_g = next(r for r in derive.table()["promotion"] if r["id"] == "type_g")["independent_lineages_at_least"]
                arc = dv.get("arc_confirmation", {})
                control("J4a (D-20261111-f122c0): every type G verdict says its arc confirmation is undetermined, no other "
                        "verdict does, and the derivations count the G candidates and those below the lineage bar",
                        g_ids and all(verd[c].get("arc_confirmation") == "undetermined" for c in g_ids)
                        and not any("arc_confirmation" in v for c, v in verd.items() if c not in g_ids)
                        and arc.get("state") == "undetermined" and arc.get("passed_as") is False
                        and arc.get("g_candidates") == len(g_ids)
                        and arc.get("g_below_lineage_bar") == sum(1 for c in g_ids if verd[c]["lineages"] < bar_g),
                        f"{arc} {g_ids}")
                # N#1 over the reconsiderations (J3c): the check that reads their receipts, and what the run handed it
                accepted_rc = sum(1 for r in rc.get("calls", []) for h in r["seats"].values() if h["outcome"] == "accepted")
                control("J3c (N#1): the run holds every accepted reconsideration's receipt to N#1 - the receipts it checked "
                        "count each accepted reconsideration call once", accepted_rc > 0
                        and fourth.get("receipts_checked", {}).get("reconsider") == accepted_rc
                        and fourth.get("receipts_checked", {}).get("cross") == len(cr.get("calls", [])),
                        f"{fourth.get('receipts_checked')} {accepted_rc}")
                pair_rc = []
                for who in ("A", "B"):
                    call_rc = kept_rc[(claims_known[1], who)].get("call_id")
                    held_rc = guarded(lambda call_rc=call_rc: records.read_json(whole / "calls" / call_rc / "receipt.json"), {})
                    pair_rc.append((f"reconsider/{claims_known[1]}", who, call_rc, held_rc,
                                    kept_rc[(claims_known[1], who)].get("payload_sha256")))
                control("J3c (N#1): the kept reconsiderations' receipt pair passes the check that reads it",
                        all(r[3] for r in pair_rc) and not stage_receipts(pair_rc), f"{stage_receipts(pair_rc)}")
                moved_rc = [pair_rc[0], (*pair_rc[1][:3], {**pair_rc[1][3], "evidence": {
                    **(pair_rc[1][3].get("evidence") or {}), "payload_sha256": "0" * 64}}, pair_rc[1][4])]
                named("control (N#1): a reconsideration's two receipts carrying different payload hashes is "
                      "PACKET_DIVERGENCE", stage_receipts(moved_rc), "PACKET_DIVERGENCE")
                control("J3c: a receipt missing from the list is not something the check can see - receipt_counts says what "
                        "it held", receipt_counts(pair_rc[:1]).get("reconsider") == 1 and not stage_receipts(pair_rc[:1]))
                some = next(iter(sorted(kept_sw)), None)
                if some is not None:
                    said = refusal(lambda: kept_sweep(whole, sweep_rel(*some), "0" * 64))
                    control("control (done-when 6): a sweep result cut from another inventory is SWEEP_INVENTORY_MOVED",
                            said.startswith("SWEEP_INVENTORY_MOVED"), said[:200])
                # a shard's packet, its answer checked, its plan's set accounting, a lifecycle candidate's view
                plan_w = shard_plan(want, 2, 2)
                # a shard where one candidate lacks a unit another has, so E3's unlisted pair can be planted
                first_shard = next((sh for g in plan_w for sh in g["shards"] if len(sh["pairs"]) > 1
                                    and any(len(us) < len(sh["units"]) for us in sh["pairs"].values())),
                                   next(sh for g in plan_w for sh in g["shards"] if sh["pairs"]))
                pop_w = {k["candidate_id"]: k for k in records.read_json(whole / "checked-candidates.json")["candidates"]}
                units_w = {u["unit_id"]: u for u in records.read_json(whole / "inventory" / "current.json")["units"]}
                labels_w = guarded(lambda: SweepLabels(first_shard, pop_w, units_w, whole_packets[next(iter(whole_packets))][0].entry_store),
                                   lambda e: e)
                if isinstance(labels_w, Exception):
                    failures.append(f"J3a: a sweep packet could not be labelled: {labels_w!r}")
                else:
                    good = {"pairs": [{"candidate": k, "unit": u, "situation": "no", "action": "no", "reason": "unrelated"}
                                      for k, u in sorted(labels_w.listed)]}
                    control("J3a: a sweep answer judging exactly the listed pairs passes", not sweep_problems(labels_w, good),
                            f"{sweep_problems(labels_w, good)}")
                    k0, u0 = sorted(labels_w.listed)[0]
                    unlisted = next(((k, u) for k in labels_w.candidates for u in labels_w.units if (k, u) not in labels_w.listed),
                                    None)
                    cases = [("a listed pair left out", {"pairs": good["pairs"][1:]}, "SWEEP_PAIR_MISSING"),
                             ("a pair judged twice", {"pairs": good["pairs"] + good["pairs"][:1]}, "SWEEP_PAIR_TWICE"),
                             ("a label the packet does not show", {"pairs": good["pairs"] + [{**good["pairs"][0], "unit": "n99"}]},
                              "UNKNOWN_LABEL")]
                    if unlisted is not None:
                        cases.append(("a pair the packet does not list", {"pairs": good["pairs"] + [
                            {**good["pairs"][0], "candidate": unlisted[0], "unit": unlisted[1]}]}, "SWEEP_PAIR_UNLISTED"))
                    for name, answer, code in cases:
                        named(f"control: {name} is refused by name", sweep_problems(labels_w, answer), code)
                    control("control: the sweep packet names an unlisted pair to plant (E3 has one to refuse)", unlisted is not None)
                    control("J3a: a sweep payload is bound to its inventory - another inventory hash is another payload",
                            sweep_payload(labels_w, "a" * 64) != sweep_payload(labels_w, "b" * 64))
                shifted = json.loads(json.dumps(plan_w))
                g0 = shifted[0]
                c0 = next(c for c in g0["candidates"] if any(c in sh["pairs"] for sh in g0["shards"]))
                sh0 = next(sh for sh in g0["shards"] if c0 in sh["pairs"])
                for name, change, code in (
                        ("a remaining unit in two shards", lambda: g0["shards"][-1]["pairs"].setdefault(c0, []).append(sh0["pairs"][c0][0]),
                         "SET_MISMATCH sweep g001"),
                        ("a remaining unit in no shard", lambda: sh0["pairs"][c0].pop(), "SET_MISMATCH sweep g001"),
                        ("a candidate in two groups", lambda: shifted[-1]["candidates"].append(c0), "SET_MISMATCH sweep groups")):
                    shifted = json.loads(json.dumps(plan_w))
                    g0 = shifted[0]
                    sh0 = next(sh for sh in g0["shards"] if c0 in sh["pairs"])
                    change()
                    named(f"control (done-when 6): {name} is refused by the set accounting", shard_problems(shifted, want), code)
                control("J3a: the plan's set accounting passes", not shard_problems(plan_w, want), f"{shard_problems(plan_w, want)}")
                said = refusal(lambda: sweep_seats({"seats": {"S6.sweep_a": "claude:claude-sonnet-5-5/medium"}}))
                control("control: a declaration without the OpenAI-side sweep's seat is SEAT_UNDECLARED",
                        said.startswith("SEAT_UNDECLARED"), said)
                lifecycle_w = next((k for k in pop_w.values() if k["source"] == "legacy"), None)
                if lifecycle_w is not None:
                    shown_w = guarded(lambda: sweep_view(lifecycle_w, {}, units_w), {})
                    held_w = guarded(lambda: sweep_view(lifecycle_w, labels_w.entry_store, units_w), {})
                    control("J3a: a lifecycle candidate is shown with the texts of the entries it names; a name the stores do "
                            "not hold is counted, as S5 counts one", shown_w.get("entry_texts") == [] and shown_w.get("names_not_held", 0) >= 1
                            and held_w.get("entry_texts") and held_w.get("names_not_held") == 0
                            and not set(held_w) & (set(LIFECYCLE_NAMED) - {"source"}), f"{shown_w} {held_w}")
                # the absence rule itself: a judge missing, and a unit the judges disagree on
                one_side = {"k-x": {"A": {"units": []}}}
                control("J3a: a candidate either judge did not judge is not swept, and is named",
                        guarded(lambda: absent_candidates(["k-x"], one_side, {"k-x": "formed"}), None) == ([], ["k-x"]))
                split = {"k-y": {"A": {"units": [{"unit_id": "u", "situation": "yes", "action": "yes"}]},
                                 "B": {"units": [{"unit_id": "u", "situation": "no", "action": "no"}]}}}
                control("J3a: a candidate whose only unit the judges disagree on is no absence claim (the disputed unit could "
                        "cover it)", guarded(lambda: absent_candidates(["k-y"], split, {"k-y": "formed"}), None) == ([], []))
                agreed_no = {"k-z": {w: {"units": [{"unit_id": "u", "situation": "no", "action": "no"}]} for w in ("A", "B")}}
                control("J3a: a candidate both judges find no unit matching is an absence claim",
                        guarded(lambda: absent_candidates(["k-z"], agreed_no, {"k-z": "formed"}), None) == (["k-z"], []))
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
          "reuse across runs, and A's judgment never answering B; the absence sweeps (J3a) - nothing swept at an "
          "incomplete reference point, the dry upper bound, the absence claims, every remaining unit judged once by each "
          "sweep, one payload bound to the inventory, the re-run reused, SWEEP_INVENTORY_MOVED, the pair and set "
          "accounting refusals planted, a sweep answer missing a pair failed by name, SEAT_UNDECLARED, a lifecycle "
          "candidate's named texts with the names not held counted; Judge B's cross-review (J3b) - every flag and the "
          "drawn fifty, another seed another sample, CROSS_REVIEW_INCOMPLETE and CROSS_REVIEW_STALE planted, a review "
          "missing a unit failed by name, the re-run reusing the rest; the reconsiderations (J3c) - the returned set "
          "both ways, one payload for both judges, contradicted, disputed and standing claims, RECONSIDERATION_MISSING "
          "planted and run, a claim with nothing returned; the reconsideration's units-only shape - its schema the judge "
          "schema's projection with drift planted both ways, candidate-level fields refused by the schema in a run and "
          "by FIELD_UNEXPECTED, the unit rules in the judgment packet's own words; the derivations (J4a) - done-when 2's "
          "disputed, rejected and admitted, every judged candidate derived, the marks and lineages read, the reconsidered "
          "diagnosis carried, no release point, the delivery pairs counted as waiting, an unfinished claim named, no unit "
          "outcome said by name, the type G arc confirmation undetermined and counted, the reconsiderations' receipts held "
          "to N#1 and counted, a run with no S6 budget refused before any call; design §3.2's ten gate controls (J4b) - "
          "planted on copies of an accepted A and B call by host, each rejected by its code, sealed again, the originals "
          "accepted, read by controls.evaluate)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    print("usage: stage_judge.py --self-test (the stage runs as `distill.py judge --run-id ID`)", file=sys.stderr)
    sys.exit(2)
