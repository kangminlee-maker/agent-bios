"""Contract representation tests. Run by gates/workenv/check-workenv.py, one process per file."""
import hashlib
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from workenv.contracts import canonical, errors, examples, schema  # noqa: E402


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
        every = set(errors.table()) - set(errors.not_from_bytes())
        self.assertEqual(errors.coverage(every), [])
        missing = errors.coverage(every - {canonical.DUPLICATE_KEY})
        self.assertEqual(len(missing), 1)
        self.assertIn(canonical.DUPLICATE_KEY, missing[0])
        self.assertIn("no negative example", missing[0])
        unknown = errors.coverage(every | {"not_in_the_table"})
        self.assertEqual(len(unknown), 1)
        self.assertIn("not_in_the_table", unknown[0])


class ContractExamples(unittest.TestCase):
    """The real examples pass; each rule of the checker fails by name on a copy with one
    thing planted. A copy per case, so no case depends on what another left behind."""

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
        every = set(errors.table())
        exempt = set(errors.not_from_bytes())
        self.assertEqual(exempt, {canonical.UNSUPPORTED_TYPE})
        self.assertEqual(errors.coverage(every - exempt), [])
        stale = errors.coverage(every)
        self.assertEqual(len(stale), 1)
        self.assertIn("the declaration is stale", stale[0])
        with mock.patch.dict(canonical.NOT_FROM_BYTES, {"not_in_the_table": "x"}):
            dangling = errors.coverage(every - exempt)
        self.assertEqual(len(dangling), 1)
        self.assertIn("is not in the table", dangling[0])


if __name__ == "__main__":
    unittest.main()
