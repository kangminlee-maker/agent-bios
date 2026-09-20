"""Contract examples: raw byte files, each with its expectation beside it.

An example is bytes, not parsed JSON, because the things a contract refuses first — a key
stated twice, whitespace, a float — cannot be written down as parsed JSON. Beside every
`examples/<group>/<name>.json` sits `<name>.expect.json`, a canonical record that says what the
example is and what must happen to it:

  subject `bytes`   the example goes to `canonical.load` alone
  subject `schema`  the example is a schema document: `canonical.parse`, then `load_schema`
  subject `record`  `canonical.load`, then validation against the named schema in a mode

`check` runs every example and compares. It fails by name on an example without an expectation
or the reverse, on an empty example set, on a schema no accepted example and no refused example
exercises, and — through `errors.coverage` — on an error code no example exercises and on an
expectation naming a code the table does not hold.

Fixture identity is measured, never declared: `index.json` lists every schema, example and
expectation with the sha256 and size this module read, and a test fails a stale one.

  python3 -m workenv.contracts.examples --emit     # rewrite examples/index.json
  python3 -m workenv.contracts.examples            # run every example
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
from typing import Any

from . import canonical, errors
from .schema import Schema, SchemaError, load_schema

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


def outcome(example: bytes, expectation: dict[str, Any],
            schemas: dict[str, Schema]) -> list[dict[str, str]]:
    """What actually happens to the example: [] when accepted, else the refusals as
    code-and-pointer rows, in the shape an expectation states them."""
    subject = expectation["subject"]
    try:
        if subject == "bytes":
            canonical.load(example)
            return []
        if subject == "schema":
            load_schema(canonical.parse(example))
            return []
        value = canonical.load(example)
    except canonical.CanonicalError as error:
        return [{"code": error.code, "pointer": ""}]
    except SchemaError as error:
        return [{"code": error.code, "pointer": error.pointer}]
    found = schemas[expectation["schema"]].validate(value, expectation["mode"])
    return [{"code": v.code, "pointer": v.pointer} for v in found]


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

    exercised: set[str] = set()
    accepted: dict[str, int] = dict.fromkeys(schemas, 0)
    refused: dict[str, int] = dict.fromkeys(schemas, 0)
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
        got = outcome(example.read_bytes(), expectation, schemas)
        exercised.update(row["code"] for row in want)
        if got != want:
            problems.append(f"{name}: expected {want or 'acceptance'}, got {got or 'acceptance'}")
        if expectation["subject"] == "record":
            (refused if want else accepted)[expectation["schema"]] += 1
    for identifier in schemas:
        report.append(f"schema {identifier}: {accepted[identifier]} accepted, "
                      f"{refused[identifier]} refused")
        if not accepted[identifier]:
            problems.append(f"schema {identifier}: no example it accepts")
        if not refused[identifier]:
            problems.append(f"schema {identifier}: no example it refuses")
    problems += errors.coverage(exercised)
    return problems, report


def index(schemas_dir: pathlib.Path = SCHEMAS, examples_dir: pathlib.Path = EXAMPLES) -> bytes:
    """The fixture identities as canonical bytes: every schema, example and expectation, by
    path relative to this package, with the sha256 and size read from disk."""
    files = sorted(schemas_dir.glob(f"*{SCHEMA_SUFFIX}"))
    files += sorted(p for p in examples_dir.rglob("*.json") if p != examples_dir / INDEX.name)
    rows = []
    for path in files:
        data = path.read_bytes()
        rows.append({"path": path.relative_to(schemas_dir.parent).as_posix(),
                     "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
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
