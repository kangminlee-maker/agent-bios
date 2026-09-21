"""Contract representation tests. Run by gates/workenv/check-workenv.py, one process per file."""
import ast
import contextlib
import functools
import io
import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from workenv.contracts import (  # noqa: E402
    b01, b02, b03, b04, b05, c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12,
    canonical, errors, examples, inventory, records, schema,
)



@functools.lru_cache(maxsize=None)
def committed_schemas():
    return examples.load_schemas()


def reader_says(rel):
    """(what the committed reader reports, what the committed expectation states) for one
    committed example, each as sorted (code, pointer) pairs, read in the example's own mode."""
    path = examples.EXAMPLES / f"{rel}.json"
    expectation = canonical.load(examples.expectation_path(path).read_bytes())
    _, _, found = records.load(path.read_bytes(), committed_schemas(), expectation["mode"])
    return (sorted((v.code, v.pointer) for v in found),
            sorted((r["code"], r["pointer"]) for r in expectation.get("refusals", [])))


class NamedExamples:
    """A rule test names the committed example that shows its rule. Loosening the rule then fails
    the test that states it, instead of whichever check happens to read the same bytes; and a
    rule the schema stops applying (a definition left in place but no longer used) is seen, which
    reading the definition cannot see."""

    def assertRefused(self, at, *rels):
        """Each example is refused as its expectation states, and only at `at` or under it: the
        place its rule refuses. Naming the place is what stops the expectation being moved to
        another refusal — another mode, another field — while the rule is loosened."""
        self.assertTrue(rels)
        for rel in rels:
            got, want = reader_says(rel)
            self.assertTrue(want, f"{rel} is not a refused example")
            self.assertEqual(got, want, rel)
            for _, pointer in got:
                self.assertTrue(pointer == at or pointer.startswith(f"{at}/"),
                                f"{rel} is refused at {pointer}, not at {at}")

    def assertAccepted(self, *rels):
        for rel in rels:
            self.assertEqual(reader_says(rel), ([], []), rel)

class CanonicalVectors(unittest.TestCase):
    """Expected bytes are literals. Deriving them from the encoder would compare it to itself."""

    def test_rfc8785_string_example(self):
        # RFC 8785 section 3.2.2: the parsed string and its required serialization.
        # Code points, not escapes: this is the string the RFC's JSON text parses to.
        parsed = "".join(map(chr, (0x20AC, 0x24, 0x0F, 0x0A, 0x41, 0x27, 0x42, 0x22, 0x5C, 0x5C,
                                   0x22, 0x2F)))
        want = b'"\xe2\x82\xac$\\u000f\\nA\'B\\"\\\\\\\\\\"/"'
        self.assertEqual(canonical.encode(parsed), want)

    def test_rfc8785_literals(self):
        self.assertEqual(canonical.encode([None, True, False]), b"[null,true,false]")

    def test_control_characters(self):
        # Two-character escapes for the five named controls, lowercase \u00xx for the rest,
        # and everything from U+0020 up as itself, DEL and the line separators included.
        value = ''.join(map(chr, (0x08, 0x09, 0x0A, 0x0C, 0x0D, 0x00, 0x1F, 0x7F, 0x2028, 0x2029)))
        want = b'"\\b\\t\\n\\f\\r\\u0000\\u001f\x7f\xe2\x80\xa8\xe2\x80\xa9"'
        self.assertEqual(canonical.encode(value), want)

    def test_astral_character_is_utf8_not_a_surrogate_escape(self):
        self.assertEqual(canonical.encode("\U0001f600"), b'"\xf0\x9f\x98\x80"')

    def test_keys_sorted_and_no_whitespace(self):
        value = {"b": [1, {"d": 2, "c": 3}], "a_1": -7, "a": ""}
        self.assertEqual(canonical.encode(value), b'{"a":"","a_1":-7,"b":[1,{"c":3,"d":2}]}')

    def test_integer_bounds(self):
        top = 2**53 - 1
        self.assertEqual(canonical.encode([top, -top, 0]),
                         b"[9007199254740991,-9007199254740991,0]")

    def test_empty_containers(self):
        self.assertEqual(canonical.encode({"a": [], "b": {}}), b'{"a":[],"b":{}}')


class CanonicalRefusals(unittest.TestCase):
    def refused(self, code, call, *args):
        with self.assertRaises(canonical.CanonicalError) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)

    def test_encode_refuses_values_outside_the_domain(self):
        cases = (
            (canonical.UNSUPPORTED_NUMBER, 1.5),
            (canonical.UNSUPPORTED_NUMBER, float("nan")),
            (canonical.UNSUPPORTED_NUMBER, 2**53),
            (canonical.UNSUPPORTED_NUMBER, -(2**53)),
            (canonical.INVALID_UTF8, "\ud800"),
            (canonical.INVALID_KEY, {"camelCase": 1}),
            (canonical.INVALID_KEY, {"café": 1}),
            (canonical.INVALID_KEY, {"trailing_": 1}),
            (canonical.INVALID_KEY, {"a\n": 1}),
            (canonical.INVALID_KEY, {"": 1}),
            (canonical.INVALID_KEY, {1: 1}),
            (canonical.UNSUPPORTED_TYPE, (1, 2)),
            (canonical.UNSUPPORTED_TYPE, b"bytes"),
            (canonical.UNSUPPORTED_TYPE, {"a": {1, 2}}),
        )
        for code, value in cases:
            with self.subTest(value=repr(value)):
                self.refused(code, canonical.encode, value)

    def test_true_is_not_the_integer_one(self):
        self.assertEqual(canonical.encode([True, 1]), b"[true,1]")

    def test_load_refuses_bytes_that_are_not_their_own_canonical_form(self):
        cases = (
            (canonical.NON_CANONICAL_BYTES, b'{"a": 1}'),
            (canonical.NON_CANONICAL_BYTES, b'{"b":1,"a":2}'),
            (canonical.NON_CANONICAL_BYTES, b'"\\u0041"'),
            (canonical.NON_CANONICAL_BYTES, b'"\\/"'),
            (canonical.NON_CANONICAL_BYTES, b"-0"),
            (canonical.NON_CANONICAL_BYTES, b"1\n"),
            (canonical.DUPLICATE_KEY, b'{"a":1,"a":1}'),
            (canonical.DUPLICATE_KEY, b'{"a":{"b":1,"b":2}}'),
            (canonical.UNSUPPORTED_NUMBER, b"1.0"),
            (canonical.UNSUPPORTED_NUMBER, b"1e2"),
            (canonical.UNSUPPORTED_NUMBER, b"1e400"),
            (canonical.INVALID_JSON, b"NaN"),
            (canonical.INVALID_JSON, b"[-Infinity]"),
            (canonical.UNSUPPORTED_NUMBER, b"9007199254740992"),
            (canonical.UNSUPPORTED_NUMBER, b"1" * 5000),
            (canonical.INVALID_KEY, b'{"A":1}'),
            (canonical.INVALID_UTF8, b'"\xff"'),
            (canonical.INVALID_UTF8, b'"\\ud800"'),
            (canonical.INVALID_JSON, b""),
            (canonical.INVALID_JSON, b"{"),
            (canonical.INVALID_JSON, b'\xef\xbb\xbf"a"'),
            (canonical.NESTING_TOO_DEEP, b"[" * 100000 + b"]" * 100000),
        )
        for code, data in cases:
            with self.subTest(data=data[:24]):
                self.refused(code, canonical.load, data)

    def test_a_parser_that_gives_up_on_depth_is_reported_by_name(self):
        # Interpreters differ on whether the parser or the walk after it runs out first.
        with mock.patch.object(canonical.json, "loads", side_effect=RecursionError):
            self.refused(canonical.NESTING_TOO_DEEP, canonical.load, b"[]")

    def test_the_depth_limit_is_a_stated_number(self):
        deepest = b"[" * canonical.MAX_DEPTH + b"]" * canonical.MAX_DEPTH
        self.assertEqual(canonical.encode(canonical.load(deepest)), deepest)
        self.refused(canonical.NESTING_TOO_DEEP, canonical.load, b"[" + deepest + b"]")
        mixed = b'{"a":' * canonical.MAX_DEPTH + b"[]" + b"}" * canonical.MAX_DEPTH
        self.refused(canonical.NESTING_TOO_DEEP, canonical.load, mixed)
        self.assertIn(str(canonical.MAX_DEPTH), canonical.ERRORS[canonical.NESTING_TOO_DEEP])

    def test_encode_refuses_a_value_too_deep_to_walk(self):
        value = []
        for _ in range(100000):
            value = [value]
        self.refused(canonical.NESTING_TOO_DEEP, canonical.encode, value)


class CanonicalDigest(unittest.TestCase):
    def test_stored_bytes_are_the_hash_input(self):
        data = b'{"a":1}'
        self.assertEqual(canonical.digest(data), hashlib.sha256(data).hexdigest())
        self.assertEqual(canonical.digest_of({"a": 1}), canonical.digest(data))

    def test_digest_refuses_non_canonical_bytes_instead_of_hashing_them(self):
        with self.assertRaises(canonical.CanonicalError) as caught:
            canonical.digest(b'{ "a":1}')
        self.assertEqual(caught.exception.code, canonical.NON_CANONICAL_BYTES)

    def test_round_trip(self):
        value = {"kind": "example", "members": [{"path": "a/b", "size": 3}], "ok": True}
        self.assertEqual(canonical.load(canonical.encode(value)), value)



DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
RECORD = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "example",
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "members", "receipt_id"],
    "properties": {
        "kind": {"const": "example"},
        "members": {"type": "array", "minItems": 1, "uniqueItems": True,
                    "items": {"$ref": "#/$defs/member"}},
        "note": {"type": "string", "minLength": 1, "maxLength": 8},
        "receipt_id": {"type": "string", "pattern": "^r-[0-9]+$", "x-runtime-owned": True},
        "state": {"enum": ["active", "locked", 1, True, None]},
        "choice": {"oneOf": [{"type": "integer", "minimum": 0, "maximum": 9},
                             {"type": "string", "maxLength": 3}]},
    },
    "$defs": {
        "member": {"type": "object", "additionalProperties": False, "required": ["path", "sha256"],
                   "properties": {"path": {"type": "string", "minLength": 1}, "sha256": DIGEST,
                                  "children": {"type": "array",
                                               "items": {"$ref": "#/$defs/member"}}}},
    },
}
GOOD = {"kind": "example", "receipt_id": "r-1",
        "members": [{"path": "a", "sha256": "0" * 64,
                     "children": [{"path": "b", "sha256": "1" * 64}]}]}


def codes(found):
    return [(v.code, v.pointer) for v in found]


class SchemaLoad(unittest.TestCase):
    def refused(self, code, document, pointer=None):
        with self.assertRaises(schema.SchemaError) as caught:
            schema.load_schema(document)
        self.assertEqual(caught.exception.code, code)
        if pointer is not None:
            self.assertEqual(caught.exception.pointer, pointer)

    def test_the_example_loads(self):
        schema.load_schema(RECORD)

    def test_a_keyword_outside_the_closed_set_fails_by_name(self):
        for keyword in ("format", "anyOf", "allOf", "not", "if", "patternProperties", "default",
                        "exclusiveMinimum", "multipleOf", "prefixItems", "nullable", "x-other"):
            with self.subTest(keyword=keyword):
                self.refused(schema.UNSUPPORTED_KEYWORD, {"type": "string", keyword: 1},
                             "/" + keyword)
        nested = {"type": "object", "additionalProperties": False,
                  "properties": {"a": {"type": "array",
                                       "items": {"type": "string", "format": "uri"}}}}
        self.refused(schema.UNSUPPORTED_KEYWORD, nested, "/properties/a/items/format")

    def test_an_object_schema_is_closed_in_the_document(self):
        self.refused(schema.OPEN_OBJECT, {"type": "object"}, "")
        self.refused(schema.OPEN_OBJECT, {"type": "object", "additionalProperties": True})
        self.refused(schema.OPEN_OBJECT,
                     {"type": "object", "additionalProperties": {"type": "string"}})

    def test_invalid_schemas(self):
        closed = {"type": "object", "additionalProperties": False}
        cases = (
            [],
            {},
            {"type": "number"},
            {"type": ["string", "null"]},
            {"type": "integer", "minLength": 1},
            {"type": "string", "minLength": -1},
            {"type": "string", "minLength": True},
            {"type": "string", "pattern": 1},
            {"type": "integer", "minimum": "0"},
            {"type": "array"},
            {"type": "array", "items": {"type": "string"}, "uniqueItems": 1},
            {"enum": []},
            {"enum": ["a"], "type": "string"},
            {"const": 1, "type": "integer"},
            {"oneOf": [{"type": "string"}]},
            {"oneOf": [{"type": "string"}, {"type": "null"}], "type": "string"},
            {"$ref": "#/$defs/a", "type": "string", "$defs": {"a": {"type": "string"}}},
            {"type": "string", "x-runtime-owned": False},
            {"type": "string", "title": 1},
            dict(closed, required=["a"]),
            dict(closed, required=["a", "a"], properties={"a": {"type": "string"}}),
            dict(closed, properties={"camelCase": {"type": "string"}}),
            dict(closed, properties={"a": dict(closed, **{"$defs": {}})}),
            {"type": "string", "$defs": {"bad-name": {"type": "string"}}},
            {"type": "string", "$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}},
            {"type": "string",
             "$defs": {"a": {"oneOf": [{"$ref": "#/$defs/a"}, {"type": "null"}]}}},
        )
        for document in cases:
            with self.subTest(document=repr(document)[:70]):
                self.refused(schema.INVALID_SCHEMA, document)

    def test_refs(self):
        self.refused(schema.UNRESOLVED_REF, {"$ref": "#/$defs/missing"}, "/$ref")
        self.refused(schema.UNRESOLVED_REF, {"$ref": "other.json#/$defs/a"})
        self.refused(schema.UNRESOLVED_REF, {"$ref": "#/properties/a"})
        self.refused(schema.UNRESOLVED_REF, {"$ref": 1})

    def test_a_number_that_is_not_an_integer_fails_at_load(self):
        # 1 and 1.0 are one number to JSON Schema and two to the reader's comparison.
        self.refused(schema.INVALID_SCHEMA, {"oneOf": [{"const": 1}, {"const": 1.0}]},
                     "/oneOf/1/const")
        self.refused(schema.INVALID_SCHEMA, {"enum": [1, 2.5]}, "/enum")

    def test_a_lazy_quantifier_and_a_quantified_plus_sign_are_both_dialects(self):
        for pattern in ("^a+?$", "^a{2}?$", "^\\++$", "^[+]+$", "^[a\\-z]$", "^\\]$", "^\\}$"):
            with self.subTest(pattern=pattern):
                schema.load_schema({"type": "string", "pattern": pattern})

    def test_a_runtime_owned_mark_the_reader_would_not_read_fails_at_load(self):
        # Submit mode reads the mark on the root and on a property's own schema only.
        owned = {"type": "string", "x-runtime-owned": True}
        for document, where in (
                ({"type": "object", "additionalProperties": False,
                  "properties": {"stamp": {"$ref": "#/$defs/owned"}}, "$defs": {"owned": owned}},
                 "/$defs/owned/x-runtime-owned"),
                ({"type": "object", "additionalProperties": False,
                  "properties": {"stamp": {"oneOf": [owned, {"type": "integer"}]}}},
                 "/properties/stamp/oneOf/0/x-runtime-owned"),
                ({"type": "array", "items": owned}, "/items/x-runtime-owned")):
            with self.subTest(where=where):
                self.refused(schema.INVALID_SCHEMA, document, where)
        loaded = schema.load_schema({"type": "object", "additionalProperties": False,
                                     "properties": {"stamp": owned}})
        self.assertEqual([(v.code, v.pointer) for v in loaded.validate({"stamp": "x"}, "submit")],
                         [(schema.RUNTIME_OWNED_FIELD, "/stamp")])

    def test_patterns_outside_the_shared_dialect_fail_by_name(self):
        bad = ("[a-z]+", "^[a-z]+", "[a-z]+$", "^a|b$", "^a.b$", "^a\\sb$", "^\\bword$", "^a\\$",
               "^(?=a)a$", "^(?P<n>a)$", "^(a)\\1$", "^[[:alpha:]]$", "^[]a]$", "^[^]a]$", "^a^b$",
               "^a$b$", "^(a$", "^a)$", "^[a$", "^caf" + chr(0xE9) + "$", "^a\\", "^*$", "",
               "^a{,2}$", "^x{y}$", "^a{}$", "^a++$", "^a*+$", "^a?+$", "^a{1,2}+$",
               "^a}$", "^a]$", "^\\-$")
        for pattern in bad:
            with self.subTest(pattern=pattern):
                self.refused(schema.UNSUPPORTED_PATTERN, {"type": "string", "pattern": pattern},
                             "/pattern")
        good = ("^[0-9a-f]{64}$", "^(?:a|b)+$", "^(a|b)c$", "^\\d{4}-\\d{2}$", "^\\w+\\.json$",
                "^a\\\\$", "^[^/]+(?:/[^/]+)*$", "^$", "^a\\|b$", "^[.$^|]$", "^a{2,}$",
                "^a{1,3}$", "^a\\{,2\\}$")
        for pattern in good:
            with self.subTest(pattern=pattern):
                schema.load_schema({"type": "string", "pattern": pattern})


class SchemaValidate(unittest.TestCase):
    def setUp(self):
        self.schema = schema.load_schema(RECORD)

    def test_the_good_record_is_clean_when_stored(self):
        self.assertEqual(self.schema.validate(GOOD), [])

    def test_violations_carry_code_and_pointer(self):
        def changed(**fields):
            return {**GOOD, **fields}
        member = GOOD["members"][0]
        cases = (
            (changed(kind="other"), [(schema.VALUE_NOT_ALLOWED, "/kind")]),
            (changed(kind=1), [(schema.VALUE_NOT_ALLOWED, "/kind")]),
            (changed(extra=1), [(schema.UNKNOWN_FIELD, "/extra")]),
            ({k: v for k, v in GOOD.items() if k != "members"},
             [(schema.MISSING_FIELD, "/members")]),
            (changed(members=[]), [(schema.COUNT_OUT_OF_RANGE, "/members")]),
            (changed(members="a"), [(schema.TYPE_MISMATCH, "/members")]),
            (changed(members=[member, dict(member)]), [(schema.DUPLICATE_ITEM, "/members/1")]),
            (changed(members=[dict(member, sha256="0" * 63)]),
             [(schema.PATTERN_MISMATCH, "/members/0/sha256")]),
            (changed(members=[dict(member, sha256="0" * 64 + "\n")]),
             [(schema.PATTERN_MISMATCH, "/members/0/sha256")]),
            (changed(members=[dict(member, children=[{"path": "", "sha256": "2" * 64}])]),
             [(schema.LENGTH_OUT_OF_RANGE, "/members/0/children/0/path")]),
            (changed(note=""), [(schema.LENGTH_OUT_OF_RANGE, "/note")]),
            (changed(note="123456789"), [(schema.LENGTH_OUT_OF_RANGE, "/note")]),
            (changed(state="signed_out"), [(schema.VALUE_NOT_ALLOWED, "/state")]),
            (changed(state=False), [(schema.VALUE_NOT_ALLOWED, "/state")]),
            (changed(state=0), [(schema.VALUE_NOT_ALLOWED, "/state")]),
            (changed(choice=10), [(schema.VARIANT_MISMATCH, "/choice")]),
            (changed(choice=True), [(schema.VARIANT_MISMATCH, "/choice")]),
            (changed(choice=None), [(schema.VARIANT_MISMATCH, "/choice")]),
        )
        for record, want in cases:
            with self.subTest(want=want):
                self.assertEqual(codes(self.schema.validate(record)), want)
        for ok in (changed(state=1), changed(state=True), changed(state=None), changed(choice=9),
                   changed(choice="abc"), changed(note="12345678")):
            self.assertEqual(self.schema.validate(ok), [])

    def test_one_of_needs_exactly_one_variant(self):
        both = schema.load_schema({"oneOf": [{"type": "integer"},
                                             {"type": "integer", "minimum": 0}]})
        self.assertEqual(codes(both.validate(5)), [(schema.VARIANT_MISMATCH, "")])
        self.assertEqual(both.validate(-5), [])

    def test_digit_and_word_classes_are_ascii(self):
        # ECMAScript reads \d and \w as ASCII without the u flag; Python does only under re.ASCII.
        digits = schema.load_schema({"type": "string", "pattern": "^\\d+$"})
        self.assertEqual(digits.validate("2026"), [])
        self.assertEqual(codes(digits.validate(chr(0x0661))), [(schema.PATTERN_MISMATCH, "")])
        words = schema.load_schema({"type": "string", "pattern": "^\\w+$"})
        self.assertEqual(words.validate("cafe_1"), [])
        self.assertEqual(codes(words.validate("caf" + chr(0xE9))),
                         [(schema.PATTERN_MISMATCH, "")])

    def test_a_boolean_never_equals_an_integer(self):
        one = schema.load_schema({"enum": [1, [0]]})
        self.assertEqual(one.validate(1), [])
        self.assertEqual(one.validate([0]), [])
        self.assertEqual(codes(one.validate(True)), [(schema.VALUE_NOT_ALLOWED, "")])
        self.assertEqual(codes(one.validate([False])), [(schema.VALUE_NOT_ALLOWED, "")])
        yes = schema.load_schema({"const": {"on": True}})
        self.assertEqual(yes.validate({"on": True}), [])
        self.assertEqual(codes(yes.validate({"on": 1})), [(schema.VALUE_NOT_ALLOWED, "")])
        distinct = schema.load_schema({"type": "array", "uniqueItems": True,
                                       "items": {"enum": [0, 1, True, False]}})
        self.assertEqual(distinct.validate([0, False, 1, True]), [])
        self.assertEqual(codes(distinct.validate([1, True, 1])),
                         [(schema.DUPLICATE_ITEM, "/2")])

    def test_true_is_not_an_integer(self):
        integer = schema.load_schema({"type": "integer"})
        self.assertEqual(codes(integer.validate(True)), [(schema.TYPE_MISMATCH, "")])
        self.assertEqual(integer.validate(1), [])
        boolean = schema.load_schema({"type": "boolean"})
        self.assertEqual(codes(boolean.validate(1)), [(schema.TYPE_MISMATCH, "")])

    def test_submit_mode_refuses_a_runtime_owned_field_and_does_not_require_it(self):
        submitted = {k: v for k, v in GOOD.items() if k != "receipt_id"}
        self.assertEqual(self.schema.validate(submitted, schema.SUBMIT), [])
        self.assertEqual(codes(self.schema.validate(GOOD, schema.SUBMIT)),
                         [(schema.RUNTIME_OWNED_FIELD, "/receipt_id")])
        # and the stored direction still requires it
        self.assertEqual(codes(self.schema.validate(submitted)),
                         [(schema.MISSING_FIELD, "/receipt_id")])
        with self.assertRaises(ValueError):
            self.schema.validate(GOOD, "other")

    def test_pointer_tokens_are_escaped(self):
        self.assertEqual(schema._escape("a/b~c"), "a~1b~0c")


class ErrorTable(unittest.TestCase):
    def test_the_stored_table_is_what_the_modules_emit(self):
        self.assertEqual(errors.TABLE_PATH.read_bytes(), errors.emit())
        stored = canonical.load(errors.TABLE_PATH.read_bytes())
        self.assertEqual([row["code"] for row in stored["errors"]], sorted(errors.table()))

    def test_every_code_has_one_owner_and_a_meaning(self):
        joined = errors.table()
        self.assertEqual(errors.OWNERS[:3], (canonical, schema, records))
        self.assertEqual(set(joined), {code for module in errors.OWNERS for code in module.ERRORS})
        self.assertEqual(len(joined), sum(len(module.ERRORS) for module in errors.OWNERS))
        for code, entry in joined.items():
            with self.subTest(code=code):
                self.assertRegex(code, r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
                self.assertTrue(entry["meaning"].strip())

    def test_a_contract_module_names_its_contract_and_its_record_kinds(self):
        described: dict[str, set[str]] = {}
        for kind, versions in records.registry(examples.load_schemas()).items():
            for identifier in versions.values():
                contract, _, rest = identifier.partition("_")
                self.assertEqual(rest, kind, f"schema {identifier} describes kind {kind}")
                described.setdefault(contract, set()).add(kind)
        modules = [m for m in errors.OWNERS if getattr(m, "IN_RESULTS", False)]
        names = [m.__name__.rsplit(".", 1)[-1] for m in modules]
        # Derived, not listed: the contract modules are exactly the contracts the schema
        # documents name, so a module without schemas and a schema without a module both fail.
        self.assertEqual(names, sorted(names))
        self.assertEqual(set(names), set(described))
        self.assertTrue(all(re.fullmatch(r"[bc][0-9]{2}", name) for name in names), names)
        for module, name in zip(modules, names, strict=True):
            with self.subTest(module=name):
                self.assertEqual(module.CONTRACT, name.upper())
                self.assertEqual(len(module.RECORD_KINDS), len(set(module.RECORD_KINDS)))
                self.assertEqual(set(module.RECORD_KINDS), described[name])

    def test_a_code_two_modules_claim_is_refused(self):
        taken = next(iter(canonical.ERRORS))
        schema.ERRORS[taken] = "claimed twice"
        try:
            with self.assertRaisesRegex(ValueError, taken):
                errors.table()
        finally:
            del schema.ERRORS[taken]
        errors.table()

    def test_an_error_outside_its_module_rows_cannot_be_raised(self):
        with self.assertRaises(LookupError):
            canonical.CanonicalError("not_in_the_table", "x")
        with self.assertRaises(LookupError):
            schema.SchemaError("not_in_the_table", "", "x")
        with self.assertRaises(LookupError):
            schema.Violation("not_in_the_table", "", "x")

    def test_coverage_is_checked_both_ways(self):
        results = errors.in_results()
        self.assertEqual(results, {code for module in (b01, b02, b03, b04, b05, c01, c02,
                                                  c03, c04, c05, c06, c07, c08, c09, c10,
                                                  c11, c12)
                                   for code in module.ERRORS})
        readers = set(errors.table()) - results - set(errors.not_from_bytes())
        self.assertEqual(errors.coverage(readers, results), [])
        missing = errors.coverage(readers - {canonical.DUPLICATE_KEY}, results)
        self.assertEqual(len(missing), 1)
        self.assertIn(canonical.DUPLICATE_KEY, missing[0])
        self.assertIn("no negative example", missing[0])
        unknown = errors.coverage(readers | {"not_in_the_table"}, results)
        self.assertEqual(len(unknown), 1)
        self.assertIn("not_in_the_table", unknown[0])

    def test_a_gap_code_is_stated_by_a_result_and_never_asked_of_the_reader(self):
        results = errors.in_results()
        readers = set(errors.table()) - results - set(errors.not_from_bytes())
        self.assertEqual(errors.coverage(readers, results - {c03.STALE_BASE}),
                         ["gap code 'stale_base' is stated by no accepted result example"])
        self.assertEqual(errors.coverage(readers | {c03.STALE_BASE}, results),
                         ["an expectation asks the reader for 'stale_base', which only a result "
                          "states"])
        self.assertEqual(errors.coverage(readers, results | {"not_in_the_table"}),
                         ["an example states gap code 'not_in_the_table', which the table does "
                          "not hold"])
        # A result may repeat a reader's code, for a submission it refused. That shows nothing
        # about the reader, so the reader's code still needs its own refused example.
        self.assertEqual(errors.coverage(readers - {schema.MISSING_FIELD},
                                         results | {schema.MISSING_FIELD}),
                         ["error code 'missing_field' is exercised by no negative example"])


class PlantedCopies(unittest.TestCase):
    """A copy of the schemas and examples per case, with one thing planted, so no case depends
    on what another left behind."""

    def planted(self, plant):
        with tempfile.TemporaryDirectory(prefix="workenv-examples-") as scratch:
            root = pathlib.Path(scratch)
            shutil.copytree(examples.SCHEMAS, root / "schemas")
            shutil.copytree(examples.EXAMPLES, root / "examples")
            plant(root)
            return examples.check(root / "schemas", root / "examples")[0]

    def one_problem(self, plant, fragment):
        problems = self.planted(plant)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(fragment, problems[0])


class ContractExamples(PlantedCopies):
    """The real examples pass; each rule of the checker fails by name on a planted copy."""

    def test_the_real_examples_pass_and_the_copy_is_faithful(self):
        self.assertEqual(examples.check()[0], [])
        self.assertEqual(self.planted(lambda root: None), [])

    def test_the_stored_index_is_what_is_on_disk(self):
        self.assertEqual(examples.INDEX.read_bytes(), examples.index())

    def test_the_generated_files_satisfy_the_schemas_written_about_them(self):
        schemas = examples.load_schemas()
        index = canonical.load(examples.INDEX.read_bytes())
        self.assertEqual(schemas["fixture_index"].validate(index), [])
        table = canonical.load(errors.TABLE_PATH.read_bytes())
        self.assertEqual(schemas["error_table"].validate(table), [])

    def test_an_example_without_an_expectation(self):
        self.one_problem(lambda root: (root / "examples/encoding/float.expect.json").unlink(),
                         "encoding/float.json has no expectation beside it")

    def test_an_expectation_without_its_example(self):
        self.one_problem(lambda root: (root / "examples/encoding/float.json").unlink(),
                         "encoding/float.expect.json expects something of an example that is "
                         "absent")

    def test_an_empty_example_set(self):
        def plant(root):
            shutil.rmtree(root / "examples")
            (root / "examples").mkdir()
        problems = self.planted(plant)
        self.assertIn("empty subject set: no example with an expectation", problems)

    def test_an_example_that_does_not_do_what_its_expectation_says(self):
        def plant(root):
            (root / "examples/encoding/float.json").write_bytes(b'{"size":1}')
        self.one_problem(plant, "encoding/float.json: expected [{'code': 'unsupported_number'")

    def test_a_refusal_at_another_pointer_is_a_mismatch(self):
        def plant(root):
            path = root / "examples/fixture_index/negative_size.expect.json"
            path.write_bytes(path.read_bytes().replace(b"/files/0/size", b"/files/0/path"))
        self.one_problem(plant, "fixture_index/negative_size.json: expected")

    def test_a_code_only_one_example_exercised(self):
        def plant(root):
            for name in ("nested_65_deep.json", "nested_65_deep.expect.json"):
                (root / "examples/encoding" / name).unlink()
        self.one_problem(plant, "'nesting_too_deep' is exercised by no negative example")

    def test_an_expectation_naming_a_code_outside_the_table(self):
        def plant(root):
            path = root / "examples/encoding/float.expect.json"
            path.write_bytes(path.read_bytes().replace(b"unsupported_number",
                                                       b"unsupported_digits"))
        problems = self.planted(plant)
        self.assertTrue(any("'unsupported_digits', which the table does not hold" in p
                            for p in problems), problems)

    def test_a_malformed_expectation(self):
        def plant(root):
            (root / "examples/encoding/float.expect.json").write_bytes(
                b'{"subject":"bytes","why":1}')
        problems = self.planted(plant)
        self.assertTrue(any("encoding/float.json: its expectation is malformed" in p
                            for p in problems), problems)

    def test_an_expectation_that_is_not_canonical(self):
        def plant(root):
            (root / "examples/encoding/float.expect.json").write_bytes(b'{"subject": "bytes"}')
        problems = self.planted(plant)
        self.assertTrue(any("its expectation is not a canonical record" in p for p in problems),
                        problems)

    def test_a_schema_with_no_accepted_or_no_refused_example(self):
        def no_accepted(root):
            for name in ("one_row.json", "one_row.expect.json"):
                (root / "examples/error_table" / name).unlink()
        self.one_problem(no_accepted, "schema error_table: no example it accepts")

        def unexercised(root):
            shutil.copy(root / "schemas/error_table.schema.json",
                        root / "schemas/second_table.schema.json")
        problems = self.planted(unexercised)
        self.assertEqual(problems, ["schema second_table: no example it accepts",
                                    "schema second_table: no example it refuses"])

    def test_an_expectation_naming_an_absent_schema(self):
        def plant(root):
            path = root / "examples/error_table/empty_meaning.expect.json"
            path.write_bytes(path.read_bytes().replace(b'"error_table"', b'"absent_table"'))
        problems = self.planted(plant)
        self.assertTrue(any("expects schema 'absent_table', which is absent" in p
                            for p in problems), problems)

    def test_a_schema_that_does_not_load(self):
        def plant(root):
            (root / "schemas/broken.schema.json").write_bytes(b'{"type":"object"}')
        self.one_problem(plant, "a contract schema does not load: open_object")

    def test_without_the_expectation_schema_nothing_is_read(self):
        self.one_problem(lambda root: (root / "schemas/expectation.schema.json").unlink(),
                         "schemas/expectation.schema.json is absent")

    def test_a_code_declared_unreachable_from_bytes(self):
        results = errors.in_results()
        every = set(errors.table()) - results
        exempt = set(errors.not_from_bytes())
        self.assertEqual(exempt, {canonical.UNSUPPORTED_TYPE})
        self.assertEqual(errors.coverage(every - exempt, results), [])
        stale = errors.coverage(every, results)
        self.assertEqual(len(stale), 1)
        self.assertIn("the declaration is stale", stale[0])
        with mock.patch.dict(canonical.NOT_FROM_BYTES, {"not_in_the_table": "x"}):
            dangling = errors.coverage(every - exempt, results)
        self.assertEqual(len(dangling), 1)
        self.assertIn("is not in the table", dangling[0])


class ContractRecordExamples(PlantedCopies):
    """The rules that hold contract records together, each planted on its own copy."""

    @staticmethod
    def remove(name):
        def plant(root):
            (root / "examples" / f"{name}.json").unlink()
            (root / "examples" / f"{name}.expect.json").unlink()
        return plant

    def rewrite(self, relative, old, new):
        def plant(root):
            path = root / relative
            data = path.read_bytes()
            self.assertEqual(data.count(old), 1, f"{old!r} in {relative}")
            path.write_bytes(data.replace(old, new))
        return plant

    def test_a_dispatched_example_is_read_by_its_own_kind(self):
        self.one_problem(self.rewrite("examples/dispatch/known_kind_and_version.json",
                                      b'"operation_query"', b'"operation_wish"'),
                         "dispatch/known_kind_and_version.json: expected acceptance, got "
                         "[{'code': 'unknown_record_kind', 'pointer': '/kind'}]")

    def test_a_place_the_runtime_writes_with_no_refused_submission(self):
        self.one_problem(self.remove("c01/submission_dates_itself"),
                         "schema c01_principal_binding: the runtime writes /created_at and no "
                         "submission is refused for carrying it")
        self.one_problem(self.remove("fixture_index/authored_entry_declares_its_size"),
                         "schema fixture_index: the runtime writes /files/size and no")
        self.one_problem(self.remove("c03/receipt_is_never_submitted"),
                         "schema c03_operation_receipt: the runtime writes the whole record and")

    def test_a_refusal_when_stored_is_not_a_refused_submission(self):
        # Stored, the same receipt is accepted, so the expectation is wrong as well.
        problems = self.planted(self.rewrite(
            "examples/c03/receipt_is_never_submitted.expect.json", b'"submit"', b'"stored"'))
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("c03_operation_receipt: the runtime writes the whole record", problems[1])

    def test_another_refusal_at_the_same_place_is_not_a_refused_submission(self):
        def plant(root):
            self.remove("c01/submission_dates_itself")(root)
            stored = (root / "examples/c01/device_key_binding.json").read_bytes()
            self.assertEqual(stored.count(b'"created_at":"2026-09-20T09:00:00Z"'), 1)
            (root / "examples/c01/dated_in_words.json").write_bytes(
                stored.replace(b'"created_at":"2026-09-20T09:00:00Z"', b'"created_at":"today"'))
            (root / "examples/c01/dated_in_words.expect.json").write_bytes(canonical.encode({
                "subject": "dispatched", "mode": "stored",
                "refusals": [{"code": "pattern_mismatch", "pointer": "/created_at"}]}))
        self.one_problem(plant, "c01_principal_binding: the runtime writes /created_at and no")

    def test_the_places_a_schema_marks(self):
        schemas = examples.load_schemas()
        self.assertEqual(examples.owned_places(schemas["fixture_index"]),
                         {"/files/digest", "/files/size"})
        self.assertEqual(examples.owned_places(schemas["c01_repository_binding"]), {"/observed"})
        self.assertEqual(examples.owned_places(schemas["c03_operation_result"]), {""})
        # The digest of a sealed request is its identity, so the runtime adds nothing to it.
        self.assertEqual(examples.owned_places(schemas["c03_operation_request"]), set())
        closed = {"type": "object", "additionalProperties": False}
        recursive = schema.load_schema({
            "$ref": "#/$defs/node",
            "$defs": {"node": {**closed, "properties": {
                "stamp": {"type": "string", "x-runtime-owned": True},
                # A submission is refused at the marked property and never read below it.
                "sealed": {**closed, "x-runtime-owned": True, "properties": {
                    "inner": {"type": "string", "x-runtime-owned": True}}},
                "either": {"oneOf": [{"type": "null"}, {**closed, "properties": {
                    "seen": {"type": "string", "x-runtime-owned": True}}}]},
                "children": {"type": "array", "items": {"$ref": "#/$defs/node"}}}}}})
        self.assertEqual(examples.owned_places(recursive),
                         {"/stamp", "/sealed", "/either/seen"})
        self.assertEqual(examples.without_indices("/files/12/sha256"), "/files/sha256")

    def test_a_definition_name_with_two_meanings(self):
        # The document named first is whichever defines `digest` earliest in sorted order, so
        # derive it rather than naming one that a later contract can displace.
        schemas = examples.load_schemas()
        first = min(i for i, loaded in schemas.items() if "digest" in loaded.defs)
        self.assertNotEqual(first, "c01_source_ref")
        self.one_problem(self.rewrite("schemas/c01_source_ref.schema.json",
                                      b'\n    "digest": {\n',
                                      b'\n    "digest": {\n      "title": "another digest",\n'),
                         f"$defs/digest differs between schemas {first} and "
                         "c01_source_ref; one name has one meaning")

    def test_two_documents_describing_one_record_kind(self):
        def plant(root):
            shutil.copy(root / "schemas/c03_operation_query.schema.json",
                        root / "schemas/c03_operation_query_again.schema.json")
        self.one_problem(plant, "record kind 'operation_query' version 1 is described by "
                                "c03_operation_query and c03_operation_query_again")

    def test_a_result_answers_a_request_example_that_exists(self):
        request = (examples.EXAMPLES / "c03/commit_request.json").read_bytes()
        digest = hashlib.sha256(request).hexdigest().encode()
        stale = (examples.EXAMPLES / "c03/stale_base.json").read_bytes()
        self.assertIn(b'"request_digest":"' + digest + b'"', stale)
        self.one_problem(self.rewrite("examples/c03/stale_base.json", digest, b"0" * 64),
                         "c03/stale_base.json: answers request req_")
        # The digest of another request example is not enough; the id has to be that one's.
        other = (examples.EXAMPLES / "c03/preview_request.json").read_bytes()
        self.one_problem(self.rewrite("examples/c03/stale_base.json", digest,
                                      hashlib.sha256(other).hexdigest().encode()),
                         "and no request example has both")

    def test_a_refused_request_is_not_one_a_result_can_answer(self):
        # commit_without_a_base shares its request id with commit_request and is refused, so a
        # result quoting its digest answers no request example.
        refused = (examples.EXAMPLES / "c03/commit_without_a_base.json").read_bytes()
        accepted = (examples.EXAMPLES / "c03/commit_request.json").read_bytes()
        self.assertEqual(canonical.load(refused)["request_id"],
                         canonical.load(accepted)["request_id"])
        self.one_problem(self.rewrite("examples/c03/stale_base.json",
                                      hashlib.sha256(accepted).hexdigest().encode(),
                                      hashlib.sha256(refused).hexdigest().encode()),
                         "and no request example has both")

    def test_a_gap_code_no_result_states(self):
        self.one_problem(self.remove("c03/stale_base"),
                         "gap code 'stale_base' is stated by no accepted result example")

    def test_a_gap_stated_by_a_refused_example_does_not_count(self):
        def plant(root):
            path = root / "examples/c03/stale_base.json"
            path.write_bytes(path.read_bytes().replace(b'"stage":"stale"', b'"stage":"stalled"'))
            (root / "examples/c03/stale_base.expect.json").write_bytes(canonical.encode({
                "subject": "dispatched", "mode": "stored",
                "refusals": [{"code": "variant_mismatch", "pointer": "/outcome"}]}))
        self.one_problem(plant, "gap code 'stale_base' is stated by no accepted result example")

    def test_a_stated_code_outside_the_table(self):
        problems = self.planted(self.rewrite("examples/c03/stale_base.json",
                                             b'"code":"stale_base"', b'"code":"stale_bass"'))
        self.assertIn("an example states gap code 'stale_bass', which the table does not hold",
                      problems)


class Records(unittest.TestCase):
    def setUp(self):
        self.schemas = examples.load_schemas()
        self.kinds = records.registry(self.schemas)

    def refused(self, code, pointer, value):
        with self.assertRaises(records.RecordError) as caught:
            records.resolve(value, self.kinds)
        self.assertEqual((caught.exception.code, caught.exception.pointer), (code, pointer))

    def test_the_registry_is_read_from_the_documents(self):
        self.assertEqual(self.kinds["operation_query"], {1: "c03_operation_query"})
        describing = {i for versions in self.kinds.values() for i in versions.values()}
        # Derived rather than counted: every contract document describes one kind, and the
        # documents that belong to no contract - the expectation, the index, the table -
        # describe none, so neither set can drift without the other.
        self.assertEqual(describing,
                         {i for i in self.schemas if re.fullmatch(r"[bc][0-9]{2}_.+", i)})
        self.assertEqual(len(describing), len(self.kinds))
        self.assertTrue(self.kinds)

    def test_a_document_describes_a_kind_only_when_it_fixes_and_requires_both(self):
        closed = {"type": "object", "additionalProperties": False}
        fixed = {"kind": {"const": "note"}, "schema": {"const": 1}}
        good = schema.load_schema({**closed, "required": ["kind", "schema"], "properties": fixed})
        self.assertEqual(records.describes(good), ("note", 1))
        for label, document in (
            ("kind not required", {**closed, "required": ["schema"], "properties": fixed}),
            ("version not an integer", {**closed, "required": ["kind", "schema"], "properties": {
                **fixed, "schema": {"const": "1"}}}),
            ("version is a boolean", {**closed, "required": ["kind", "schema"], "properties": {
                **fixed, "schema": {"const": True}}}),
            ("kind is open", {**closed, "required": ["kind", "schema"], "properties": {
                **fixed, "kind": {"type": "string"}}}),
            ("not an object", {"type": "string"}),
        ):
            with self.subTest(label):
                self.assertIsNone(records.describes(schema.load_schema(document)))

    def test_what_is_not_a_record_is_refused_by_name(self):
        good = {"kind": "operation_query", "schema": 1}
        self.assertEqual(records.resolve(good, self.kinds), "c03_operation_query")
        self.refused(records.NOT_A_RECORD, "", [good])
        self.refused(records.NOT_A_RECORD, "/kind", {"schema": 1})
        self.refused(records.NOT_A_RECORD, "/kind", {**good, "kind": 3})
        self.refused(records.NOT_A_RECORD, "/schema", {"kind": "operation_query"})
        self.refused(records.NOT_A_RECORD, "/schema", {**good, "schema": True})
        self.refused(records.UNKNOWN_RECORD_KIND, "/kind", {**good, "kind": "operation_wish"})
        self.refused(records.UNSUPPORTED_SCHEMA_VERSION, "/schema", {**good, "schema": 2})

    def test_load_goes_from_bytes_to_the_kinds_own_schema(self):
        data = (examples.EXAMPLES / "c03/commit_receipt.json").read_bytes()
        value, identifier, found = records.load(data, self.schemas)
        self.assertEqual((value["kind"], identifier, found), ("operation_receipt",
                                                              "c03_operation_receipt", []))
        found = records.load(data, self.schemas, schema.SUBMIT)[2]
        self.assertEqual([(v.code, v.pointer) for v in found], [("runtime_owned_field", "")])
        with self.assertRaises(canonical.CanonicalError):
            records.load(data + b"\n", self.schemas)

    def test_a_record_error_outside_the_module_rows_cannot_be_raised(self):
        with self.assertRaises(LookupError):
            records.RecordError("not_in_the_table", "", "x")

    def test_stated_gaps_are_collected_at_any_depth_and_nothing_else_is(self):
        value = {"code": "not_a_gap", "material_gaps": [{"code": "stale_base"}],
                 "outcome": {"material_gaps": [{"code": "access_locked", "pointer": "/x"}, 7,
                                               {"code": 9}]},
                 "list": [{"material_gaps": [{"code": "ref_unavailable"}]}],
                 "gaps": [{"code": "not_collected"}]}
        self.assertEqual(records.stated(value), {"stale_base", "access_locked", "ref_unavailable"})
class SourceRoleExamples(NamedExamples, unittest.TestCase):
    """The nine role examples, and the rule that a role cannot be promoted by relabelling the
    record that carries it. Families are the three named in the unit; every other subject here
    is derived, because a count written down is a count that stops matching quietly."""

    FAMILIES = ("capture", "provenance", "request")

    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()
        cls.registry = records.registry(cls.schemas)
        cls.group = examples.EXAMPLES / "sources"

    def family(self, kind):
        named = [family for family in self.FAMILIES if kind.endswith(family)]
        return named[0] if named else None

    def read(self):
        """(name, value, expectation) for every example in the sources group."""
        paths = [p for p in sorted(self.group.glob("*.json"))
                 if not p.name.endswith(examples.EXPECT_SUFFIX)]
        self.assertTrue(paths, self.group)
        for path in paths:
            yield (path.stem, canonical.load(path.read_bytes()),
                   canonical.load(examples.expectation_path(path).read_bytes()))

    def test_each_family_is_carried_by_a_record_kind_of_its_own(self):
        carried = {kind: self.family(kind) for kind in c01.RECORD_KINDS
                   if self.family(kind) is not None}
        self.assertEqual(set(carried.values()), set(self.FAMILIES), carried)
        for kind in carried:
            self.assertIn(kind, self.registry, f"{kind} is described by no schema document")

    def test_three_roles_and_three_families_make_nine_accepted_examples(self):
        roles = self.schemas["c01_source_ref"].defs["role"]["enum"]
        self.assertTrue(roles)
        grid = {}
        for name, value, expectation in self.read():
            family = self.family(value.get("kind", ""))
            if family is None or expectation.get("refusals") or expectation["mode"] != "stored":
                continue
            grid.setdefault((family, value["role"]), []).append(name)
        self.assertEqual(set(grid), {(family, role)
                                     for family in self.FAMILIES for role in roles})
        self.assertEqual(sorted(map(len, grid.values())), [1] * (len(self.FAMILIES) * len(roles)))

    def test_every_kind_in_the_grid_has_a_refused_example_too(self):
        refused = {value.get("kind") for _, value, expectation in self.read()
                   if expectation.get("refusals")}
        wanted = {kind for kind in c01.RECORD_KINDS if self.family(kind) is not None}
        self.assertEqual(wanted - refused, set())

    def test_a_capture_of_another_role_cannot_carry_a_behavioural_unit(self):
        captures = {kind for kind in c01.RECORD_KINDS if self.family(kind) == "capture"}
        self.assertTrue(captures)
        carrying = {kind for kind in captures
                    if "units" in self.schemas[self.registry[kind][1]].document["properties"]}
        self.assertEqual(len(carrying), 1, carrying)
        refusing = {value["kind"] for _, value, expectation in self.read()
                    if any(refusal["pointer"] == "/units"
                           for refusal in expectation.get("refusals", []))}
        self.assertEqual(refusing, captures - carrying)

    def test_a_behaviour_capture_cannot_be_relabelled_another_role(self):
        # The capture that may carry units carries them only under its own role.
        self.assertRefused("/role", "sources/behavioural_units_relabelled_as_knowledge")


class Inventory(unittest.TestCase):
    """The emitter builds its own input: a fixture committed beside it could not be planted
    into without changing what the other tests read."""

    INSTANT = "2026-09-20T09:00:00Z"
    SOURCE = "src_" + "0" * 32

    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="workenv-inventory-")
        self.addCleanup(scratch.cleanup)
        self.package = pathlib.Path(scratch.name) / "package"
        (self.package / "tables").mkdir(parents=True)
        (self.package / "concepts.md").write_bytes(b"a concept\n")
        (self.package / "tables" / "rates.csv").write_bytes(b"year,rate\n2026,0.1\n")
        self.stated = inventory.manifest(self.package, self.SOURCE, self.INSTANT)

    def test_what_it_emits_is_a_record_the_committed_schema_accepts(self):
        schemas = examples.load_schemas()
        identifier = records.registry(schemas)[inventory.KIND][inventory.SCHEMA]
        self.assertEqual(schemas[identifier].validate(self.stated), [])
        self.assertEqual([member["path"] for member in self.stated["members"]],
                         ["concepts.md", "tables/rates.csv"])

    def test_two_runs_over_one_directory_give_one_digest(self):
        first = inventory.emit(self.package, self.SOURCE, self.INSTANT)
        self.assertEqual(first, inventory.emit(self.package, self.SOURCE, self.INSTANT))
        (self.package / "concepts.md").write_bytes(b"another concept\n")
        self.assertNotEqual(first, inventory.emit(self.package, self.SOURCE, self.INSTANT))

    def test_a_member_the_inventory_does_not_list(self):
        (self.package / "tables" / "relief.csv").write_bytes(b"case,relief\n")
        self.assertEqual(inventory.differences(self.stated, self.package),
                         [(c01.MANIFEST_MEMBER_UNLISTED, "tables/relief.csv")])

    def test_a_listed_member_this_installation_does_not_hold(self):
        (self.package / "concepts.md").unlink()
        self.assertEqual(inventory.differences(self.stated, self.package),
                         [(c01.REF_UNAVAILABLE, "concepts.md")])

    def test_a_listed_member_whose_bytes_differ(self):
        # Same length as the original, so only the digest comparison can see the change.
        (self.package / "concepts.md").write_bytes(b"b concept\n")
        self.assertEqual(inventory.differences(self.stated, self.package),
                         [(c01.ID_BOUND_TO_OTHER_BYTES, "concepts.md")])

    def test_the_manifest_in_its_own_directory_is_not_a_member_of_itself(self):
        (self.package / inventory.MANIFEST_NAME).write_bytes(canonical.encode(self.stated))
        self.assertEqual(inventory.differences(self.stated, self.package), [])
        nested = self.package / "tables" / inventory.MANIFEST_NAME
        nested.write_bytes(b"a member that happens to share the name\n")
        self.assertEqual(inventory.differences(self.stated, self.package),
                         [(c01.MANIFEST_MEMBER_UNLISTED, "tables/manifest.json")])

    def test_a_revision_cannot_hold_something_else_where_its_manifest_goes(self):
        (self.package / inventory.MANIFEST_NAME).mkdir()
        (self.package / inventory.MANIFEST_NAME / "body.md").write_bytes(b"x")
        with self.assertRaises(inventory.InventoryError):
            inventory.files(self.package)

    def test_the_emitter_refuses_what_the_manifest_schema_refuses(self):
        (self.package / "notes 1.md").write_bytes(b"x")
        with self.assertRaises(inventory.InventoryError) as raised:
            inventory.emit(self.package, self.SOURCE, self.INSTANT)
        self.assertIn("/members/", str(raised.exception))

    def test_what_the_command_prints_is_the_manifest_bytes_and_nothing_else(self):
        out = io.TextIOWrapper(io.BytesIO())
        with contextlib.redirect_stdout(out):
            self.assertEqual(inventory.main([str(self.package), "--source", self.SOURCE,
                                             "--at", self.INSTANT]), 0)
        out.flush()
        self.assertEqual(out.buffer.getvalue(), canonical.encode(self.stated))

    def test_a_path_that_is_not_a_directory_is_refused_not_read_as_empty(self):
        with self.assertRaises(inventory.InventoryError):
            inventory.files(self.package / "absent")

    def test_a_comparison_refuses_a_manifest_its_schema_refuses(self):
        for rel in ("sources/revision_with_no_members",
                    "sources/one_path_listed_twice_with_two_digests"):
            with self.subTest(rel=rel), contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertEqual(inventory.main([str(self.package), "--against",
                                                 str(examples.EXAMPLES / f"{rel}.json")]), 1)
            self.assertIn("FAIL: manifest /members", said.getvalue())

    def test_one_path_listed_twice(self):
        first = self.stated["members"][0]
        twice = {**self.stated, "members": [first, {**first, "digest": "0" * 64},
                                            self.stated["members"][1]]}
        self.assertEqual(inventory.differences(twice, self.package),
                         [(c01.ID_BOUND_TO_OTHER_BYTES, first["path"])])

    def test_a_symbolic_link_is_not_inventoried(self):
        # The link points at a real file outside the package, which is the hazard: following it
        # would bind bytes this revision does not hold.
        elsewhere = self.package.parent / "elsewhere.md"
        elsewhere.write_bytes(b"somebody else's bytes\n")
        (self.package / "outside.md").symlink_to(elsewhere)
        with self.assertRaises(inventory.InventoryError) as raised:
            inventory.manifest(self.package, self.SOURCE, self.INSTANT)
        self.assertIn("outside.md", str(raised.exception))

    def test_a_member_that_is_not_a_regular_file(self):
        os.mkfifo(self.package / "pipe")
        with self.assertRaises(inventory.InventoryError) as raised:
            inventory.manifest(self.package, self.SOURCE, self.INSTANT)
        self.assertIn("pipe", str(raised.exception))

    def test_a_directory_with_no_member(self):
        empty = self.package.parent / "empty"
        empty.mkdir()
        with self.assertRaises(inventory.InventoryError) as raised:
            inventory.manifest(empty, self.SOURCE, self.INSTANT)
        self.assertIn("no member", str(raised.exception))

    def test_every_code_it_names_is_in_the_one_table(self):
        named = {c01.MANIFEST_MEMBER_UNLISTED, c01.REF_UNAVAILABLE, c01.ID_BOUND_TO_OTHER_BYTES}
        self.assertEqual(named - set(errors.table()), set())


class RouteAndExposure(NamedExamples, unittest.TestCase):
    """U15's rules read back off the committed documents, so a rule moved out of a shape is
    caught here even when no example happens to exercise it."""

    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()
        cls.registry = records.registry(cls.schemas)

    def document(self, kind):
        return self.schemas[self.registry[kind][1]].document

    def defs(self, kind):
        return self.schemas[self.registry[kind][1]].defs

    def test_an_observation_is_observed_and_has_no_other_class(self):
        self.assertRefused("/evidence_class", "routes/observation_called_deterministic")
        held = self.document("surface_observation")["properties"]["evidence_class"]
        self.assertEqual(held, {"const": "observed"})
        self.assertIn("evidence_class", self.document("surface_observation")["required"])

    def test_only_the_qualifying_evidence_carries_a_separated_origin(self):
        self.assertRefused(
            "/subject",
            "routes/observation_qualifying_on_an_answer_the_host_generated")
        defs = self.defs("surface_observation")
        variants = [v["$ref"].rsplit("/", 1)[-1] for v in defs["exposure_evidence"]["oneOf"]]
        self.assertEqual(len(variants), 2, variants)
        origins = {name: defs[name]["properties"]["origin"]["$ref"].rsplit("/", 1)[-1]
                   for name in variants}
        self.assertEqual(sorted(origins.values()), ["not_an_answer", "verified_origin"])
        separated = [name for name, origin in origins.items() if origin == "verified_origin"]
        self.assertEqual(defs[separated[0]]["properties"]["qualifies"], {"const": "yes"})
        self.assertIn("separation_evidence_digest", defs["verified_origin"]["required"])

    def test_any_terminal_is_recordable_and_only_a_listed_one_is_claimable(self):
        self.assertRefused("/subject", "routes/observation_claiming_a_terminal_nobody_listed")
        self.assertRefused("/locale", "routes/observation_in_a_locale_the_product_has_no_text_for")
        document = self.document("surface_observation")
        defs = self.defs("surface_observation")
        self.assertEqual(defs["observed_terminal"]["properties"]["reported_as"]["type"],
                         "string")
        listed = defs["supported_terminal"]["enum"]
        self.assertTrue(listed, "a claim may name nothing, so no claim could ever be written")
        self.assertEqual(defs["support_claim"]["properties"]["terminal"]["$ref"],
                         "#/$defs/supported_terminal")
        # A claim is optional, and only a candidate subject has one (round-3 P4): the refusal of
        # an unlisted terminal therefore names the subject's branch, not the terminal.
        self.assertNotIn("claim", document["properties"])
        self.assertIn("claim", defs["candidate_subject"]["properties"])
        self.assertNotIn("claim", defs["candidate_subject"]["required"])
        self.assertNotIn("claim", defs["prototype_subject"]["properties"])

    def test_a_prototype_states_what_it_does_not_establish(self):
        self.assertRefused(
            "/subject",
            "routes/observation_of_a_prototype_that_says_nothing_about_what_it_establishes",
            "routes/observation_of_a_prototype")
        self.assertAccepted("routes/prototype_observation_that_qualifies_for_nothing")
        defs = self.defs("surface_observation")
        variants = [v["$ref"].rsplit("/", 1)[-1] for v in defs["observation_subject"]["oneOf"]]
        prototype = [name for name in variants
                     if defs[name]["properties"]["is"] == {"const": "prototype"}]
        self.assertEqual(len(prototype), 1, variants)
        self.assertEqual(defs[prototype[0]]["properties"]["establishes"],
                         {"const": "neither_product_nor_human_evidence"})
        self.assertIn("establishes", defs[prototype[0]]["required"])

    def test_focus_is_optional_and_a_selection_is_not(self):
        self.assertRefused("/selected", "routes/selection_that_only_focused")
        document = self.document("route_selection")
        self.assertIn("focused", document["properties"])
        self.assertNotIn("focused", document["required"])
        for name in ("selected", "expected", "request_id"):
            self.assertIn(name, document["required"])

    def test_installed_and_delivered_are_different_stages(self):
        self.assertRefused("/expected/stage", "routes/selection_expecting_an_undeclared_effect")
        stages = self.defs("route_selection")["expected_effect"]["properties"]["stage"]["enum"]
        self.assertEqual(sorted(stages), ["adopted", "configured", "delivered", "draft_saved",
                                          "installed", "prepared", "published"])
        # SSOT: saving a draft does not publish or adopt, so it is an effect of its own.
        self.assertAccepted("routes/selection_expecting_a_saved_draft")

    def test_the_ways_back_are_one_list_named_once(self):
        """c03's result and an offered route point at one definition, not two copies."""
        naming = {identifier for identifier, loaded in self.schemas.items()
                  if "recovery" in loaded.defs}
        self.assertGreater(len(naming), 1, naming)
        bodies = {examples.canonical_form(self.schemas[i].defs["recovery"]) for i in naming}
        self.assertEqual(len(bodies), 1, naming)
        self.assertEqual(self.document("operation_result")["properties"]["supported_recovery"],
                         {"$ref": "#/$defs/recovery"})


class SessionRouting(NamedExamples, unittest.TestCase):
    """U16's rules read off the committed document: what an activated session receives, and the
    two things a route has no way to change."""

    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()
        identifier = records.registry(cls.schemas)["session_routing"][1]
        cls.document = cls.schemas[identifier].document
        cls.defs = cls.schemas[identifier].defs

    def variants(self):
        return {name.rsplit("/", 1)[-1] for name in
                (v["$ref"] for v in self.defs["session_delivery"]["oneOf"])}

    def test_an_activated_session_always_carries_the_usage_contract(self):
        self.assertRefused(
            "/delivery",
            "session/activated_without_the_usage_contract",
            "session/activated_with_a_null_usage_contract")
        self.assertAccepted("session/activated_with_nothing_selected_still_carries_the_contract")
        activated = self.defs["activated_delivery"]
        self.assertIn("memory_usage", activated["required"])
        # Zero selected Instructions is a real delivery, so the projections may be empty.
        self.assertEqual(activated["properties"]["projections"]["$ref"], "#/$defs/digests")
        self.assertNotIn("minItems", self.defs["digests"])

    def test_a_session_that_was_only_selected_has_nowhere_to_put_a_delivery(self):
        self.assertRefused("/delivery", "session/selected_only_that_delivered_anyway")
        only = self.defs["selected_only_delivery"]
        self.assertEqual(set(only["properties"]), {"state"})
        self.assertIs(only["additionalProperties"], False)
        self.assertEqual(len(self.variants()), 2, self.variants())

    def test_the_always_surface_has_no_value_for_an_addition(self):
        self.assertRefused("/always_surface", "session/a_route_that_adds_to_the_always_surface")
        self.assertEqual(sorted(self.document["properties"]["always_surface"]["enum"]),
                         ["reduced", "unchanged"])
        self.assertIn("always_surface", self.document["required"])

    def test_a_native_instruction_file_is_preserved_and_has_no_other_value(self):
        self.assertRefused("/native_files", "session/a_route_that_writes_a_native_global_file")
        self.assertEqual(self.document["properties"]["native_files"], {"const": "preserved"})
        self.assertIn("native_files", self.document["required"])

    def test_a_guide_is_named_and_held(self):
        self.assertRefused("/delivery", "session/a_guide_named_but_not_held")
        self.assertEqual(sorted(self.defs["guide_pointer"]["required"]), ["digest", "path"])
        self.assertIn("guide", self.defs["usage_contract"]["required"])

    def test_the_record_is_the_runtimes_own_and_never_a_submission(self):
        self.assertRefused("", "session/routing_is_never_submitted")
        self.assertIs(self.document[schema.RUNTIME_OWNED], True)
        self.assertEqual(examples.owned_places(
            self.schemas[records.registry(self.schemas)["session_routing"][1]]), {""})


class ClosedNames(NamedExamples, unittest.TestCase):
    """U10 closes two open patterns. Each committed enum is projected from a module tuple, so
    these hold the artifact against its owner rather than restating the list a third time."""

    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()
        cls.contracts = {}
        for path in sorted(pathlib.Path(c03.__file__).parent.glob("c*.py")):
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                if getattr(node.targets[0], "id", "") == "OPERATIONS":
                    cls.contracts[path.stem] = ast.literal_eval(node.value)

    def test_every_contract_declares_the_operations_it_owns(self):
        self.assertEqual(len(self.contracts), 12, sorted(self.contracts))
        for name, operations in self.contracts.items():
            self.assertTrue(operations, f"{name} declares no operation")
            self.assertEqual(len(set(operations)), len(operations), name)

    def test_one_operation_name_has_one_owning_contract(self):
        seen = {}
        for name, operations in self.contracts.items():
            for operation in operations:
                self.assertNotIn(operation, seen,
                                 f"{operation} declared by {seen.get(operation)} and {name}")
                seen[operation] = name

    def test_a_request_may_name_only_an_operation_a_contract_declares(self):
        self.assertRefused(
            "/operation",
            "c03/request_naming_an_undeclared_operation",
            "c07/assessment_naming_an_undeclared_operation")
        union = sorted({o for ops in self.contracts.values() for o in ops})
        for kind in ("operation_request", "action_assessment"):
            identifier = records.registry(self.schemas)[kind][1]
            document = self.schemas[identifier].document
            self.assertEqual(document["properties"]["operation"], {"$ref": "#/$defs/operation"})
            self.assertEqual(self.schemas[identifier].defs["operation"], {"enum": union}, kind)

    def test_every_operation_says_what_it_takes_and_returns(self):
        # A payload is a record a caller may submit; a returned record is one some contract owns.
        kinds = records.registry(self.schemas)
        owned = {kind for module in errors.OWNERS for kind in getattr(module, "RECORD_KINDS", ())}
        for operations in self.contracts.values():
            for operation, row in operations.items():
                self.assertEqual(set(row), {"takes", "returns"}, operation)
                for kind in row["takes"] + row["returns"]:
                    self.assertIn(kind, owned, f"{operation} names {kind}, which no module owns")
                for kind in row["takes"]:
                    document = self.schemas[kinds[kind][1]].document
                    self.assertNotIn(schema.RUNTIME_OWNED, document,
                                     f"{operation} takes {kind}, which only the runtime writes")

    def test_a_result_may_name_only_a_kind_some_operation_returns(self):
        self.assertRefused("/outputs", "c03/result_naming_a_kind_no_operation_returns")
        union = sorted({kind for operations in self.contracts.values()
                        for row in operations.values() for kind in row["returns"]})
        identifier = records.registry(self.schemas)["operation_result"][1]
        self.assertEqual(self.schemas[identifier].defs["output_kind"], {"enum": union})

    def test_a_request_names_no_payload_kind_of_its_own(self):
        # The payload's bytes name their kind; a second statement of it could disagree.
        self.assertRefused("/payload_kind", "c03/request_stating_its_payload_kind")
        identifier = records.registry(self.schemas)["operation_request"][1]
        self.assertNotIn("payload_digest", self.schemas[identifier].document["required"])

    def test_every_projected_list_is_what_its_owners_declare(self):
        # project-names.py is the one writer of these lists; this is its --check.
        spec = importlib.util.spec_from_file_location(
            "project_names", pathlib.Path(__file__).with_name("project-names.py"))
        projector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(projector)
        names = projector.lists()
        self.assertTrue(all(names.values()), names)
        taken = 0
        for identifier, loaded in self.schemas.items():
            if names.keys() & loaded.defs.keys():
                taken += 1
                self.assertEqual(projector.projected(loaded.document, names), loaded.document,
                                 identifier)
        self.assertGreaterEqual(taken, 17)

    def test_a_record_may_state_only_a_gap_a_contract_declares(self):
        # One list in every document that defines a gap, projected from the modules' error rows.
        self.assertRefused("/material_gaps", "c06/a_gap_no_contract_declares")
        carrying = {identifier: loaded.defs["gap"] for identifier, loaded in self.schemas.items()
                    if "gap" in loaded.defs}
        self.assertEqual(len(carrying), 18, sorted(carrying))
        for identifier, gap in carrying.items():
            self.assertEqual(gap["properties"]["code"], {"enum": sorted(errors.in_results())},
                             identifier)

    def test_an_entrance_may_name_only_an_entrance_the_contract_declares(self):
        self.assertRefused(
            "/entrance/name",
            "c04/plan_from_an_undeclared_entrance",
            "routes/offer_from_an_undeclared_entrance")
        for kind in ("projection_plan", "route_offer"):
            identifier = records.registry(self.schemas)[kind][1]
            name = self.schemas[identifier].defs["entrance"]["properties"]["name"]
            self.assertEqual(name, {"enum": list(c03.ENTRANCES)}, kind)
            self.assertNotIn("pattern", name)


class EntranceDisposition(NamedExamples, unittest.TestCase):
    """U10's closing property, held against the reader rather than the document's shape: an
    entrance that reaches state the target keeps has no spelling that names no guard."""

    GUARDED = {"choke_point", "routed"}
    REACHES_NOTHING = {"retired_at_cutover", "no_reach"}

    @classmethod
    def setUpClass(cls):
        cls.schemas = committed_schemas()
        registry = records.registry(cls.schemas)
        cls.disposition = cls.schemas[registry["entrance_disposition"][1]]
        cls.plan = cls.schemas[registry["cutover_plan"][1]]

    def states(self):
        """The state each disposition variant fixes, read through the variant the record uses."""
        refs = self.disposition.document["properties"]["disposition"]["oneOf"]
        return [self.disposition.defs[ref["$ref"].rsplit("/", 1)[-1]]["properties"]["state"]
                ["const"] for ref in refs]

    def test_the_construction_sites_and_the_guarded_set_are_one_set(self):
        # Compared by the state each spelling fixes: a variant renamed or replaced under an old
        # name changes this set. Two spellings reach nothing: one writes nothing at all, one
        # writes only under a root the entrance fixes itself.
        self.assertEqual(set(self.states()), self.GUARDED | self.REACHES_NOTHING)
        self.assertRefused(
            "/disposition",
            "c03/a_reach_that_names_no_guard",
            "c03/a_guard_outside_the_three",
            "c03/an_unreached_entrance_naming_a_choke_point",
            "c03/a_disposition_in_a_fifth_state")
        self.assertAccepted("c03/the_store_admits_what_it_owns",
                            "c03/a_bridge_reaches_only_through_its_owner")

    def test_a_root_the_caller_chose_cannot_claim_to_miss_kept_state(self):
        # C03's own question includes "through a root the caller chose": such a writer is routed.
        self.assertRefused("/disposition", "c03/a_caller_rooted_writer_claiming_to_miss_kept_state")
        self.assertAccepted("c03/a_caller_rooted_writer_routed_through_the_store")

    def test_every_disposition_names_the_route_it_disposes_of(self):
        self.assertRefused("/route", "c03/a_disposition_naming_no_route")

    def test_a_compatibility_route_names_the_route_it_forwards_to(self):
        self.assertAccepted("c03/a_compatibility_route_names_its_successor")
        self.assertRefused("/disposition", "c03/a_retirement_naming_a_category_as_successor")

    def test_a_choke_point_admits_something_and_only_declared_operations(self):
        self.assertRefused(
            "/disposition",
            "c03/a_choke_point_admitting_no_operation",
            "c03/a_choke_point_admitting_a_name_no_contract_declares")

    def test_every_reason_for_reaching_nothing_is_one_the_trace_found(self):
        defs = self.disposition.defs
        whys = defs["no_reach"]["properties"]["why"]["enum"] + [
            defs["holds_no_write"]["properties"]["why"]["const"]]
        self.assertEqual(sorted(whys), sorted(c03.NO_REACH_REASONS))
        self.assertAccepted("c03/an_entrance_that_writes_only_under_temp")
        self.assertRefused("/disposition", "c03/a_reason_the_trace_never_found")

    def test_the_cutover_has_three_stages_that_cannot_be_reordered(self):
        document = self.plan.document
        for stage in ("quiesce", "verify", "commit"):
            self.assertIn(stage, document["required"])
            self.assertNotEqual(document["properties"][stage].get("type"), "array")
        self.assertAccepted("c03/one_cutover_sealed_verified_and_committed_once")
        self.assertRefused("/abortable_until", "c03/a_cutover_abortable_past_its_commit")

    def test_quiescing_seals_every_owner_without_counting_them(self):
        self.assertRefused(
            "/quiesce/sealed",
            "c03/a_cutover_that_sealed_two_of_three",
            "c03/a_cutover_sealing_one_owner_twice")
        self.assertRefused(
            "/quiesce/in_flight",
            "c03/a_cutover_starting_with_an_operation_in_flight")

    def test_the_cutover_does_not_restate_what_retires(self):
        # Each route says so in its own disposition; a second copy is a second thing to keep true.
        self.assertRefused("/retires", "c03/a_cutover_restating_what_retires")

    def test_one_commit_and_abortable_until_it(self):
        self.assertRefused("/commit/commits", "c03/a_cutover_that_would_commit_twice")
        self.assertRefused(
            "/verify/unrouted_writers",
            "c03/a_cutover_verified_with_a_writer_left_unrouted")


class UniqueBy(unittest.TestCase):
    """`x-unique-by` states an identity JSON Schema cannot: items of the named sibling arrays may
    not share one property's value, although whole items differ."""

    DOCUMENT = {"type": "object", "additionalProperties": False,
                "x-unique-by": {"key": "path", "across": ["kept", "dropped"]},
                "properties": {name: {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["path", "n"],
                    "properties": {"path": {"type": "string"}, "n": {"type": "integer"}}}}
                    for name in ("kept", "dropped")} | {"label": {"type": "string"}}}

    def test_one_key_twice_within_or_across_the_arrays_is_refused_at_the_later_item(self):
        loaded = schema.load_schema(self.DOCUMENT)
        a, b = {"path": "a", "n": 1}, {"path": "a", "n": 2}
        self.assertEqual(loaded.validate({"kept": [a], "dropped": [{"path": "b", "n": 1}]}), [])
        self.assertEqual([(v.code, v.pointer) for v in loaded.validate({"kept": [a, b]})],
                         [(schema.DUPLICATE_ITEM, "/kept/1")])
        across = loaded.validate({"kept": [a], "dropped": [b]})
        self.assertEqual([(v.code, v.pointer) for v in across],
                         [(schema.DUPLICATE_ITEM, "/dropped/0")])

    def test_a_malformed_declaration_fails_at_load(self):
        for bad in ({"key": "path"}, {"key": "path", "across": []}, {"key": 1, "across": ["kept"]},
                    {"key": "path", "across": ["absent"]}, "path",
                    {"key": "path", "across": ["label"]}, {"key": "paht", "across": ["kept"]}):
            with self.subTest(bad=bad), self.assertRaises(schema.SchemaError) as caught:
                schema.load_schema({**self.DOCUMENT, "x-unique-by": bad})
            self.assertEqual(caught.exception.code, schema.INVALID_SCHEMA)


class BoundFields(NamedExamples, unittest.TestCase):
    """Repair round 1 after the interim cross-provider review: each rule below was two fields
    that had to agree and could be written independently, or a required state with no spelling.
    Each test names the committed example that shows its rule."""

    def test_a_sign_out_cannot_leave_access_active(self):
        self.assertRefused(
            "/state",
            "c02/sign_out_that_leaves_access_active",
            "c02/recovery_that_restores_access")

    def test_a_head_moving_request_names_the_base_it_expects(self):
        self.assertRefused(
            "/target",
            "c03/commit_without_a_base",
            "c03/publication_expecting_an_unversioned_source")
        self.assertAccepted("c03/commit_request")

    def test_a_withdrawn_participant_is_never_an_applicable_option(self):
        self.assertRefused("/standing", "c05/a_withdrawn_participant_still_applicable")

    def test_an_active_choice_keeps_no_ended_participant(self):
        # SSOT S07: a withdrawal invalidates the stored choice, so an ended participant is
        # history of an invalidated one. Round 1 accepted the first example; that was the defect.
        self.assertRefused("/standing", "c05/a_withdrawn_participant_kept_in_the_set")
        self.assertAccepted("c05/a_withdrawn_participant_kept_as_history")

    def test_a_denied_read_names_no_source(self):
        self.assertRefused("/outcome", "c06/denied_that_names_a_source")
        self.assertAccepted("c06/denied_is_not_empty")

    def test_an_invitation_precedes_consent(self):
        self.assertAccepted("c08/invited_before_consent")
        self.assertRefused(
            "/standing",
            "c08/invited_standing_that_names_a_consent",
            "c08/invitation_admission_without_consent")

    def test_a_settled_transfer_states_no_gap(self):
        self.assertRefused("/stage", "c09/committed_with_continuity_unverified")

    def test_one_object_is_promised_or_evictable_not_both(self):
        self.assertRefused("/evictable", "c10/one_object_promised_and_evictable")

    def test_a_manifest_lists_each_path_once(self):
        self.assertRefused("/members", "sources/one_path_listed_twice_with_two_digests")

    def test_a_custody_holder_is_named(self):
        self.assertRefused("/holder", "c10/peer_holder_with_no_peer")

    def test_a_replica_is_not_a_recipient(self):
        self.assertRefused(
            "/requested/recipient_kind",
            "c07/a_replica_that_holds_the_bytes_is_not_a_recipient")

    def test_publication_happens_in_one_order(self):
        self.assertRefused(
            "/choice/publication_order",
            "bindings/storage_committing_before_it_stages",
            "bindings/storage_publishing_in_four_steps")

    def test_a_host_is_not_qualified_by_its_own_declaration(self):
        self.assertRefused("/qualification", "bindings/host_qualified_on_its_own_declaration")

    def test_a_personal_preparation_may_select_nothing(self):
        self.assertAccepted("c07/personal_preparation_with_nothing_selected")

    def test_an_environment_is_published_and_then_adopted_separately(self):
        self.assertIn("environment.publish", c07.OPERATIONS)
        self.assertIn("environment.adopt", c07.OPERATIONS)


class BoundFieldsRoundTwo(NamedExamples, unittest.TestCase):
    """Repair round 2, after the second cross-provider review: the same two failures again —
    fields that had to agree left apart, and required states with no spelling."""

    def test_every_owner_that_keeps_a_head_is_asked_for_its_base(self):
        # SSOT: a collection keeps its original head and a Team the head its finalizer orders.
        self.assertEqual(c03.HEAD_KEEPING, ("src", "col", "env", "tem"))
        self.assertRefused("/target", "c03/commit_to_a_collection_naming_no_base")
        self.assertAccepted("c03/commit_to_a_collection_head")

    def test_a_result_answers_a_request_its_owner_holds(self):
        self.assertRefused("/request_digest", "c03/a_result_answering_no_request")
        self.assertRefused("/actual_stage", "c03/a_request_not_held_that_reports_a_stage")
        self.assertRefused("", "c03/request_not_held_is_never_submitted")
        self.assertAccepted("c03/query_for_a_request_never_received")

    def test_a_denied_read_carries_no_continuation(self):
        self.assertRefused("/outcome", "c06/denied_with_a_continuation")

    def test_a_waiting_read_names_the_use_and_question_it_waits_on(self):
        self.assertRefused("/outcome", "c06/waiting_without_the_use_it_waits_on",
                           "c06/pending_reference_without_its_version")
        self.assertAccepted("c06/result_waiting_on_the_person")

    def test_a_preparation_of_nothing_names_no_frontier(self):
        self.assertAccepted("c07/preparation_of_nothing")

    def test_verification_that_found_a_gap_did_not_verify(self):
        self.assertRefused("/stage", "c09/verified_with_continuity_unverified")
        self.assertAccepted("c09/inventory_whose_body_is_absent")

    def test_only_what_can_be_rebuilt_is_evictable(self):
        self.assertRefused("/evictable", "c10/an_outbox_row_offered_for_eviction")
        self.assertAccepted("c10/promised_and_evictable_are_two_lists")


class BoundFieldsRoundThree(NamedExamples, unittest.TestCase):
    """Repair round 3, after the third cross-provider review."""

    def test_a_commit_names_its_receipt_and_states_only_disclosures(self):
        self.assertRefused("/outcome", "c03/committed_beside_a_stale_base",
                           "c03/committed_without_its_receipt", "c03/stage_outside_the_list")
        self.assertAccepted("c03/committed", "bindings/committed_on_an_unencrypted_volume")
        disclosed = committed_schemas()["c03_operation_result"].defs["disclosed_gap"]
        self.assertEqual(disclosed["properties"]["code"], {"enum": sorted(errors.disclosed())})
        self.assertEqual(sorted(errors.disclosed()), ["storage_not_encrypted"])

    def test_every_cause_the_source_names_separately_has_a_code(self):
        # 02:10 design: an unencrypted volume is disclosed; SSOT: an unreachable carrier is
        # reported apart from missing credentials, controls and bodies.
        self.assertAccepted("bindings/committed_on_an_unencrypted_volume",
                            "c02/blocked_on_an_unreachable_carrier")

    def test_only_a_candidate_can_claim_support(self):
        self.assertRefused("/subject", "routes/prototype_observation_claiming_support")

    def test_a_first_exposure_trial_keeps_what_was_said_apart_from_what_happened(self):
        self.assertAccepted("routes/a_trial_that_mistook_a_draft_for_publication")
        self.assertRefused("/stated", "routes/a_trial_without_a_prediction")
        self.assertRefused("/participant", "routes/a_trial_naming_a_principal")
        self.assertRefused("/assistance", "routes/help_given_without_saying_what")

    def test_an_answer_over_no_source_is_empty_and_names_no_frontier(self):
        self.assertAccepted("c06/empty_answer_over_no_source", "c05/state_over_no_source")
        self.assertRefused("/outcome", "c06/result_without_a_frontier")

    def test_the_founder_seals_the_finalizer(self):
        self.assertRefused("/finalizer", "c08/founding_proposal_without_its_finalizer")

    def test_every_gap_list_in_every_document_is_the_projection(self):
        # Found by where material_gaps occurs, not by a definition's name, so a gap list written
        # without the shared definition is seen.
        places = []

        def walk(node, where, schema_id, defs):
            if isinstance(node, dict):
                for name, child in node.get("properties", {}).items():
                    if name == "material_gaps":
                        places.append((schema_id, f"{where}/{name}", child))
                for key, child in node.items():
                    if key != "properties":
                        walk(child, f"{where}/{key}", schema_id, defs)
                for name, child in node.get("properties", {}).items():
                    walk(child, f"{where}/properties/{name}", schema_id, defs)
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, f"{where}/{index}", schema_id, defs)

        for identifier, loaded in committed_schemas().items():
            walk(loaded.document, "", identifier, loaded.defs)
        self.assertGreaterEqual(len(places), 16)
        lists = {"#/$defs/gap": sorted(errors.in_results()),
                 "#/$defs/disclosed_gap": sorted(errors.disclosed())}
        for identifier, where, child in places:
            with self.subTest(schema=identifier, at=where):
                defs = committed_schemas()[identifier].defs
                # A runtime-owned mark says who writes the list, not what it may hold.
                bare = {k: v for k, v in child.items() if k != schema.RUNTIME_OWNED}
                items = defs["gaps"]["items"] if bare == {"$ref": "#/$defs/gaps"} \
                    else bare.get("items", {})
                self.assertIn(items.get("$ref"), lists)
                name = items["$ref"].rsplit("/", 1)[-1]
                self.assertEqual(defs[name]["properties"]["code"], {"enum": lists[items["$ref"]]})


class EnvironmentEdition(NamedExamples, unittest.TestCase):
    """What `environment.publish` publishes and `environment.adopt` adopts (SSOT S05)."""

    def test_an_edition_is_derived_from_exact_parents_or_from_nothing(self):
        self.assertAccepted("c07/an_edition_derived_from_its_parent")
        self.assertRefused("/lineage", "c07/an_edition_following_its_parent_by_name",
                           "c07/a_first_edition_that_changes_something")

    def test_memory_is_a_policy_not_a_set_of_records(self):
        self.assertRefused("/memory_policy", "c07/an_edition_pinning_memory_records")

    def test_a_source_is_pinned_once_and_a_component_is_needed_or_optional(self):
        self.assertRefused("/knowledge", "c07/an_edition_pinning_one_source_twice")
        self.assertRefused("/components", "c07/a_component_both_needed_and_optional")


if __name__ == "__main__":
    unittest.main()
