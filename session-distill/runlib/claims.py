#!/usr/bin/env python3
"""The three record schemas every later stage keeps: claim, evidence, expected observation.

They are `session-distill/schemas/<kind>.schema.json`, loaded through `validate.compile_schema`
(`check_schema`, then the schema-policy lint). Each carries `$comment: "design §X"` and its
`required` set is the field list of that design section: §3.3 (claim records), §5.5 (evidence
locators), §7.3 (proposal content, the expected observation). The `--self-test` holds the
three lists, copied once and cited, and fails naming the schema and the section when a
schema's field set differs; it also names the consumer of every field, so a field no later
stage reads cannot enter a schema unnoticed.

  claims.py --self-test
"""
import copy
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import validate

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / "schemas"
KINDS = ("claim", "evidence", "expected_observation")


def read_schema(kind, schema_dir=SCHEMA_DIR):
    return json.loads((pathlib.Path(schema_dir) / f"{kind}.schema.json").read_text(encoding="utf-8"))


def validator_for(kind, schema_dir=SCHEMA_DIR):
    return validate.compile_schema(read_schema(kind, schema_dir))


def validate_record(kind, record, schema_dir=SCHEMA_DIR):
    """Violations of one record against its kind's schema; empty when it conforms."""
    return validate.validate_instance(validator_for(kind, schema_dir), record)


def contract_mismatch(kind, schema, section, required, together=()):
    """Where `schema` departs from the field list `section` of the design gives.

    `required` are the fields every record carries; `together` are fields the section makes
    conditional that must be present as a group or not at all."""
    errors = []
    if not str(schema.get("$comment", "")).startswith(f"design {section}"):
        errors.append(f"CONTRACT_MISMATCH {kind} (design {section}): $comment does not cite the section")
    want, have = set(required), set(schema.get("required", []))
    for verb, fields in (("lacks", sorted(want - have)), ("adds", sorted(have - want))):
        if fields:
            errors.append(f"CONTRACT_MISMATCH {kind} (design {section}): required {verb} {fields}")
    declared = set(schema.get("properties", {}))
    for verb, fields in (("lacks", sorted((want | set(together)) - declared)),
                         ("adds", sorted(declared - want - set(together)))):
        if fields:
            errors.append(f"CONTRACT_MISMATCH {kind} (design {section}): properties {verb} {fields}")
    group = {name: sorted(set(together) - {name}) for name in together}
    if schema.get("dependentRequired", {}) != group:
        errors.append(f"CONTRACT_MISMATCH {kind} (design {section}): dependentRequired is not {group}")
    return errors


def unconsumed_fields(schema, consumers):
    """Properties of `schema` that name no consumer: the inert-field rule, as a check."""
    return sorted(set(schema.get("properties", {})) - set(consumers))


def self_test():
    # The field lists of the design sections, copied here once (WP-01 done-when 5). A second
    # copy anywhere else is a second authority; the cross-provider review of this module
    # compares these three against the design text.
    contract = {
        "claim": ("§3.3", ("claim_id", "fact", "interpretation", "uncertainty", "evidence_ids", "call_id"), ()),
        "evidence": ("§5.5", ("evidence_id", "source_copy", "version_sha", "line", "json_pointer",
                              "char_span", "redaction_version", "redacted_text"), ()),
        "expected_observation": ("§7.3", ("occasion_criteria", "exposure_rule", "expected_behavior",
                                          "retrieval_terms", "expiry"), ("counter", "threshold")),
    }
    # Every field and the work package that reads it (the inert-field rule): a field enters a
    # schema when a later stage consumes it, and this table is where that is said.
    consumers = {
        "claim": {
            "claim_id": "WP-08: S3 writes claims/<transcript>.jsonl; events and WP-09 candidates refer to a claim by it",
            "fact": "WP-21 done-when 13: render and ledger project it unchanged",
            "interpretation": "WP-21 done-when 13: render and ledger project it unchanged",
            "uncertainty": "WP-21 done-when 13: render and ledger project it unchanged",
            "evidence_ids": "WP-08 done-when 1: every claim's evidence records resolve (quote fidelity)",
            "call_id": "WP-02 gate: cross-record integrity, design §3.2 item 4",
        },
        "evidence": {
            "evidence_id": "WP-08: a claim's evidence_ids resolve to it",
            "source_copy": "WP-06 done-when 1 (locator resolves to the immutable copy); WP-20 render (openable path)",
            "version_sha": "WP-06 done-when 1: SOURCE_TAMPERED when the copy's hash differs",
            "line": "WP-20 render: the openable line in the source copy (design §5.5)",
            "json_pointer": "WP-06 done-when 1: locates the content block the projection is taken from",
            "char_span": "WP-06 done-when 1: the span of the block the quote covers",
            "redaction_version": "WP-06 done-when 1: REDACTION_VERSION_MISMATCH",
            "redacted_text": "WP-08 done-when 1: QUOTE_MISMATCH when a model retypes the quote",
        },
        "expected_observation": {
            "occasion_criteria": "WP-08 done-when 5: reading finds the occasions where it holds",
            "exposure_rule": "WP-21: the table-driven exposure predicate of design §11",
            "expected_behavior": "WP-08 done-when 5: each occasion is judged observed or not observed against it",
            "retrieval_terms": "WP-06: the full-source search; WP-08: the expansion it forces",
            "expiry": "WP-09: lifecycle intake of incubates whose expiry is on or before the window end",
            "counter": "WP-21: the plain-asks adapter of design §11",
            "threshold": "WP-21: the plain-asks adapter resolves by it (design §11)",
        },
    }
    valid = {
        "claim": {"claim_id": "c-1", "fact": "The owner asked for the plain version twice.",
                  "interpretation": "The first explanation was too technical.",
                  "uncertainty": "Two occurrences in one session.", "evidence_ids": ["e-1", "e-2"],
                  "call_id": "r1/S3/t1/1"},
        "evidence": {"evidence_id": "e-1", "source_copy": "sources/" + "ab" * 32 + ".jsonl",
                     "version_sha": "ab" * 32, "line": 12, "json_pointer": "/message/content/0/text",
                     "char_span": [0, 40], "redaction_version": "r1", "redacted_text": "show me the plain version"},
        "expected_observation": {"occasion_criteria": "the owner asks for an explanation",
                                 "exposure_rule": "the unit was delivered before the ask",
                                 "expected_behavior": "no second request for the plain version",
                                 "retrieval_terms": ["plain version", "explain"], "expiry": "2026-12-31"},
    }
    # one rejected mutation per row: (kind, name, mutate(record), a fragment the violation must carry)
    def drop(field):
        return lambda r: {k: v for k, v in r.items() if k != field}

    def put(field, value):
        return lambda r: {**r, field: value}

    mutations = [(kind, f"drop required {field}", drop(field), f"'{field}' is a required property")
                 for kind, (_s, fields, _t) in contract.items() for field in fields]
    mutations += [
        ("claim", "unknown field", put("revises", "c-0"), "Additional properties"),
        ("claim", "empty fact", put("fact", ""), "fact:"),
        ("claim", "evidence_ids repeat an id", put("evidence_ids", ["e-1", "e-1"]), "evidence_ids:"),
        ("evidence", "version_sha not a sha256", put("version_sha", "abc"), "version_sha:"),
        ("evidence", "line as a string", put("line", "12"), "line:"),
        ("evidence", "line below 1", put("line", 0), "line:"),
        ("evidence", "char_span of three numbers", put("char_span", [0, 1, 2]), "char_span:"),
        ("evidence", "json_pointer without a leading slash", put("json_pointer", "message/content"), "json_pointer:"),
        ("expected_observation", "retrieval_terms empty", put("retrieval_terms", []), "retrieval_terms:"),
        ("expected_observation", "counter without threshold", put("counter", "plain-explanation asks"), "'threshold' is a dependency of"),
        ("expected_observation", "threshold without counter", put("threshold", 0.5), "'counter' is a dependency of"),
    ]

    failures = []
    for kind in KINDS:
        section, fields, together = contract[kind]
        try:  # positive controls first: the schema loads, matches its section, and takes a valid record
            schema = read_schema(kind)
            validator_for(kind)
        except Exception as exc:
            failures.append(f"positive control: {kind} schema did not load: {exc!r}")
            continue
        for problem in contract_mismatch(kind, schema, section, fields, together):
            failures.append(f"positive control: {problem}")
        for field in unconsumed_fields(schema, consumers[kind]):
            failures.append(f"positive control: {kind}.{field} names no consumer")
        if sorted(set(consumers[kind]) - set(schema["properties"])):
            failures.append(f"positive control: {kind} consumers name a field the schema lacks")
        if validate_record(kind, valid[kind]):
            failures.append(f"positive control: the valid {kind} record was rejected: {validate_record(kind, valid[kind])}")
    full = {**valid["expected_observation"], "counter": "plain-explanation asks", "threshold": 0.5}
    if validate_record("expected_observation", full):
        failures.append("positive control: an expected observation with counter and threshold was rejected")

    for kind, name, mutate, fragment in mutations:
        found = validate_record(kind, mutate(valid[kind]))
        if not found:
            failures.append(f"mutation NOT caught: {kind}: {name}")
        elif not any(fragment in line for line in found):
            failures.append(f"mutation caught for the wrong reason: {kind}: {name} -> {found}")

    # the contract check itself: a schema that departs from its section is named with both
    for kind in KINDS:
        section, fields, together = contract[kind]
        base = read_schema(kind)
        extra = copy.deepcopy(base)
        extra["required"].append("extra_field")
        extra["properties"]["extra_field"] = {"type": "string"}
        lacking = copy.deepcopy(base)
        lacking["required"].remove(fields[0])
        recited = copy.deepcopy(base)
        recited["$comment"] = "design §0.0"
        for label, schema, fragment in (
                ("one field added to required", extra, "required adds ['extra_field']"),
                ("one field removed from required", lacking, f"required lacks ['{fields[0]}']"),
                ("citation of another section", recited, "$comment does not cite the section")):
            found = contract_mismatch(kind, schema, section, fields, together)
            if not any(f"CONTRACT_MISMATCH {kind} (design {section})" in line and fragment in line for line in found):
                failures.append(f"contract control not named: {kind}: {label} -> {found}")
        if unconsumed_fields(extra, consumers[kind]) != ["extra_field"]:
            failures.append(f"inert-field control: {kind}: a property with no consumer was not reported")
        unlisted = copy.deepcopy(base)  # a property that is not required is still a field of the record
        unlisted["properties"]["extra_field"] = {"type": "string"}
        unlinked = copy.deepcopy(base)
        unlinked["dependentRequired"] = {"extra_field": ["extra_field"]}
        for label, schema, fragment in (("a property added without being required", unlisted, "properties adds ['extra_field']"),
                                        ("a property removed with its requirement kept",
                                         {**base, "properties": {k: v for k, v in base["properties"].items() if k != fields[0]}},
                                         f"properties lacks ['{fields[0]}']"),
                                        ("dependentRequired changed", unlinked, "dependentRequired is not")):
            found = contract_mismatch(kind, schema, section, fields, together)
            if not any(f"CONTRACT_MISMATCH {kind} (design {section})" in line and fragment in line for line in found):
                failures.append(f"contract control not named: {kind}: {label} -> {found}")
    open_schema = copy.deepcopy(read_schema("claim"))
    del open_schema["additionalProperties"]
    try:
        validate.compile_schema(open_schema)
        failures.append("a claim schema without additionalProperties: false was accepted")
    except validate.SchemaPolicyError:
        pass

    for failure in failures:
        print(f"claims --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"claims --self-test: OK ({len(KINDS)} schemas match §3.3, §5.5, §7.3; "
          f"{sum(len(c) for c in consumers.values())} fields each name a consumer; "
          f"{len(mutations)} record mutations and {6 * len(KINDS)} schema mutations rejected by name)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: claims.py --self-test")
    sys.exit(self_test())
