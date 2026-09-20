"""Reading a contract record by the kind and version it states.

A contract record is a canonical object whose `kind` names what it is and whose `schema` is
the integer version of that kind's shape. A schema document describes a record kind when its
root fixes both as constants. `registry` derives the (kind, version) table from the documents
themselves, so there is no second list to keep in step, and `load` is the one entrance a
reader uses: canonical bytes, then the kind's schema in the asked mode.

A record whose kind is unknown, or whose version this reader does not hold, is refused by
name and is never checked against a neighbouring version: a field the reader does not know
may carry a rule it would break.

The contract modules (`c01`, `c02`, ...) own the refusals an operation answers with. Those
travel inside a result record, in `material_gaps`, and `stated` collects them from a value.
"""
from __future__ import annotations

from typing import Any

from . import canonical
from .schema import STORED, Schema, Violation

NOT_A_RECORD = "not_a_record"
UNKNOWN_RECORD_KIND = "unknown_record_kind"
UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    NOT_A_RECORD: "a value that is not an object stating a string kind and an integer schema",
    UNKNOWN_RECORD_KIND: "a record kind no contract schema describes",
    UNSUPPORTED_SCHEMA_VERSION: "a version of a known record kind this reader does not hold",
}

GAPS = "material_gaps"


class RecordError(ValueError):
    """A record refused before its own schema is reached. `code` is the stable part."""

    def __init__(self, code: str, pointer: str, detail: str):
        if code not in ERRORS:
            raise LookupError(f"{code!r} is not in this module's rows of the error table")
        super().__init__(f"{code} at {pointer or '/'}: {detail}")
        self.code = code
        self.pointer = pointer
        self.detail = detail


def describes(loaded: Schema) -> tuple[str, int] | None:
    """(kind, version) when the document's root fixes both as constants, else None."""
    root = loaded.document
    properties = root.get("properties") if root.get("type") == "object" else None
    if not isinstance(properties, dict):
        return None
    kind = properties.get("kind", {}).get("const")
    version = properties.get("schema", {}).get("const")
    if not isinstance(kind, str) or isinstance(version, bool) or not isinstance(version, int):
        return None
    if not {"kind", "schema"} <= set(root.get("required", [])):
        return None
    return kind, version


def registry(schemas: dict[str, Schema]) -> dict[str, dict[int, str]]:
    """kind -> version -> schema id, or ValueError when two documents describe one pair."""
    table: dict[str, dict[int, str]] = {}
    for identifier, loaded in sorted(schemas.items()):
        described = describes(loaded)
        if described is None:
            continue
        kind, version = described
        holder = table.setdefault(kind, {})
        if version in holder:
            raise ValueError(f"record kind {kind!r} version {version} is described by "
                             f"{holder[version]} and {identifier}")
        holder[version] = identifier
    return table


def resolve(value: Any, kinds: dict[str, dict[int, str]]) -> str:
    """The id of the schema that describes `value`, or RecordError."""
    if not isinstance(value, dict):
        raise RecordError(NOT_A_RECORD, "", "a record is an object")
    kind, version = value.get("kind"), value.get("schema")
    if not isinstance(kind, str):
        raise RecordError(NOT_A_RECORD, "/kind", "a record states its kind as a string")
    if isinstance(version, bool) or not isinstance(version, int):
        raise RecordError(NOT_A_RECORD, "/schema", "a record states its version as an integer")
    if kind not in kinds:
        raise RecordError(UNKNOWN_RECORD_KIND, "/kind", repr(kind))
    if version not in kinds[kind]:
        held = ", ".join(map(str, sorted(kinds[kind])))
        raise RecordError(UNSUPPORTED_SCHEMA_VERSION, "/schema",
                          f"{kind} version {version}; this reader holds {held}")
    return kinds[kind][version]


def load(data: bytes, schemas: dict[str, Schema],
         mode: str = STORED) -> tuple[Any, str, list[Violation]]:
    """(value, schema id, violations) for stored bytes. CanonicalError or RecordError when
    the bytes never reach a schema."""
    value = canonical.load(data)
    identifier = resolve(value, registry(schemas))
    return value, identifier, schemas[identifier].validate(value, mode)


def stated(value: Any) -> set[str]:
    """Every gap code a value carries: the `code` of each object in a `material_gaps` array,
    at any depth."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == GAPS and isinstance(item, list):
                found.update(row["code"] for row in item
                             if isinstance(row, dict) and isinstance(row.get("code"), str))
            found |= stated(item)
    elif isinstance(value, list):
        for item in value:
            found |= stated(item)
    return found
