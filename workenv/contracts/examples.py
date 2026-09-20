"""Contract examples: raw byte files, each with its expectation beside it.

An example is bytes, not parsed JSON, because the things a contract refuses first — a key
stated twice, whitespace, a float — cannot be written down as parsed JSON. Beside every
`examples/<group>/<name>.json` sits `<name>.expect.json`, a canonical record that says what the
example is and what must happen to it:

  subject `bytes`   the example goes to `canonical.load` alone
  subject `schema`  the example is a schema document: `canonical.parse`, then `load_schema`
  subject `record`  `canonical.load`, then validation against the named schema in a mode
  subject `dispatched`  `records.load`: the schema is the one the record's own kind and
                    version select, which is how a reader meets a contract record

`check` runs every example and compares. It fails by name on an example without an expectation
or the reverse, on an empty example set, on a schema no accepted example and no refused example
exercises, and — through `errors.coverage` — on an error code no example exercises, on a gap
code no accepted result states, and on an example naming a code the table does not hold.

Three more rules hold the contract records together. Every place a schema marks as written by
the runtime has a submission that is refused for carrying it. Mark the record root, not a
property inside a `oneOf` variant: a variant that refuses is a variant that did not match, so
the branch is reported and the field can never name itself, and no example could satisfy this
rule for it. A definition name means one thing:
two documents that both define `$defs/<name>` define it identically, because `$ref` cannot
cross documents and a copy that drifts would be a second vocabulary. And an `operation_result`
example answers an `operation_request` example that exists: its `request_digest` is the
sha256 of that example's bytes.

Fixture identity is measured, never declared: `index.json` lists every schema, example and
expectation with the digest and size this module read, and a test fails a stale one.

  python3 -m workenv.contracts.examples --emit     # rewrite examples/index.json
  python3 -m workenv.contracts.examples            # run every example
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from . import c03, canonical, errors, inventory, records
from .schema import RUNTIME_OWNED, RUNTIME_OWNED_FIELD, Schema, SchemaError, load_schema

ROOT = pathlib.Path(__file__).parent
SCHEMAS = ROOT / "schemas"
EXAMPLES = ROOT / "examples"
INDEX = EXAMPLES / "index.json"
INDEX_SCHEMA = 1
EXPECT_SUFFIX = ".expect.json"
SCHEMA_SUFFIX = ".schema.json"
EXPECTATION = "expectation"


def load_schemas(directory: pathlib.Path = SCHEMAS) -> dict[str, Schema]:
    """Schema id -> loaded schema, for every `<id>.schema.json` in the directory."""
    loaded = {}
    for path in sorted(directory.glob(f"*{SCHEMA_SUFFIX}")):
        loaded[path.name[:-len(SCHEMA_SUFFIX)]] = load_schema(canonical.parse(path.read_bytes()))
    return loaded


def pairs(directory: pathlib.Path = EXAMPLES) -> tuple[list[pathlib.Path], list[str]]:
    """(examples that have an expectation, problems about the ones that do not pair up)."""
    files = sorted(p for p in directory.rglob("*.json") if p != directory / INDEX.name)
    examples = [p for p in files if not p.name.endswith(EXPECT_SUFFIX)]
    expectations = {p for p in files if p.name.endswith(EXPECT_SUFFIX)}
    problems, paired = [], []
    for example in examples:
        expectation = expectation_path(example)
        if expectation in expectations:
            expectations.discard(expectation)
            paired.append(example)
        else:
            problems.append(f"{example.relative_to(directory)} has no expectation beside it")
    problems += [f"{p.relative_to(directory)} expects something of an example that is absent"
                 for p in sorted(expectations)]
    return paired, problems


def expectation_path(example: pathlib.Path) -> pathlib.Path:
    return example.with_name(example.name[:-len(".json")] + EXPECT_SUFFIX)


def outcome(example: bytes, expectation: dict[str, Any], schemas: dict[str, Schema],
            ) -> tuple[list[dict[str, str]], str | None, Any]:
    """What actually happens to the example: (refusals, schema id, value). Refusals are []
    when accepted, else code-and-pointer rows in the shape an expectation states them. The
    schema id is None when the example never reached a schema, the value None when the bytes
    never became one."""
    subject = expectation["subject"]
    identifier = expectation.get("schema")
    try:
        if subject == "bytes":
            canonical.load(example)
            return [], None, None
        if subject == "schema":
            load_schema(canonical.parse(example))
            return [], None, None
        value = canonical.load(example)
        if subject == "dispatched":
            identifier = records.resolve(value, records.registry(schemas))
    except canonical.CanonicalError as error:
        return [{"code": error.code, "pointer": ""}], None, None
    except (SchemaError, records.RecordError) as error:
        return [{"code": error.code, "pointer": error.pointer}], None, None
    found = schemas[identifier].validate(value, expectation["mode"])
    return [{"code": v.code, "pointer": v.pointer} for v in found], identifier, value


def owned_places(loaded: Schema) -> set[str]:
    """Where a schema says the runtime writes: property paths without array indices, and ""
    for a record the runtime writes whole."""
    places: set[str] = set()

    def walk(node: dict[str, Any], path: str, through: tuple[str, ...]) -> None:
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            if name not in through:
                walk(loaded.defs[name], path, through + (name,))
            return
        for variant in node.get("oneOf", []):
            walk(variant, path, through)
        if node.get("type") == "array":
            walk(node["items"], path, through)
        for name, child in node.get("properties", {}).items():
            if child.get(RUNTIME_OWNED) is True:
                places.add(f"{path}/{name}")
            else:
                walk(child, f"{path}/{name}", through)

    if loaded.document.get(RUNTIME_OWNED) is True:
        return {""}
    walk(loaded.document, "", ())
    return places


def without_indices(pointer: str) -> str:
    return "/".join(token for token in pointer.split("/") if not token.isdigit())


def shared_definitions(schemas: dict[str, Schema]) -> list[str]:
    """Problems about a definition name two documents give different meanings."""
    first: dict[str, tuple[str, Any]] = {}
    problems = []
    for identifier, loaded in sorted(schemas.items()):
        for name, node in loaded.defs.items():
            if name not in first:
                first[name] = (identifier, node)
            elif canonical_form(first[name][1]) != canonical_form(node):
                problems.append(f"$defs/{name} differs between schemas {first[name][0]} and "
                                f"{identifier}; one name has one meaning")
    return problems


def canonical_form(node: Any) -> str:
    # Schema keys such as $ref are outside the record key domain, so compare as sorted JSON.
    return json.dumps(node, sort_keys=True)


def check(schemas_dir: pathlib.Path = SCHEMAS,
          examples_dir: pathlib.Path = EXAMPLES) -> tuple[list[str], list[str]]:
    """(problems, report lines). No problem means every example behaved as its expectation
    says and the error table and the examples agree both ways."""
    report = []
    try:
        schemas = load_schemas(schemas_dir)
    except (SchemaError, canonical.CanonicalError) as error:
        return [f"a contract schema does not load: {error}"], report
    report.append(f"schemas: {len(schemas)}")
    if EXPECTATION not in schemas:
        return [f"schemas/{EXPECTATION}{SCHEMA_SUFFIX} is absent, so no expectation can be "
                f"read"], report
    paired, problems = pairs(examples_dir)
    report.append(f"examples: {len(paired)}")
    if not paired:
        problems.append("empty subject set: no example with an expectation")

    try:
        records.registry(schemas)
    except ValueError as error:
        return problems + [str(error)], report
    problems += shared_definitions(schemas)

    exercised: set[str] = set()
    stated: set[str] = set()
    accepted: dict[str, int] = dict.fromkeys(schemas, 0)
    refused: dict[str, int] = dict.fromkeys(schemas, 0)
    submit_refused: dict[str, set[str]] = {identifier: set() for identifier in schemas}
    requests: dict[str, str] = {}
    answers: list[tuple[str, Any]] = []
    for example in paired:
        name = str(example.relative_to(examples_dir))
        try:
            expectation = canonical.load(expectation_path(example).read_bytes())
        except canonical.CanonicalError as error:
            problems.append(f"{name}: its expectation is not a canonical record: {error}")
            continue
        malformed = schemas[EXPECTATION].validate(expectation)
        if malformed:
            first = malformed[0]
            problems.append(f"{name}: its expectation is malformed: {first.code} at "
                            f"{first.pointer or '/'}")
            continue
        if expectation["subject"] == "record" and expectation["schema"] not in schemas:
            problems.append(f"{name}: expects schema {expectation['schema']!r}, which is absent")
            continue
        want = expectation.get("refusals", [])
        data = example.read_bytes()
        got, identifier, value = outcome(data, expectation, schemas)
        exercised.update(row["code"] for row in want)
        if got != want:
            problems.append(f"{name}: expected {want or 'acceptance'}, got {got or 'acceptance'}")
        if identifier is None:
            continue
        (refused if want else accepted)[identifier] += 1
        # Only a submission is refused with this code, so the mode needs no second test.
        submit_refused[identifier].update(without_indices(row["pointer"]) for row in got
                                          if row["code"] == RUNTIME_OWNED_FIELD)
        if not want:
            stated |= records.stated(value)
            if value.get("kind") == "operation_request":
                requests[canonical.digest(data)] = value["request_id"]
            elif value.get("kind") == "operation_result":
                answers.append((name, value))
    for identifier in schemas:
        report.append(f"schema {identifier}: {accepted[identifier]} accepted, "
                      f"{refused[identifier]} refused")
        if not accepted[identifier]:
            problems.append(f"schema {identifier}: no example it accepts")
        if not refused[identifier]:
            problems.append(f"schema {identifier}: no example it refuses")
        for place in sorted(owned_places(schemas[identifier]) - submit_refused[identifier]):
            problems.append(f"schema {identifier}: the runtime writes {place or 'the whole record'}"
                            f" and no submission is refused for carrying it")
    for name, value in answers:
        digest = value.get("request_digest")
        if digest is None:
            if c03.REQUEST_UNKNOWN not in records.stated(value):
                problems.append(f"{name}: names no request digest and does not state "
                                f"{c03.REQUEST_UNKNOWN}")
        elif requests.get(digest) != value["request_id"]:
            problems.append(f"{name}: answers request {value['request_id']} with digest "
                            f"{digest[:12]}, and no request example has both")
    problems += errors.coverage(exercised, stated)
    return problems, report


def index(schemas_dir: pathlib.Path = SCHEMAS, examples_dir: pathlib.Path = EXAMPLES) -> bytes:
    """The fixture identities as canonical bytes. It is an inventory of this package's own
    files, so it is built by the same walk and in the same vocabulary as a source revision's:
    `inventory.members`, by path relative to this package, with the digest and size on disk."""
    files = sorted(schemas_dir.glob(f"*{SCHEMA_SUFFIX}"))
    files += sorted(p for p in examples_dir.rglob("*.json") if p != examples_dir / INDEX.name)
    rows = inventory.members(schemas_dir.parent, files)
    return canonical.encode({"schema": INDEX_SCHEMA, "files": rows})


def main(argv: list[str]) -> int:
    if argv == ["--emit"]:
        INDEX.write_bytes(index())
        print(f"wrote {INDEX.relative_to(ROOT)}")
        return 0
    if argv:
        print("usage: python3 -m workenv.contracts.examples [--emit]")
        return 2
    problems, report = check()
    if not INDEX.is_file() or INDEX.read_bytes() != index():
        problems.append(f"{INDEX.relative_to(ROOT)} is stale; run python3 -m "
                        f"workenv.contracts.examples --emit")
    for line in report:
        print(line)
    for line in problems:
        print(f"FAIL: {line}")
    if not problems:
        print("CONTRACT EXAMPLES OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
