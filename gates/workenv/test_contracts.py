"""Contract representation tests. Run by gates/workenv/check-workenv.py, one process per file."""
import hashlib
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from workenv.contracts import canonical, errors, schema  # noqa: E402


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

    def test_patterns_outside_the_shared_dialect_fail_by_name(self):
        bad = ("[a-z]+", "^[a-z]+", "[a-z]+$", "^a|b$", "^a.b$", "^a\\sb$", "^\\bword$", "^a\\$",
               "^(?=a)a$", "^(?P<n>a)$", "^(a)\\1$", "^[[:alpha:]]$", "^[]a]$", "^[^]a]$", "^a^b$",
               "^a$b$", "^(a$", "^a)$", "^[a$", "^caf" + chr(0xE9) + "$", "^a\\", "^*$", "")
        for pattern in bad:
            with self.subTest(pattern=pattern):
                self.refused(schema.UNSUPPORTED_PATTERN, {"type": "string", "pattern": pattern},
                             "/pattern")
        good = ("^[0-9a-f]{64}$", "^(?:a|b)+$", "^(a|b)c$", "^\\d{4}-\\d{2}$", "^\\w+\\.json$",
                "^a\\\\$", "^[^/]+(?:/[^/]+)*$", "^$", "^a\\|b$", "^[.$^|]$")
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
        self.assertEqual(set(joined), set(canonical.ERRORS) | set(schema.ERRORS))
        self.assertEqual(len(joined), len(canonical.ERRORS) + len(schema.ERRORS))
        for code, entry in joined.items():
            with self.subTest(code=code):
                self.assertRegex(code, r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
                self.assertTrue(entry["meaning"].strip())

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
        every = set(errors.table())
        self.assertEqual(errors.coverage(every), [])
        missing = errors.coverage(every - {canonical.DUPLICATE_KEY})
        self.assertEqual(len(missing), 1)
        self.assertIn(canonical.DUPLICATE_KEY, missing[0])
        self.assertIn("no negative example", missing[0])
        unknown = errors.coverage(every | {"not_in_the_table"})
        self.assertEqual(len(unknown), 1)
        self.assertIn("not_in_the_table", unknown[0])


if __name__ == "__main__":
    unittest.main()
