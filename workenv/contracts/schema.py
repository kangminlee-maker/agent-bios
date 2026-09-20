"""A closed subset of JSON Schema for contract records.

Contract schemas are ordinary JSON Schema documents, so a reader in another language can
check a record with a stock validator. This module reads only the keywords listed in
KEYWORDS and refuses a document that uses any other, at load, by name. A keyword this code
silently ignored would be a rule the document states and nothing here enforces.

Three load rules keep this reader and a stock validator in agreement. The agreement meant is
with a validator that reads `pattern` as ECMAScript does, which is what JSON Schema specifies.
A validator that hands `pattern` to Python's `re.search` differs in one way no schema rule can
close: its `$` also matches before a final newline, so it accepts a string that matches its
pattern and then ends in one newline. This reader refuses that string, as ECMAScript does.

  every object schema states `additionalProperties: false`, so a record is closed under both;
  `pattern` is anchored and drawn from the constructs `compile_pattern` admits, where
  Python's and ECMAScript's regular expressions mean the same thing;
  `$ref` points at `#/$defs/<name>` in the same document and stands alone.

`x-runtime-owned: true` marks a property the runtime writes. Stored records carry it like
any other property. In submit mode its presence is refused by name and its absence is not
a missing field: one authored schema serves both directions. On a document's root it marks a
record the runtime writes whole, such as a result or a receipt, which no submission may be.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .canonical import KEY

UNSUPPORTED_KEYWORD = "unsupported_keyword"
INVALID_SCHEMA = "invalid_schema"
OPEN_OBJECT = "open_object"
UNSUPPORTED_PATTERN = "unsupported_pattern"
UNRESOLVED_REF = "unresolved_ref"

TYPE_MISMATCH = "type_mismatch"
MISSING_FIELD = "missing_field"
UNKNOWN_FIELD = "unknown_field"
RUNTIME_OWNED_FIELD = "runtime_owned_field"
VALUE_NOT_ALLOWED = "value_not_allowed"
PATTERN_MISMATCH = "pattern_mismatch"
LENGTH_OUT_OF_RANGE = "length_out_of_range"
COUNT_OUT_OF_RANGE = "count_out_of_range"
NUMBER_OUT_OF_RANGE = "number_out_of_range"
DUPLICATE_ITEM = "duplicate_item"
VARIANT_MISMATCH = "variant_mismatch"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    UNSUPPORTED_KEYWORD: "a schema keyword outside the closed set this reader implements",
    INVALID_SCHEMA: "a schema document that is malformed or states a rule that checks nothing",
    OPEN_OBJECT: "an object schema that does not state additionalProperties: false",
    UNSUPPORTED_PATTERN: "a pattern outside the constructs Python and ECMAScript read alike",
    UNRESOLVED_REF: "a $ref that is not #/$defs/<name> of a definition in the same document",
    TYPE_MISMATCH: "a value of another JSON type than the schema states",
    MISSING_FIELD: "a required property that is absent",
    UNKNOWN_FIELD: "a property the record's schema does not define",
    RUNTIME_OWNED_FIELD: "a submission that carries a property, or is a record, the runtime "
                         "writes",
    VALUE_NOT_ALLOWED: "a value that differs from the constant or is not among the listed values",
    PATTERN_MISMATCH: "a string that does not match its pattern",
    LENGTH_OUT_OF_RANGE: "a string shorter or longer than its bounds, in code points",
    COUNT_OUT_OF_RANGE: "an array with fewer or more items than its bounds",
    NUMBER_OUT_OF_RANGE: "an integer below its minimum or above its maximum",
    DUPLICATE_ITEM: "an array item equal to an earlier item where items are unique",
    VARIANT_MISMATCH: "a value that not exactly one oneOf variant accepts",
}

STORED = "stored"
SUBMIT = "submit"

RUNTIME_OWNED = "x-runtime-owned"
ANNOTATIONS = frozenset({"$schema", "$id", "title", "description"})
KEYWORDS = ANNOTATIONS | frozenset({
    "$defs", "$ref", "type", "properties", "required", "additionalProperties", "items",
    "minItems", "maxItems", "uniqueItems", "enum", "const", "pattern", "minLength",
    "maxLength", "minimum", "maximum", "oneOf", RUNTIME_OWNED,
})
TYPES = ("object", "array", "string", "integer", "boolean", "null")
# Which assertion keywords each type admits. A keyword on the wrong type asserts nothing in
# JSON Schema, which is how `minLength` on an integer passes review and checks no record.
BY_TYPE = {
    "object": {"properties", "required", "additionalProperties"},
    "array": {"items", "minItems", "maxItems", "uniqueItems"},
    "string": {"pattern", "minLength", "maxLength"},
    "integer": {"minimum", "maximum"},
    "boolean": set(),
    "null": set(),
}
REF = re.compile(r"#/\$defs/([A-Za-z][A-Za-z0-9_]*)\Z")


class SchemaError(ValueError):
    """A schema document this reader refuses. `code` is the stable part."""

    def __init__(self, code: str, pointer: str, detail: str):
        if code not in ERRORS:
            raise LookupError(f"{code!r} is not in this module's rows of the error table")
        super().__init__(f"{code} at {pointer or '/'}: {detail}")
        self.code = code
        self.pointer = pointer
        self.detail = detail


@dataclass(frozen=True)
class Violation:
    code: str
    pointer: str
    detail: str

    def __post_init__(self) -> None:
        if self.code not in ERRORS:
            raise LookupError(f"{self.code!r} is not in this module's rows of the error table")


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


# -- patterns ---------------------------------------------------------------------------

_LITERAL_ESCAPES = set("\\.^$|?*+()[]{}/-")
_CLASS_ESCAPES = {"d", "w"}   # ASCII under re.ASCII, as in ECMAScript without the u flag


def compile_pattern(pattern: str, pointer: str) -> re.Pattern[str]:
    """Compile an anchored pattern from the admitted constructs, or refuse it by name.

    Refused because the two dialects disagree: an unanchored pattern (search against
    fullmatch), `.` (line terminators), `\\s` and `\\b` (Unicode), a `$` that Python lets
    match before a final newline, alternation outside a group (binds looser than the
    anchors), non-ASCII literals, backreferences, lookaround and named groups."""
    def refuse(detail: str) -> SchemaError:
        return SchemaError(UNSUPPORTED_PATTERN, pointer, f"{pattern!r}: {detail}")

    if len(pattern) < 2 or pattern[0] != "^" or pattern[-1] != "$":
        raise refuse("a pattern starts with ^ and ends with $")
    body = pattern[1:-1]
    depth, in_class, index = 0, False, 0
    while index < len(body):
        char = body[index]
        if ord(char) > 0x7E or ord(char) < 0x20:
            raise refuse("only printable ASCII is admitted")
        if char == "\\":
            if index + 1 >= len(body):
                # The body ends in a lone backslash only when it escapes the final $.
                raise refuse("the final $ is escaped, so the pattern has no end anchor")
            following = body[index + 1]
            if following not in _LITERAL_ESCAPES and following not in _CLASS_ESCAPES:
                raise refuse(f"escape \\{following} is not admitted")
            index += 2
            continue
        if in_class:
            if char == "]":
                in_class = False
            elif char == "[":
                raise refuse("nested or POSIX character class")
        elif char == "[":
            in_class = True
            if body[index + 1:index + 2] == "]" or body[index + 1:index + 3] == "^]":
                raise refuse("a character class starts with a member")
        elif char == "(":
            depth += 1
            if body[index + 1:index + 2] == "?" and body[index + 1:index + 3] != "?:":
                raise refuse("only plain and (?:...) groups are admitted")
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise refuse("unbalanced group")
        elif char == "|" and depth == 0:
            raise refuse("alternation outside a group")
        elif char in ".^$":
            raise refuse(f"unescaped {char} inside the pattern")
        index += 1
    if depth != 0 or in_class:
        raise refuse("unbalanced group or character class")
    try:
        return re.compile(f"(?:{body})", re.ASCII)
    except re.error as error:
        raise refuse(str(error)) from None


# -- loading ----------------------------------------------------------------------------

def _non_negative(node: dict[str, Any], key: str, pointer: str) -> None:
    value = node[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaError(INVALID_SCHEMA, f"{pointer}/{key}", "a non-negative integer")


def _integer(node: dict[str, Any], key: str, pointer: str) -> None:
    value = node[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(INVALID_SCHEMA, f"{pointer}/{key}", "an integer")


class Schema:
    """A loaded schema document. Build with `load_schema`; check records with `validate`."""

    def __init__(self, document: Any):
        self.document = document
        self.patterns: dict[str, re.Pattern[str]] = {}
        self.refs: list[tuple[str, str]] = []
        if not isinstance(document, dict):
            raise SchemaError(INVALID_SCHEMA, "", "a schema document is an object")
        defs = document.get("$defs", {})
        if not isinstance(defs, dict):
            raise SchemaError(INVALID_SCHEMA, "/$defs", "an object of named schemas")
        self.defs = defs
        self._node(document, "", root=True)
        for name, node in defs.items():
            if not REF.match(f"#/$defs/{name}"):
                raise SchemaError(INVALID_SCHEMA, f"/$defs/{_escape(name)}", "not a referable name")
            self._node(node, f"/$defs/{_escape(name)}")
        for pointer, name in self.refs:
            if name not in defs:
                raise SchemaError(UNRESOLVED_REF, pointer, f"#/$defs/{name} is not defined")
        self._no_bare_cycle()

    def _node(self, node: Any, pointer: str, root: bool = False) -> None:
        if not isinstance(node, dict):
            raise SchemaError(INVALID_SCHEMA, pointer, "a schema is an object")
        for key in node:
            if key not in KEYWORDS:
                raise SchemaError(UNSUPPORTED_KEYWORD, f"{pointer}/{_escape(str(key))}",
                                  f"{key!r} is outside the closed keyword set")
        if "$defs" in node and not root:
            raise SchemaError(INVALID_SCHEMA, f"{pointer}/$defs", "only the document root defines")
        for key in ANNOTATIONS & node.keys():
            if not isinstance(node[key], str):
                raise SchemaError(INVALID_SCHEMA, f"{pointer}/{key}", "a string")
        if RUNTIME_OWNED in node and node[RUNTIME_OWNED] is not True:
            raise SchemaError(INVALID_SCHEMA, f"{pointer}/{RUNTIME_OWNED}", "true or absent")
        asserting = node.keys() - ANNOTATIONS - {"$defs", RUNTIME_OWNED}

        if "$ref" in node:
            match = isinstance(node["$ref"], str) and REF.match(node["$ref"])
            if not match:
                raise SchemaError(UNRESOLVED_REF, f"{pointer}/$ref", "only #/$defs/<name>")
            if asserting != {"$ref"}:
                raise SchemaError(INVALID_SCHEMA, pointer, "$ref stands alone")
            self.refs.append((f"{pointer}/$ref", match.group(1)))
            return
        if "oneOf" in node:
            variants = node["oneOf"]
            if asserting != {"oneOf"} or not isinstance(variants, list) or len(variants) < 2:
                raise SchemaError(INVALID_SCHEMA, pointer, "oneOf stands alone over two or more")
            for index, variant in enumerate(variants):
                self._node(variant, f"{pointer}/oneOf/{index}")
            return
        for key in ("enum", "const"):
            if key in node:
                if asserting != {key}:
                    raise SchemaError(INVALID_SCHEMA, pointer, f"{key} stands alone")
                if key == "enum" and (not isinstance(node[key], list) or not node[key]):
                    raise SchemaError(INVALID_SCHEMA, f"{pointer}/enum", "a non-empty array")
                return

        kind = node.get("type")
        if not isinstance(kind, str) or kind not in TYPES:
            raise SchemaError(INVALID_SCHEMA, f"{pointer}/type", f"one of {', '.join(TYPES)}")
        stray = asserting - {"type"} - BY_TYPE[kind]
        if stray:
            raise SchemaError(INVALID_SCHEMA, pointer,
                              f"{sorted(stray)} assert nothing about type {kind}")
        if kind == "object":
            self._object(node, pointer)
        elif kind == "array":
            if "items" not in node:
                raise SchemaError(INVALID_SCHEMA, pointer, "an array schema states its items")
            self._node(node["items"], f"{pointer}/items")
            for key in ("minItems", "maxItems"):
                if key in node:
                    _non_negative(node, key, pointer)
            if "uniqueItems" in node and not isinstance(node["uniqueItems"], bool):
                raise SchemaError(INVALID_SCHEMA, f"{pointer}/uniqueItems", "a boolean")
        elif kind == "string":
            for key in ("minLength", "maxLength"):
                if key in node:
                    _non_negative(node, key, pointer)
            if "pattern" in node:
                where = f"{pointer}/pattern"
                if not isinstance(node["pattern"], str):
                    raise SchemaError(INVALID_SCHEMA, where, "a string")
                self.patterns[where] = compile_pattern(node["pattern"], where)
        elif kind == "integer":
            for key in ("minimum", "maximum"):
                if key in node:
                    _integer(node, key, pointer)

    def _object(self, node: dict[str, Any], pointer: str) -> None:
        if node.get("additionalProperties") is not False:
            raise SchemaError(OPEN_OBJECT, pointer,
                              "an object schema states additionalProperties: false")
        properties = node.get("properties", {})
        if not isinstance(properties, dict):
            raise SchemaError(INVALID_SCHEMA, f"{pointer}/properties", "an object")
        for name, child in properties.items():
            if not KEY.match(name):
                # The canonical encoder refuses such a key, so no record could carry it.
                raise SchemaError(INVALID_SCHEMA, f"{pointer}/properties/{_escape(name)}",
                                  "a property name is ASCII snake_case")
            self._node(child, f"{pointer}/properties/{_escape(name)}")
        required = node.get("required", [])
        if not isinstance(required, list) or len(set(map(str, required))) != len(required):
            raise SchemaError(INVALID_SCHEMA, f"{pointer}/required", "an array of distinct names")
        for name in required:
            if name not in properties:
                raise SchemaError(INVALID_SCHEMA, f"{pointer}/required",
                                  f"{name!r} is required and not a property")

    def _no_bare_cycle(self) -> None:
        """Refuse a definition that reaches itself without consuming any of the value.

        `$ref` and `oneOf` hand the same value on, so a cycle through them alone never
        returns. A cycle through `properties` or `items` descends into the value and ends
        when the value does, which is how a recursive record is written."""
        def onward(node: dict[str, Any]) -> list[str]:
            if "$ref" in node:
                return [REF.match(node["$ref"]).group(1)]
            return [name for variant in node.get("oneOf", []) for name in onward(variant)]

        done: set[str] = set()

        def walk(name: str, path: tuple[str, ...]) -> None:
            if name in path:
                raise SchemaError(INVALID_SCHEMA, f"/$defs/{_escape(name)}",
                                  "reaches itself through $ref and oneOf alone")
            if name in done:
                return
            for following in onward(self.defs[name]):
                walk(following, path + (name,))
            done.add(name)

        for name in self.defs:
            walk(name, ())

    # -- validation ---------------------------------------------------------------------

    def validate(self, value: Any, mode: str = STORED) -> list[Violation]:
        if mode not in (STORED, SUBMIT):
            raise ValueError(f"mode is {STORED!r} or {SUBMIT!r}")
        found: list[Violation] = []
        if mode == SUBMIT and self._runtime_owned(self.document):
            return [Violation(RUNTIME_OWNED_FIELD, "",
                              "the runtime writes this record; it is never a submission")]
        self._check(self.document, "", value, "", mode, found)
        return found

    def _check(self, node: dict[str, Any], at: str, value: Any, pointer: str, mode: str,
               found: list[Violation]) -> None:
        if "$ref" in node:
            name = REF.match(node["$ref"]).group(1)
            self._check(self.defs[name], f"/$defs/{_escape(name)}", value, pointer, mode, found)
            return
        if "oneOf" in node:
            passing = 0
            for index, variant in enumerate(node["oneOf"]):
                inner: list[Violation] = []
                self._check(variant, f"{at}/oneOf/{index}", value, pointer, mode, inner)
                passing += not inner
            if passing != 1:
                found.append(Violation(VARIANT_MISMATCH, pointer,
                                       f"{passing} of {len(node['oneOf'])} variants accept it"))
            return
        if "const" in node:
            if not _same(value, node["const"]):
                found.append(Violation(VALUE_NOT_ALLOWED, pointer, "differs from the constant"))
            return
        if "enum" in node:
            if not any(_same(value, allowed) for allowed in node["enum"]):
                found.append(Violation(VALUE_NOT_ALLOWED, pointer, "not one of the listed values"))
            return

        kind = node["type"]
        if not _is(kind, value):
            found.append(Violation(TYPE_MISMATCH, pointer, f"expected {kind}"))
            return
        if kind == "object":
            self._check_object(node, at, value, pointer, mode, found)
        elif kind == "array":
            count = len(value)
            if count < node.get("minItems", 0) or count > node.get("maxItems", count):
                found.append(Violation(COUNT_OUT_OF_RANGE, pointer, f"{count} item(s)"))
            if node.get("uniqueItems"):
                for index, item in enumerate(value):
                    if any(_same(item, earlier) for earlier in value[:index]):
                        found.append(Violation(DUPLICATE_ITEM, f"{pointer}/{index}",
                                               "equal to an earlier item"))
            for index, item in enumerate(value):
                self._check(node["items"], f"{at}/items", item, f"{pointer}/{index}", mode, found)
        elif kind == "string":
            length = len(value)
            if length < node.get("minLength", 0) or length > node.get("maxLength", length):
                found.append(Violation(LENGTH_OUT_OF_RANGE, pointer, f"{length} character(s)"))
            if "pattern" in node and not self.patterns[f"{at}/pattern"].fullmatch(value):
                found.append(Violation(PATTERN_MISMATCH, pointer, node["pattern"]))
        elif kind == "integer":
            if value < node.get("minimum", value) or value > node.get("maximum", value):
                found.append(Violation(NUMBER_OUT_OF_RANGE, pointer, str(value)))

    def _check_object(self, node: dict[str, Any], at: str, value: dict[str, Any], pointer: str,
                      mode: str, found: list[Violation]) -> None:
        properties = node.get("properties", {})
        for name in value:
            if name not in properties:
                found.append(Violation(UNKNOWN_FIELD, f"{pointer}/{_escape(name)}",
                                       "not a property of this record"))
        for name in node.get("required", []):
            owned = self._runtime_owned(properties[name])
            if name not in value and not (mode == SUBMIT and owned):
                found.append(Violation(MISSING_FIELD, f"{pointer}/{_escape(name)}", "required"))
        for name, child in properties.items():
            if name not in value:
                continue
            where = f"{pointer}/{_escape(name)}"
            if mode == SUBMIT and self._runtime_owned(child):
                found.append(Violation(RUNTIME_OWNED_FIELD, where,
                                       "the runtime writes this field; a submission omits it"))
                continue
            self._check(child, f"{at}/properties/{_escape(name)}", value[name], where, mode,
                        found)

    def _runtime_owned(self, node: dict[str, Any]) -> bool:
        return node.get(RUNTIME_OWNED) is True


def _is(kind: str, value: Any) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return value is None


def _same(left: Any, right: Any) -> bool:
    """JSON equality. Python's == says True equals 1; the exact-type test on the last line
    is what keeps a boolean from satisfying an integer constant, at any depth."""
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(map(_same, left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    return type(left) is type(right) and left == right


def load_schema(document: Any) -> Schema:
    """A Schema, or SchemaError naming the first thing this reader refuses."""
    return Schema(document)
