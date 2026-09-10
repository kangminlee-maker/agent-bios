#!/usr/bin/env python3
"""Learning record gate + validator (collection loop, Phase 0).

learn/learning.schema.json is the SSOT for the learning record
(design/collection-loop/DESIGN.md); the dashboard mirrors only minimal
validation. Full client-side validity = JSON Schema conformance PLUS domain
membership in compose/domains.json domains ∪ 'unclassified' — membership is
checked here, not frozen in the schema, so vocabulary evolution never needs
a schema_version bump.

Modes:
  (no args)     gate: schema validates against its 2020-12 metaschema;
                every fixtures/valid-*.json passes; every fixtures/broken-*.json
                fails AND the failure names the field the fixture breaks
                (a broken fixture failing for an unrelated reason is a FAIL);
                non-vacuity: >=1 valid fixture, >=1 broken fixture,
                >=1 registered domain.
  <file.json>…  validate the given record file(s); exit 0 iff all valid.
                This is the client-side validation entry point for Phase 1.
  --self-test   negative controls: in-memory mutations of a valid record
                (each required field dropped, plus type/pattern/membership
                mutations) must ALL be rejected; the unmutated record must
                pass. Proves the gate can fail.

Any violation exits 1 with all violations listed.
"""
import json
import pathlib
import sys

try:
    import jsonschema
except ImportError:
    sys.exit("check-learning: the 'jsonschema' package is required "
             "(pip install jsonschema; verified 4.26.0 in DEPENDENCIES.md)")

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = REPO / "learn" / "learning.schema.json"
DOMAINS = REPO / "compose" / "domains.json"
FIXTURES = REPO / "design" / "collection-loop" / "fixtures"

# broken fixture -> field its single defect lives in; the reported errors
# must mention it, so a fixture failing for an accidental other reason fails
# the gate instead of silently passing as "broken as expected".
BROKEN_EXPECT = {
    "broken-missing-lesson.json": "lesson",
    "broken-unknown-domain.json": "domain",
    "broken-schema-version.json": "schema_version",
    "broken-extra-field.json": "email",
    "broken-empty-sessions.json": "supporting_sessions",
    "broken-bad-created.json": "created",
    "broken-proposed-domain-conflict.json": "domain",
    "broken-bad-classification.json": "classification",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def valid_domain_values(path=DOMAINS):
    """The set a record's `domain` may take, drawn from compose/domains.json.

    Ledger-compatible (design/session-distill/ledger.json): the ledger's
    `domain` field uses BOTH domain keys (builder-base, …) for
    domain-specific lessons AND tier names (core, infra, …) for cross-cutting
    ones — 4 real entries carry core/infra. So the valid set is the union of
    both registered vocabularies plus 'unclassified' (refinement B — the
    not-yet-triaged escape; kept distinct from 'core', which means a genuinely
    cross-cutting lesson). Reuses existing vocabulary; introduces none.
    """
    manifest = load_json(path)
    values = set(manifest["domains"]) | set(manifest["tiers"]) | {"unclassified"}
    if len(values) <= 1:
        sys.exit("FAIL: compose/domains.json registers no domains/tiers (vacuous gate)")
    return values


def validate_record(record, validator, domain_values):
    """Full validity: schema conformance + domain membership. Returns error strings."""
    errors = []
    for e in validator.iter_errors(record):
        where = "/".join(str(p) for p in e.path) or "<root>"
        errors.append(f"{where}: {e.message}")
    if isinstance(record, dict):
        dom = record.get("domain")
        if isinstance(dom, str) and dom not in domain_values:
            errors.append(
                f"domain: {dom!r} is not a registered domain key, tier name, "
                f"or 'unclassified' (compose/domains.json)")
    # A lone surrogate is a valid `str` and a valid JSON Schema "string", so everything
    # above passes it — and then the first `json.dumps(..., ensure_ascii=False)` refuses
    # to encode it. That surfaced as a UnicodeEncodeError traceback out of the write in
    # collect-learning rather than as a rejection, so the check belongs here, where every
    # consumer of a record already asks whether it is valid. `ensure_ascii=False` is the
    # form the writers use and the reason CJK stays readable in the artifacts; encoding
    # is what actually fails, so the check performs it rather than scanning code points.
    try:
        json.dumps(record, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError as exc:
        errors.append(
            f"<root>: record is not encodable as UTF-8 (unpaired surrogate or "
            f"similar): {exc}")
    return errors


def build_validator():
    schema = load_json(SCHEMA)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def gate():
    validator = build_validator()
    domain_values = valid_domain_values()
    failures = []

    valid_fx = sorted(FIXTURES.glob("valid-*.json"))
    broken_fx = sorted(FIXTURES.glob("broken-*.json"))
    if not valid_fx:
        failures.append(f"no valid-*.json fixtures in {FIXTURES} (vacuous)")
    if not broken_fx:
        failures.append(f"no broken-*.json fixtures in {FIXTURES} (vacuous)")

    for fx in valid_fx:
        errors = validate_record(load_json(fx), validator, domain_values)
        if errors:
            failures.append(f"{fx.name} must validate but failed: {'; '.join(errors)}")

    for fx in broken_fx:
        errors = validate_record(load_json(fx), validator, domain_values)
        expect = BROKEN_EXPECT.get(fx.name)
        if expect is None:
            failures.append(f"{fx.name} has no BROKEN_EXPECT entry (unmapped negative control)")
        elif not errors:
            failures.append(f"{fx.name} must FAIL but validated (negative control broken)")
        elif not any(expect in err for err in errors):
            failures.append(
                f"{fx.name} failed for the wrong reason (expected mention of "
                f"{expect!r}): {'; '.join(errors)}")
    for name in BROKEN_EXPECT:
        if not (FIXTURES / name).is_file():
            failures.append(f"BROKEN_EXPECT names a missing fixture: {name}")

    if failures:
        print("check-learning: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"check-learning: OK ({len(valid_fx)} valid, "
          f"{len(broken_fx)} negative controls)")
    return 0


def self_test():
    validator = build_validator()
    domain_values = valid_domain_values()
    base = load_json(FIXTURES / "valid-minimal.json")
    schema = load_json(SCHEMA)

    def drop(field):
        r = dict(base)
        del r[field]
        return r

    def swap(field, value):
        return {**base, field: value}

    mutations = [(f"drop required '{f}'", drop(f), f) for f in schema["required"]]
    mutations += [
        ("schema_version as string", swap("schema_version", "1"), "schema_version"),
        ("uppercase learning_id", swap("learning_id", base["learning_id"].upper()), "learning_id"),
        ("lesson below minLength", swap("lesson", "short"), "lesson"),
        ("capitalized domain", swap("domain", "Builder-Base"), "domain"),
        ("session id without tool prefix", swap("supporting_sessions", ["517fbcea"]), "supporting_sessions"),
        ("created without T/zone", swap("created", "20260720T050000Z"), "created"),
        ("unknown extra key", {**base, "user_email": "x@y"}, "user_email"),
        ("classification type out of A-G enum", swap("classification", {"type": "Z"}), "classification"),
        ("classification unknown sub-key", swap("classification", {"mechanism": "x"}), "classification"),
        ("proposed_domain with a concrete domain", {**base, "proposed_domain": "data-pipeline", "domain": "builder-base"}, "domain"),
        ("lone surrogate in lesson", swap("lesson", "unpaired \ud800 surrogate"), "not encodable as UTF-8"),
    ]

    failures = []
    if validate_record(base, validator, domain_values):
        failures.append("positive control (valid-minimal) does not validate")
    # positive control: a tier-name domain (real ledger precedent) must pass.
    if validate_record({**base, "domain": "core"}, validator, domain_values):
        failures.append("positive control (domain='core' tier name) does not validate")
    # positive control: the optional slim classification block must pass.
    if validate_record({**base, "classification": {"type": "B", "layer": "hook", "meets_bar": True}}, validator, domain_values):
        failures.append("positive control (valid classification block) does not validate")
    # positive control: proposed_domain rides only with an unclassified domain (base is unclassified).
    if validate_record({**base, "proposed_domain": "data-pipeline"}, validator, domain_values):
        failures.append("positive control (proposed_domain + unclassified) does not validate")
    # positive control: the encodability check must not reject non-ASCII text, which is
    # the only reason the writers pass ensure_ascii=False in the first place.
    if validate_record({**base, "lesson": "한국어 교훈은 그대로 남는다"}, validator, domain_values):
        failures.append("positive control (non-ASCII lesson) does not validate")
    for name, record, expect in mutations:
        errors = validate_record(record, validator, domain_values)
        if not errors:
            failures.append(f"mutation NOT caught: {name}")
        elif not any(expect in err for err in errors):
            failures.append(f"mutation caught for the wrong reason: {name} -> {errors}")

    if failures:
        print("check-learning --self-test: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"check-learning --self-test: OK ({len(mutations)} mutations caught, "
          f"5 positive controls)")
    return 0


def validate_files(paths):
    validator = build_validator()
    domain_values = valid_domain_values()
    rc = 0
    for p in paths:
        # Client entry point (Phase 1): inputs are not hand-authored fixtures,
        # so malformed JSON / unreadable files report cleanly, never a traceback.
        try:
            record = load_json(p)
        except (json.JSONDecodeError, OSError) as e:
            rc = 1
            print(f"INVALID {p}")
            print(f"  - not readable JSON: {e}")
            continue
        errors = validate_record(record, validator, domain_values)
        if errors:
            rc = 1
            print(f"INVALID {p}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"OK {p}")
    return rc


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--self-test"]:
        sys.exit(self_test())
    if args:
        sys.exit(validate_files(args))
    sys.exit(gate())
