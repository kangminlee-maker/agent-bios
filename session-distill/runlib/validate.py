#!/usr/bin/env python3
"""The one schema validator of the driver: jsonschema, loaded as learn/check-learning.py loads it.

A schema is accepted in two steps, in this order. `Draft202012Validator.check_schema` refuses
a schema that is not valid JSON Schema (it raises `SchemaError`). Then `lint` applies the
project's policy, which jsonschema does not: it accepts unknown keywords, open objects and
subschemas that say nothing about their type as valid. The policy is that every subschema
declares what it is (`type`, `enum`, `const` or a local `$ref`), every object schema is closed
(`additionalProperties: false`, whether or not it says `type: object`), and every keyword is
one this lint can see through. Instance validation stays jsonschema's.

The driver runs under the interpreter `learn/check-learning.py` runs under, and refuses by name
(JSONSCHEMA_MISSING, JSONSCHEMA_VERSION_MISMATCH, JSONSCHEMA_PIN_UNREADABLE) a jsonschema other
than the one `JSONSCHEMA_PIN` in `launch/provision-venv.sh` names: the pin has one owner, and
the installed version is read from the package metadata.

  validate.py --self-test
"""
import importlib.metadata
import pathlib
import re
import sys

try:
    import jsonschema
except ImportError:
    sys.exit("validate: JSONSCHEMA_MISSING: the 'jsonschema' package is required "
             "(pip install jsonschema; verified 4.26.0 in DEPENDENCIES.md)")

PIN_FILE = pathlib.Path(__file__).resolve().parents[2] / "launch" / "provision-venv.sh"


def pinned_version(pin_file=PIN_FILE):
    """The version `JSONSCHEMA_PIN` names in `pin_file`, or None when it names none."""
    try:
        match = re.search(r'^JSONSCHEMA_PIN="jsonschema==([^"]+)"$', pathlib.Path(pin_file).read_text(encoding="utf-8"), re.M)
    except OSError:
        return None
    return match.group(1) if match else None


def version_problem(installed, pin_file=PIN_FILE):
    """None when `installed` is the jsonschema version `JSONSCHEMA_PIN` names in `pin_file`,
    else the named refusal."""
    pin = pinned_version(pin_file)
    if pin is None:
        return f'JSONSCHEMA_PIN_UNREADABLE: {pin_file} has no JSONSCHEMA_PIN="jsonschema==<version>" line to compare with'
    if installed != pin:
        return f"JSONSCHEMA_VERSION_MISMATCH: jsonschema {installed} is installed, {pin_file} pins {pin}"
    return None


_problem = version_problem(importlib.metadata.version("jsonschema"))
if _problem:
    sys.exit(f"validate: {_problem}")

# Keywords the lint understands. A keyword that carries a subschema is supported only when
# `lint` descends into it, so a closed-object rule cannot be bypassed by hiding an open
# object under `allOf`, `anyOf`, `if` and the like: those are not supported.
SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$comment", "title", "type", "required", "enum", "const", "pattern",
    "minimum", "minLength", "minItems", "maxItems", "minProperties", "uniqueItems",
    "dependentRequired",
    "additionalProperties",  # only `false` passes the lint
    "properties", "patternProperties", "items", "$defs",  # the subschema carriers `lint` descends into
    "$ref",                  # only `#/$defs/<name>` of the same schema
})
# Keywords that constrain an object; a subschema carrying any of them is an object schema
# whether or not it says `type: object`.
OBJECT_KEYWORDS = frozenset({"properties", "patternProperties", "required", "additionalProperties",
                             "minProperties", "dependentRequired"})


def lint(schema, path="#", root=None):
    """Policy violations of one schema, each naming the keyword or the subschema's place."""
    root = schema if root is None else root
    if not isinstance(schema, dict):
        return [f"SCHEMA_POLICY {path}: a subschema must be an object, got {type(schema).__name__}"]
    errors = [f"SCHEMA_POLICY unknown keyword {key!r} at {path}"
              for key in sorted(set(schema) - SUPPORTED_KEYWORDS)]
    if "$ref" in schema:
        ref = schema["$ref"]
        name = ref[len("#/$defs/"):] if isinstance(ref, str) and ref.startswith("#/$defs/") else None
        if name not in (root.get("$defs") or {}):
            errors.append(f"SCHEMA_POLICY {path}: $ref must name an entry of this schema's $defs, got {ref!r}")
    if not {"type", "enum", "const", "$ref"} & set(schema):
        errors.append(f"SCHEMA_POLICY untyped subschema at {path}: declare type, enum, const or $ref")
    types = schema.get("type")
    types = types if isinstance(types, list) else [types]
    if ("object" in types or OBJECT_KEYWORDS & set(schema)) and schema.get("additionalProperties") is not False:
        errors.append(f"SCHEMA_POLICY open object at {path}: additionalProperties must be false")
    for keyword in ("properties", "patternProperties", "$defs"):
        for name, sub in (schema.get(keyword) or {}).items():
            errors.extend(lint(sub, f"{path}/{keyword}/{name}", root))
    if "items" in schema:
        errors.extend(lint(schema["items"], f"{path}/items", root))
    return errors


class SchemaPolicyError(Exception):
    """A schema that jsonschema accepts but the policy refuses; the message lists every violation."""


def compile_schema(schema):
    """A validator for `schema`: `check_schema` first (raises `jsonschema.SchemaError`), then the lint."""
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = lint(schema)
    if errors:
        raise SchemaPolicyError("; ".join(errors))
    return jsonschema.Draft202012Validator(schema)


def violations(validator, instance):
    """jsonschema's errors for `instance`, in a stable order (for callers that need structure)."""
    return sorted(validator.iter_errors(instance), key=lambda e: list(map(str, e.absolute_path)))


def validate_instance(validator, instance):
    """Every violation of `instance`, as `<json path>: <message>`; empty when it conforms."""
    return [f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in violations(validator, instance)]


def self_test():
    import importlib.metadata
    import importlib.util
    failures = []
    good = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
            "additionalProperties": False, "required": ["a"],
            "properties": {"a": {"type": "string"},
                           "b": {"type": "array", "items": {"type": "object",
                                                            "additionalProperties": False,
                                                            "properties": {"c": {"type": "integer"}}}}}}
    try:  # positive control first: the valid, closed schema compiles and validates
        validator = compile_schema(good)
        if validate_instance(validator, {"a": "x", "b": [{"c": 1}]}):
            failures.append("a conforming instance was reported")
    except Exception as exc:
        failures.append(f"positive control: the valid closed schema was refused: {exc!r}")
        validator = None

    if validator is not None:
        found = validate_instance(validator, {"b": [{"c": "x", "d": 1}]})
        for want in ("<root>: 'a' is a required property", "b/0/c:", "b/0: Additional properties"):
            if not any(want in line for line in found):
                failures.append(f"instance violation missing {want!r}: {found}")

    def refused_with(schema, error_type, needle):
        try:
            compile_schema(schema)
        except error_type as exc:
            return needle in str(exc)
        except Exception:
            return False
        return False

    if not refused_with({"type": "object", "required": "x"}, jsonschema.SchemaError, "'x' is not of type 'array'"):
        failures.append("an invalid schema (required: \"x\") was not refused by check_schema with SchemaError")
    unknown = {**good, "properties": {"a": {"type": "string", "x-note": "ignored by jsonschema"}}}
    if not refused_with(unknown, SchemaPolicyError, "unknown keyword 'x-note' at #/properties/a"):
        failures.append("an unknown keyword was not refused by the lint, naming the keyword and its place")
    if not refused_with({k: v for k, v in good.items() if k != "additionalProperties"},
                        SchemaPolicyError, "open object at #:"):
        failures.append("an object without additionalProperties: false was not refused by the lint")
    nested = {**good, "properties": {"b": {"type": "array", "items": {"type": "object", "properties": {}}}}}
    if not refused_with(nested, SchemaPolicyError, "open object at #/properties/b/items"):
        failures.append("an open object nested under items was not named by its path")
    for open_form in (True, {"type": "string"}):
        if not refused_with({**good, "additionalProperties": open_form}, SchemaPolicyError, "open object at #:"):
            failures.append(f"additionalProperties {open_form!r} was not refused")
    if not refused_with({**good, "allOf": [{"type": "object"}]}, SchemaPolicyError, "unknown keyword 'allOf'"):
        failures.append("a subschema carrier the lint cannot see (allOf) was not refused")
    # an object that never says `type: object` is still an object schema, and must be closed
    implicit = {**good, "properties": {"a": {"required": ["x"], "additionalProperties": True}}}
    if not refused_with(implicit, SchemaPolicyError, "open object at #/properties/a"):
        failures.append("an implicit object schema (object keywords, no type) was not refused as open")
    implicit_bare = {**good, "properties": {"a": {"required": ["x"]}}}
    if not refused_with(implicit_bare, SchemaPolicyError, "open object at #/properties/a"):
        failures.append("an implicit object schema without additionalProperties was not refused as open")
    for bare in ({}, {"minLength": 1}):
        if not refused_with({**good, "properties": {"a": bare}}, SchemaPolicyError, "untyped subschema at #/properties/a"):
            failures.append(f"an untyped subschema {bare!r} was not refused")
    mapped = {"type": "object", "additionalProperties": False, "minProperties": 1,
              "patternProperties": {"^[a-z]+$": {"type": "object", "properties": {}}}}
    if not refused_with(mapped, SchemaPolicyError, "open object at #/patternProperties/^[a-z]+$"):
        failures.append("an open object under patternProperties was not named by its path")
    # positive controls for the carriers the lint supports: $defs with $ref, and a closed patternProperties map
    shared = {"type": "object", "additionalProperties": False, "required": ["k"],
              "$defs": {"sha": {"type": "string", "pattern": "^[0-9a-f]{4}$"}},
              "properties": {"k": {"$ref": "#/$defs/sha"}},
              "patternProperties": {"^x-": {"$ref": "#/$defs/sha"}}}
    try:
        validator_shared = compile_schema(shared)
        if validate_instance(validator_shared, {"k": "abcd", "x-1": "0123"}):
            failures.append("a conforming instance of a $ref schema was reported")
        if not validate_instance(validator_shared, {"k": "zzzz"}):
            failures.append("the $ref'd definition did not constrain the instance")
        if not validate_instance(validator_shared, {"k": "abcd", "other": "abcd"}):
            failures.append("a key outside patternProperties was accepted by a closed map")
    except Exception as exc:
        failures.append(f"positive control: a closed $defs/$ref/patternProperties schema was refused: {exc!r}")
    for ref in ("#/$defs/missing", "https://example.invalid/schema.json", "#/properties/k"):
        if not refused_with({**shared, "properties": {"k": {"$ref": ref}}}, SchemaPolicyError,
                            "$ref must name an entry of this schema's $defs"):
            failures.append(f"$ref {ref!r} was not refused")
    if not refused_with({**good, "properties": {"a": True}}, SchemaPolicyError, "must be an object"):
        failures.append("a boolean subschema was not refused")

    # a missing package and a package of another version are named failures at import, never a silent skip
    source = pathlib.Path(__file__).read_text(encoding="utf-8")

    def import_outcome(installed=None, missing=False):
        """What importing this module says when jsonschema is missing, or reports `installed`."""
        saved_module, saved_version = sys.modules.get("jsonschema"), importlib.metadata.version
        if missing:
            sys.modules["jsonschema"] = None  # makes `import jsonschema` raise ImportError
        if installed is not None:
            importlib.metadata.version = lambda name: installed
        try:
            module = importlib.util.module_from_spec(importlib.util.spec_from_loader("validate_probe", loader=None))
            module.__dict__["__file__"] = __file__
            exec(compile(source, __file__, "exec"), module.__dict__)
            return "imported"
        except SystemExit as exc:
            return str(exc)
        finally:
            importlib.metadata.version = saved_version
            if saved_module is None:
                sys.modules.pop("jsonschema", None)
            else:
                sys.modules["jsonschema"] = saved_module

    real_pin = pinned_version()
    if real_pin is None:
        failures.append(f"the real pin file {PIN_FILE} names no jsonschema version")
        real_pin = "unreadable"
    if "JSONSCHEMA_MISSING" not in import_outcome(missing=True):
        failures.append("import without jsonschema did not fail by name")
    if import_outcome(installed=real_pin) != "imported":
        failures.append("import under the pinned version was refused")
    if version_problem(importlib.metadata.version("jsonschema")) is not None:
        failures.append(f"the interpreter running this self-test does not carry the pinned jsonschema: "
                        f"{version_problem(importlib.metadata.version('jsonschema'))}")
    outcome = import_outcome(installed="4.25.1")
    if "JSONSCHEMA_VERSION_MISMATCH" not in outcome or "4.25.1" not in outcome or real_pin not in outcome:
        failures.append(f"import under another jsonschema version did not fail naming both versions: {outcome}")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        scratch = pathlib.Path(td) / "provision-venv.sh"
        text = PIN_FILE.read_text(encoding="utf-8")
        scratch.write_text(text.replace(f'"jsonschema=={real_pin}"', '"jsonschema==9.9.9"'), encoding="utf-8")
        planted = version_problem(importlib.metadata.version("jsonschema"), scratch)
        if not (planted and "JSONSCHEMA_VERSION_MISMATCH" in planted and "9.9.9" in planted):
            failures.append(f"a planted pin 9.9.9 was not refused by name: {planted}")
        scratch.write_text(text.replace("JSONSCHEMA_PIN=", "OTHER_PIN="), encoding="utf-8")
        if "JSONSCHEMA_PIN_UNREADABLE" not in (version_problem(real_pin, scratch) or ""):
            failures.append("a pin file without JSONSCHEMA_PIN was not refused by name")
        if "JSONSCHEMA_PIN_UNREADABLE" not in (version_problem(real_pin, pathlib.Path(td) / "absent.sh") or ""):
            failures.append("a missing pin file was not refused by name")

    for failure in failures:
        print(f"validate --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"validate --self-test: OK (jsonschema {importlib.metadata.version('jsonschema')}; check_schema refusal, "
          "unknown keyword, open object (explicit, nested, implicit, under patternProperties), untyped "
          "subschema, hidden subschema, $defs/$ref, missing package)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: validate.py --self-test")
    sys.exit(self_test())
