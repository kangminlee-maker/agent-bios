"""Canonical bytes and digests for contract records.

One owner for the byte form a record is stored, hashed and signed in. The form is compact
JSON with sorted keys and UTF-8 output. The admitted value domain is narrower than JSON on
purpose: object keys are ASCII snake_case, numbers are integers a double holds exactly, and
strings are valid Unicode. Inside that domain the bytes are the ones RFC 8785 defines, so a
reader in another language needs no agent-bios code to reproduce a digest.

Stored bytes are the hash input. `load` therefore refuses bytes that are valid JSON but not
the canonical form of their own value, instead of re-encoding them and hashing something the
writer never stored.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

INVALID_UTF8 = "invalid_utf8"
INVALID_JSON = "invalid_json"
DUPLICATE_KEY = "duplicate_key"
INVALID_KEY = "invalid_key"
UNSUPPORTED_NUMBER = "unsupported_number"
UNSUPPORTED_TYPE = "unsupported_type"
NESTING_TOO_DEEP = "nesting_too_deep"
NON_CANONICAL_BYTES = "non_canonical_bytes"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    INVALID_UTF8: "bytes that are not UTF-8, or a string holding a lone surrogate",
    INVALID_JSON: "bytes that are not one JSON value",
    DUPLICATE_KEY: "an object that states one key more than once",
    INVALID_KEY: "an object key that is not ASCII snake_case",
    UNSUPPORTED_NUMBER: "a number that is not an integer a double holds exactly",
    UNSUPPORTED_TYPE: "a value that is not null, a boolean, an integer, a string, an array "
                      "or an object",
    NESTING_TOO_DEEP: "containers nested more than 64 deep",
    NON_CANONICAL_BYTES: "bytes that are valid but are not the canonical form of their value",
}

# Codes no byte example can reach, each with its reason. `errors.coverage` exempts exactly
# these from the rule that a negative example exercises every code, and fails an exemption an
# example does exercise. Their control is a unit test.
NOT_FROM_BYTES = {
    UNSUPPORTED_TYPE: "JSON text has no other type; only a Python value handed to encode does",
}

KEY = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
# Integers beyond this are not exact in an IEEE 754 double, which is what RFC 8785 serializes.
MAX_SAFE_INTEGER = 2**53 - 1
# Containers inside containers, the outermost counting as 1. A stated number, so that a reader
# in another language refuses the same records; an interpreter's own recursion limit would
# make the answer depend on the host.
MAX_DEPTH = 64


class CanonicalError(ValueError):
    """A value or byte string outside the canonical domain. `code` is the stable part."""

    def __init__(self, code: str, detail: str):
        if code not in ERRORS:
            raise LookupError(f"{code!r} is not in this module's rows of the error table")
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _check(value: Any, where: str, depth: int = 0) -> None:
    if value is None:
        return
    if isinstance(value, int):
        # Booleans arrive here too, as the integers 0 and 1, and pass; json writes them
        # as true and false.
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(UNSUPPORTED_NUMBER, f"{where}: integer outside the exact range")
        return
    if isinstance(value, float):
        raise CanonicalError(UNSUPPORTED_NUMBER, f"{where}: only integers are admitted")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise CanonicalError(INVALID_UTF8, f"{where}: lone surrogate in a string") from None
        return
    if isinstance(value, (list, dict)) and depth >= MAX_DEPTH:
        raise CanonicalError(NESTING_TOO_DEEP, f"{where}: more than {MAX_DEPTH} containers deep")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check(item, f"{where}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not KEY.match(key):
                raise CanonicalError(INVALID_KEY, f"{where}: key {key!r} is not ASCII snake_case")
            _check(item, f"{where}.{key}", depth + 1)
        return
    raise CanonicalError(UNSUPPORTED_TYPE, f"{where}: {type(value).__name__}")


def encode(value: Any) -> bytes:
    """The canonical bytes of `value`, or CanonicalError when it is outside the domain."""
    try:
        _check(value, "$")
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False)
    except RecursionError:
        raise CanonicalError(NESTING_TOO_DEEP,
                             "value nests deeper than the encoder walks") from None
    return text.encode("utf-8")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, item in pairs:
        if key in seen:
            raise CanonicalError(DUPLICATE_KEY, f"key {key!r} appears more than once")
        seen[key] = item
    return seen


def _not_json(text: str) -> Any:
    # Python's parser admits NaN, Infinity and -Infinity; RFC 8259 does not.
    raise CanonicalError(INVALID_JSON, f"{text} is not a JSON value")


def parse(data: bytes) -> Any:
    """One JSON value from UTF-8 bytes, with no key stated twice and no NaN or Infinity.

    For authored documents such as schemas, whose keys (`$ref`, `additionalProperties`) are
    outside the canonical domain. A record is read with `load`, which also requires the
    canonical form."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CanonicalError(INVALID_UTF8, "stored bytes are not UTF-8") from None
    try:
        # A float literal parses here; `encode` refuses it with every other float.
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_not_json)
    except RecursionError:
        raise CanonicalError(NESTING_TOO_DEEP, "bytes nest deeper than the parser walks") from None
    except json.JSONDecodeError as error:
        raise CanonicalError(INVALID_JSON, f"{error.msg} at character {error.pos}") from None
    except CanonicalError:
        raise
    except ValueError:
        # The interpreter's own limit on integer literal length; no such integer is exact.
        raise CanonicalError(UNSUPPORTED_NUMBER, "integer literal too long to parse") from None


def load(data: bytes) -> Any:
    """Parse stored bytes, refusing anything that is not the canonical form of its value."""
    value = parse(data)
    if encode(value) != data:
        raise CanonicalError(NON_CANONICAL_BYTES,
                             "bytes differ from the canonical form of their value")
    return value


def digest(data: bytes) -> str:
    """sha256 of stored bytes, which must already be canonical."""
    load(data)
    return hashlib.sha256(data).hexdigest()


def digest_of(value: Any) -> str:
    """sha256 of the canonical bytes of `value`."""
    return hashlib.sha256(encode(value)).hexdigest()
