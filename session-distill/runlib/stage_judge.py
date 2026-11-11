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

  stage_judge.py --self-test
"""
import hashlib
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import packet, validate  # noqa: E402
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
    payload = "line one\nline two\n"
    control("the same payload to both seats is no divergence", not divergence({"A": payload, "B": payload}))
    named("done-when 1 control: a seat-specific line injected into one payload is PACKET_DIVERGENCE",
          divergence({"A": payload, "B": payload + "You are Judge B.\n"}), "PACKET_DIVERGENCE")
    built = {seat: packet.build(f"r1-S6-k1-{seat}-a1", STAGE, s, payload, None)
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

    for failure in failures:
        print(f"stage_judge --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stage_judge --self-test: OK ({len(ran)} controls: done-when 8's two halves - the judgment schema's fields "
          "against §6.2's both ways and the reuse key's components against §6.2's, each with a planted drift; D12's key "
          "per candidate, unit and seat, changed by each component; done-when 1's one payload and one receipt per call "
          "with PACKET_DIVERGENCE and RECEIPT_STALE planted; D14's quotes and every unit, matching unit and ledger entry "
          "judged once, each refusal planted; D11's classes from the schema's enum)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    print("usage: stage_judge.py --self-test (the stage runs as `distill.py judge --run-id ID`)", file=sys.stderr)
    sys.exit(2)
