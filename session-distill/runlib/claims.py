#!/usr/bin/env python3
"""The record schemas every later stage keeps: claim, evidence, expected observation, event, observation.

They are `session-distill/schemas/<kind>.schema.json`, loaded through `validate.compile_schema`
(`check_schema`, then the schema-policy lint). Each carries `$comment: "design §X"` and its
`required` set is the field list of that design section: §3.3 (claim records), §5.5 (evidence
locators, plus `window_role` from §5.2), §7.3 (proposal content, the expected observation), §5.4 (events,
the field list of the implementation plan's WP-08 artifacts) and §11 (an observation instance, the same).
The `--self-test` holds the lists, copied once and cited, and fails naming the schema and the section when a
schema's field set differs; it also names the consumer of every field, so a field no later
stage reads cannot enter a schema unnoticed.

The two answers S3's calls return (`read.schema.json`, `stitch.schema.json`) are held to the same copies by
`answer_mismatch`: a reading's claim object is §3.3's, its vocabularies are the stored records', and what code
sets - an observation's coverage basis, an event's `unresolved` and `stitched_from` - is never answered.

  claims.py --self-test
"""
import ast
import copy
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import validate

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / "schemas"
KINDS = ("claim", "evidence", "expected_observation", "event", "observation")
ANSWERS = ("read", "stitch")   # what S3's calls return; each holds the stored records' contracts, never its own


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


def returned_literals(source, function):
    """The string constants `function` of `source` returns: the vocabulary a predicate can answer in."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            return sorted({n.value.value for n in ast.walk(node) if isinstance(n, ast.Return)
                           and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)})
    return []


def answer_mismatch(answers, stored, claim_contract, basis, basis_returns, decisions):
    """Where S3's two answer schemas depart from the records they become (WP-08 done-when 8).

    `answers` and `stored` map a kind to its schema; `claim_contract` is §3.3's field list, `basis` §5.4's
    three words, `basis_returns` what `views.coverage_basis` can return, `decisions` `views.DECISIONS`. A
    reading's claim object is §3.3's; an observation's exposure and verdict are the stored instance's and its
    basis is never answered (code sets it over the scope, §5.4); a window's event is the stored event without
    `unresolved` or `stitched_from` (the stitch call's), and a stitch answers resolved or unresolved, never
    pending."""
    errors = []
    defs = answers["read"].get("$defs", {})
    errors += contract_mismatch("read.claim", defs.get("claim", {}), "§3.3", claim_contract)

    def enum(schema, field):
        return sorted((schema.get("properties", {}).get(field) or {}).get("enum", []))

    def differ(name, section, have, want):
        if sorted(have) != sorted(want):
            errors.append(f"CONTRACT_MISMATCH {name} (design {section}): {sorted(have)} is not {sorted(want)}")

    observation, event = stored["observation"], stored["event"]
    differ("observation.basis", "§5.4", enum(observation, "basis"), basis)
    differ("views.coverage_basis returns", "§5.4", basis_returns, basis)
    answered = defs.get("observation", {})
    differ("read.observation fields", "§11", answered.get("properties", {}),
           set(observation.get("properties", {})) - {"basis"})
    for field in ("exposure", "verdict"):
        differ(f"read.observation.{field}", "§11", enum(answered, field), enum(observation, field))
    window_event = defs.get("event", {})
    differ("read.event fields", "§5.4", window_event.get("properties", {}),
           set(event.get("properties", {})) - {"stitched_from"})
    differ("read.event.outcome", "§5.4", enum(window_event, "outcome"), set(enum(event, "outcome")) - {"unresolved"})
    resolution = answers["stitch"].get("$defs", {}).get("resolution", {})
    differ("stitch.resolution.outcome", "§5.4", enum(resolution, "outcome"), set(enum(event, "outcome")) - {"pending"})
    differ("read.decision.decision", "§5.4", enum(defs.get("decision", {}), "decision"), decisions)
    return errors


def self_test():
    # The field lists of the design sections, copied here once (WP-01 done-when 5). A second
    # copy anywhere else is a second authority; the cross-provider review of this module
    # compares these three against the design text.
    contract = {
        "claim": ("§3.3", ("claim_id", "fact", "interpretation", "uncertainty", "evidence_ids", "call_id"), ()),
        # §5.5's list, and `window_role` from §5.2 ("every evidence record carries window_role"; plan WP-06 done-when 7)
        "evidence": ("§5.5", ("evidence_id", "source_copy", "version_sha", "line", "json_pointer",
                              "char_span", "redaction_version", "redacted_text", "window_role"), ()),
        "expected_observation": ("§7.3", ("occasion_criteria", "exposure_rule", "expected_behavior",
                                          "retrieval_terms", "expiry"), ("counter", "threshold")),
        # §5.4 names events and their outcomes; the field list is the implementation plan's WP-08 artifacts
        "event": ("§5.4", ("event_id", "kind", "at_record", "claim_ids", "outcome", "description", "stitched_from"), ()),
        # §11's instance, with §5.4's basis; the field list is the implementation plan's WP-08 artifacts
        "observation": ("§11", ("expected_id", "occasion_locator", "exposure", "verdict", "basis", "evidence_ids"), ()),
    }
    # §5.4's three coverage bases, in its checking order (WP-08 done-when 8)
    basis = ("incomplete", "view", "source")
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
            "window_role": "WP-08 done-when 5 and WP-10: only in_window evidence counts toward occasions and recurrence (design §5.2)",
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
        "event": {
            "event_id": "WP-08 done-when 3: the stitch call answers for it by id; coverage.json's pending_events carries it (WP-05)",
            "kind": "WP-09: S4 forms candidates with set accounting over events (design §4)",
            "at_record": "WP-08: an event belongs to the window of its first record (design §5.2); a pending one forces expansion (§5.4)",
            "claim_ids": "WP-08 done-when 3: the stitch call receives the claims; WP-09 S4",
            "outcome": "WP-08 done-when 3: a unit with pending events and no stitch call is read_partial",
            "description": "WP-08 done-when 3: the stitch call receives it; WP-20 render",
            "stitched_from": "WP-08 done-when 3: a stitched resolution names the claims it was resolved with",
        },
        "observation": {
            "expected_id": "WP-08 measures.derive_resolution: the window resolution is derived per expected observation (design §11)",
            "occasion_locator": "WP-20 render: where the occasion is",
            "exposure": "WP-08 measures.derive_resolution: an exposure_unknown occasion leaves the resolution pending (design §11)",
            "verdict": "WP-08 measures.derive_resolution: not observed / observed (design §11)",
            "basis": "WP-08 measures.derive_resolution: an absence needs basis source (design §5.4, §11)",
            "evidence_ids": "WP-08 done-when 5: each instance is judged with evidence ids; WP-20 render",
        },
    }
    valid = {
        "claim": {"claim_id": "c-1", "fact": "The owner asked for the plain version twice.",
                  "interpretation": "The first explanation was too technical.",
                  "uncertainty": "Two occurrences in one session.", "evidence_ids": ["e-1", "e-2"],
                  "call_id": "r1/S3/t1/1"},
        "evidence": {"evidence_id": "e-1", "source_copy": "sources/" + "ab" * 32 + ".jsonl",
                     "version_sha": "ab" * 32, "line": 12, "json_pointer": "/message/content/0/text",
                     "char_span": [0, 40], "redaction_version": "r1", "redacted_text": "show me the plain version",
                     "window_role": "in_window"},
        "expected_observation": {"occasion_criteria": "the owner asks for an explanation",
                                 "exposure_rule": "the unit was delivered before the ask",
                                 "expected_behavior": "no second request for the plain version",
                                 "retrieval_terms": ["plain version", "explain"], "expiry": "2026-12-31"},
        "event": {"event_id": "v-1", "kind": "request", "at_record": "4/message/content", "claim_ids": ["c-1"],
                  "outcome": "pending", "description": "The owner asked for a rerun; its result is not in this window.",
                  "stitched_from": []},
        "observation": {"expected_id": "x-1", "occasion_locator": "12/message/content", "exposure": "eligible",
                        "verdict": "observed", "basis": "view", "evidence_ids": ["e-1"]},
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
        ("evidence", "window_role outside the three", put("window_role", "elsewhere"), "window_role:"),
        ("evidence", "backlog without its window", put("window_role", "backlog()"), "window_role:"),
        ("evidence", "json_pointer without a leading slash", put("json_pointer", "message/content"), "json_pointer:"),
        ("expected_observation", "retrieval_terms empty", put("retrieval_terms", []), "retrieval_terms:"),
        ("expected_observation", "counter without threshold", put("counter", "plain-explanation asks"), "'threshold' is a dependency of"),
        ("expected_observation", "threshold without counter", put("threshold", 0.5), "'counter' is a dependency of"),
        ("event", "outcome outside the three", put("outcome", "open"), "outcome:"),
        ("event", "an event no claim describes", put("claim_ids", []), "claim_ids:"),
        ("observation", "a fourth coverage basis", put("basis", "partial"), "basis:"),
        ("observation", "exposure outside §11's two", put("exposure", "exposed"), "exposure:"),
        ("observation", "verdict outside §11's two", put("verdict", "maybe"), "verdict:"),
        ("observation", "an instance judged without evidence", put("evidence_ids", []), "evidence_ids:"),
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

    # S3's answers (WP-08 done-when 8): the two schemas the model answers in, held to the stored records' copies.
    # `views` is read for its basis predicate and its decision vocabulary only, inside the test: the schemas
    # are leaves, and nothing at import time may make them depend on the stage that cuts windows.
    from runlib import views
    answers = {}
    for kind in ANSWERS:
        try:
            answers[kind] = read_schema(kind)
            validator_for(kind)
        except Exception as exc:
            failures.append(f"positive control: the {kind} answer schema did not load: {exc!r}")
    stored = {kind: read_schema(kind) for kind in ("event", "observation")}
    basis_returns = returned_literals(pathlib.Path(views.__file__).read_text(encoding="utf-8"), "coverage_basis")

    def answer_problems(answers=answers, stored=stored, returns=basis_returns):
        return answer_mismatch(answers, stored, contract["claim"][1], basis, returns, views.DECISIONS)

    answer_mutations = []
    if len(answers) == len(ANSWERS):
        for problem in answer_problems():
            failures.append(f"positive control: {problem}")
        if not basis_returns:
            failures.append("positive control: views.coverage_basis returns no literal the check could read")

        def planted(kind, edit, schemas):
            copied = copy.deepcopy(schemas)
            edit(copied[kind])
            return copied

        claim_of = lambda s: s["$defs"]["claim"]  # noqa: E731
        answer_mutations = [
            ("a fourth coverage basis in the stored instance", lambda: answer_problems(
                stored=planted("observation", lambda s: s["properties"]["basis"]["enum"].append("partial"), stored)),
             "CONTRACT_MISMATCH observation.basis (design §5.4)"),
            ("a fourth basis the predicate can return", lambda: answer_problems(returns=sorted(basis_returns + ["partial"])),
             "CONTRACT_MISMATCH views.coverage_basis returns (design §5.4)"),
            ("a claim field added to the reading's claim object", lambda: answer_problems(
                answers=planted("read", lambda s: (claim_of(s)["required"].append("revises"),
                                                   claim_of(s)["properties"].update(revises={"type": "string"})), answers)),
             "CONTRACT_MISMATCH read.claim (design §3.3): required adds ['revises']"),
            ("a §3.3 field dropped from the reading's claim object", lambda: answer_problems(
                answers=planted("read", lambda s: (claim_of(s)["required"].remove("uncertainty"),
                                                   claim_of(s)["properties"].pop("uncertainty")), answers)),
             "CONTRACT_MISMATCH read.claim (design §3.3): required lacks ['uncertainty']"),
            ("the model answering the coverage basis", lambda: answer_problems(
                answers=planted("read", lambda s: s["$defs"]["observation"]["properties"].update(
                    basis={"type": "string", "enum": list(basis)}), answers)),
             "CONTRACT_MISMATCH read.observation fields (design §11)"),
            ("a window answering unresolved", lambda: answer_problems(
                answers=planted("read", lambda s: s["$defs"]["event"]["properties"]["outcome"]["enum"].append("unresolved"),
                                answers)),
             "CONTRACT_MISMATCH read.event.outcome (design §5.4)"),
            ("a stitch answering pending", lambda: answer_problems(
                answers=planted("stitch", lambda s: s["$defs"]["resolution"]["properties"]["outcome"]["enum"].append("pending"),
                                answers)),
             "CONTRACT_MISMATCH stitch.resolution.outcome (design §5.4)"),
            ("an exposure the stored instance cannot hold", lambda: answer_problems(
                answers=planted("read", lambda s: s["$defs"]["observation"]["properties"]["exposure"]["enum"].append("exposed"),
                                answers)),
             "CONTRACT_MISMATCH read.observation.exposure (design §11)"),
            # X review of WP-08 r1 #3: each comparison has a departure only it names
            ("a window answering what the stitch records (stitched_from)", lambda: answer_problems(
                answers=planted("read", lambda s: s["$defs"]["event"]["properties"].update(
                    stitched_from={"type": "array", "items": {"type": "string"}}), answers)),
             "CONTRACT_MISMATCH read.event fields (design §5.4)"),
            ("a verdict the stored instance cannot hold", lambda: answer_problems(
                answers=planted("read", lambda s: s["$defs"]["observation"]["properties"]["verdict"]["enum"].append("unclear"),
                                answers)),
             "CONTRACT_MISMATCH read.observation.verdict (design §11)"),
            ("a decision other than expand or skip", lambda: answer_problems(
                answers=planted("read", lambda s: s["$defs"]["decision"]["properties"]["decision"]["enum"].append("defer"),
                                answers)),
             "CONTRACT_MISMATCH read.decision.decision (design §5.4)"),
        ]
        for label, problems, fragment in answer_mutations:
            found = problems()
            if not any(fragment in line for line in found):
                failures.append(f"answer contract control not named: {label} -> {found}")
        planted_source = "def coverage_basis(scope):\n    if scope:\n        return 'incomplete'\n    return 'partial'\n"
        if returned_literals(planted_source, "coverage_basis") != ["incomplete", "partial"]:
            failures.append("returned_literals control: a planted predicate's literals were not read")

    for failure in failures:
        print(f"claims --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"claims --self-test: OK ({len(KINDS)} schemas match §3.3, §5.5, §7.3, §5.4, §11; "
          f"{sum(len(c) for c in consumers.values())} fields each name a consumer; "
          f"{len(mutations)} record mutations and {6 * len(KINDS)} schema mutations rejected by name; "
          f"{len(ANSWERS)} answer schemas hold the stored contracts, {len(answer_mutations)} departures named)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: claims.py --self-test")
    sys.exit(self_test())
