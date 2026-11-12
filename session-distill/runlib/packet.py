#!/usr/bin/env python3
"""The packet a model call is sent, and the linter every packet passes before dispatch.

A dispatched packet is the per-call envelope followed by the judgment payload:

  CALL-ID: <call_id>
  STAGE: <stage>
  SEAT: <provider:model/effort>
  SCHEMA: sha256:<hex of schema.json> | none
  PRINCIPLES: sha256:<hex of the principles block>

  <the principles block>
  === PAYLOAD ===
  <the payload>

`packet_sha256` (the receipt's) hashes the whole packet and is unique per call, since the
envelope carries the call id; `payload_sha256` hashes the payload alone and is what two calls
of one judgment share, so a judgment-reuse key is computed over the payload and never over
the envelope.

The principles block carries what a hermetic reader cannot load (plan P9): concept economy,
the LLM/capability boundary, the staged workflow, verification discipline and the
mock/realization boundary. Each summary is taken from the guide that owns it — its frontmatter
`core_rules`, or, for the staged-workflow guide, which declares none, its `## Stages` list — so
nothing here restates a guide, and the block's hash says which version a packet carried.

The schema a call is given is compiled through `validate.compile_schema` (closed objects,
supported keywords) before it is written, so a packet never references a schema the policy
refuses. The form a host is handed holds only keywords the host's draft-07 check and the policy's
2020-12 reading read alike (HOST_KEYWORDS); any other is HOST_SCHEMA_KEYWORD.

A stage's payload is one of the templates under `session-distill/packets/` (`read.md`, `stitch.md`)
with its `{{field}}` placeholders filled by `render`, once and in one pass: every placeholder takes
exactly one field, no field is left over, and a field's text is never read as a template, so a
transcript quoting `{{window}}` stays text.

Linter failures are named CALL_ID_MISSING, PRINCIPLES_MISSING, SCHEMA_REFERENCE_MISSING and
PAYLOAD_MISSING; a guide without its section is PRINCIPLES_UNAVAILABLE; a template that is not there,
or fields that are not its placeholders, are TEMPLATE_UNAVAILABLE and TEMPLATE_FIELDS_MISMATCH.

  packet.py --self-test
"""
import hashlib
import json
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import validate

REPO = pathlib.Path(__file__).resolve().parents[2]
PAYLOAD_MARKER = "=== PAYLOAD ==="
TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[1] / "packets"
TEMPLATES = ("read", "stitch", "form", "judge", "sweep", "cross_review", "reconsider")  # S3's two calls (plan WP-08), S4's one (plan WP-09), S6's judges', sweeps', cross-review and reconsiderations (plan WP-11)
WINDOW_TEMPLATES = ("read", "stitch")  # the calls whose fixed part the view windows were cut to leave room for
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
# (summary title, owning guide, the part of it that is the summary)
PRINCIPLE_SOURCES = (
    ("Concept economy", "claude/guides/concept-economy.md", "core_rules"),
    ("LLM and capability boundary", "claude/guides/llm-capability-boundary.md", "core_rules"),
    ("Staged workflow", "claude/guides/coding-staged-workflow.md", "## Stages"),
    ("Verification discipline", "claude/guides/verification-discipline.md", "core_rules"),
    ("Mock and realization boundary", "claude/guides/mock-realization-boundary.md", "core_rules"),
)


class Unavailable(Exception):
    """A guide lacks the section its summary is taken from; the message starts with PRINCIPLES_UNAVAILABLE."""


class TemplateError(Exception):
    """A payload template is missing or was given other fields than its placeholders; the message starts with
    TEMPLATE_UNAVAILABLE or TEMPLATE_FIELDS_MISMATCH."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def summary(text, part, where):
    """The lines of `part` in one guide's text: a frontmatter list, or the body under a heading."""
    if part.startswith("## "):
        body = text.split(f"\n{part}\n", 1)[1].split("\n## ", 1)[0] if f"\n{part}\n" in text else ""
        lines = body.splitlines()
    else:
        front = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
        block = re.search(rf"^{re.escape(part)}:\n((?:  - .*\n?)+)", front + "\n", re.M)
        lines = ["- " + line[4:] for line in block.group(1).splitlines()] if block else []
    lines = [line for line in lines if line.strip()]
    if not lines:
        raise Unavailable(f"PRINCIPLES_UNAVAILABLE {where}: no {part!r} to summarize")
    return "\n".join(lines)


def principles_block(repo=REPO):
    texts = {}
    for _title, guide, _part in PRINCIPLE_SOURCES:
        try:
            texts[guide] = (pathlib.Path(repo) / guide).read_text(encoding="utf-8")
        except OSError as exc:
            raise Unavailable(f"PRINCIPLES_UNAVAILABLE {guide}: {exc}") from exc
    return "\n\n".join(["# Working principles (the instructions you do not load)"]
                       + [f"## {title} ({guide})\n{summary(texts[guide], part, guide)}"
                          for title, guide, part in PRINCIPLE_SOURCES]) + "\n"


def host_schema(schema):
    """The schema a host is handed, derived from `schema` by code and never written by hand (WP-08 commit 7, dw2-live1):
    no `$schema`, every `$ref` replaced by a copy of the `$defs` entry it names, and no `$defs`.

    Claude Code's `--json-schema` check builds Ajv's draft-07 class, which refuses a schema naming a meta-schema it does
    not hold - the 2020-12 one every distill schema names - and exits before any request; and the host hands the schema
    on as a tool's input schema, which then holds no reference to resolve. The policy pins draft 2020-12 in code
    (`validate.compile_schema`) and allows a `$ref` only to an entry of the schema's own `$defs` (`validate.lint`), so
    neither key decides anything the inlined form does not. A `$ref` beside other keywords, one that reaches itself, or
    one naming no entry of `$defs` has no inlined form and is refused. A reference's name is read by
    `validate.local_ref_name`, as the policy's lint reads it: a name of letters, digits, `_` and `-` only, which a JSON
    Pointer resolves as written, so nothing is decoded here (WP-08c, W r2).

    The schema is walked by its structure, as `host_keywords` walks it (WP-08c, X and W r1): a reference is a `$ref` at
    a schema position, and the schemas inside are the values under `properties` and `patternProperties` by name and
    the schema `items` or `additionalProperties` holds. A property named `$ref` is a name, and an `enum`, `const`,
    `default` or `examples` value is data, kept as written: a literal `{"$ref": ...}` there is not a reference, and
    inlining it would hand the host a schema that accepts other answers. Any other keyword's value is kept as written
    too, and `host_keywords` then refuses the keyword by name."""
    defs = schema.get("$defs") or {}

    def inline(node, seen):
        if not isinstance(node, dict):
            return node  # a boolean schema, or `items` as a list, which `host_keywords` refuses
        if "$ref" in node:
            ref = node["$ref"]
            name = validate.local_ref_name(ref)
            if set(node) != {"$ref"}:
                raise validate.SchemaPolicyError(f"HOST_SCHEMA {ref}: a $ref beside {sorted(set(node) - {'$ref'})} has no inlined form")
            if name is None:
                raise validate.SchemaPolicyError(f"HOST_SCHEMA {ref}: a reference is {validate.LOCAL_REF}<name>, its name read "
                                                 "as written (validate.local_ref_name)")
            if name not in defs:
                raise validate.SchemaPolicyError(f"HOST_SCHEMA {ref}: the reference names no entry of $defs")
            if name in seen:
                raise validate.SchemaPolicyError(f"HOST_SCHEMA {ref}: the reference reaches itself")
            return inline(defs[name], seen | {name})
        out = {}
        for key, value in node.items():
            if key in SUBSCHEMA_MAPS and isinstance(value, dict):
                out[key] = {name: inline(sub, seen) for name, sub in value.items()}
            elif key in SUBSCHEMAS:
                out[key] = inline(value, seen)
            else:
                out[key] = value
        return out
    return inline({key: value for key, value in schema.items() if key not in ("$schema", "$defs")}, frozenset())


# The keywords a schema handed to a host may hold (WP-08c): of those the distill schemas use, the ones Claude Code's
# `--json-schema` check (Ajv 8's draft-07 class, as Claude Code 2.1.317 configures it) and the policy's draft 2020-12
# reading read alike. Measured offline with Ajv 8.20.0 (record 2026-11-06T0055--3809707): each of these compiles; a
# 2019-09 or 2020-12 keyword (dependentRequired, dependentSchemas, prefixItems, unevaluatedProperties) is refused as
# unknown. `$defs`, `$ref` and `$schema` are not here because the handed form has none (`host_schema`), and `items` is
# here as one schema only: as a list, draft-07 reads a tuple and 2020-12 refuses the schema.
HOST_KEYWORDS = frozenset({"$comment", "title", "type", "properties", "patternProperties", "additionalProperties",
                           "required", "items", "enum", "const", "pattern", "minLength", "minimum", "minItems", "maxItems",
                           "uniqueItems", "minProperties"})
# keywords whose value is a map of names to schemas, or one schema; every other keyword's value is data
SUBSCHEMA_MAPS, SUBSCHEMAS = ("properties", "patternProperties"), ("items", "additionalProperties")


def host_keywords(schema, at="#"):
    """`[(pointer, keyword)]` of what a schema handed to a host must not hold: every keyword outside HOST_KEYWORDS, and
    `items` as a list. Walked by the schema's structure, so a property named `items` or `required` under `properties` is
    a name, not a keyword, and an `enum` or `const` value is data."""
    out = []
    if not isinstance(schema, dict):
        return out
    for key, value in schema.items():
        if key not in HOST_KEYWORDS or (key == "items" and isinstance(value, list)):
            out.append((at, key))
            continue
        if key in SUBSCHEMA_MAPS and isinstance(value, dict):
            for name, sub in value.items():
                out += host_keywords(sub, f"{at}/{key}/{name}")
        elif key in SUBSCHEMAS:
            out += host_keywords(value, f"{at}/{key}")
    return out


def schema_bytes(schema):
    """The bytes `schema.json` holds, which are the schema the host is handed (`host_schema`), as canonical JSON. The
    schema and its handed form are both compiled through the policy. The same bytes are what the packet's SCHEMA hash
    names and the receipt hashes, so the gate binds one schema from the driver to the host."""
    validate.compile_schema(schema)
    sent = host_schema(schema)
    validate.compile_schema(sent)
    unread = host_keywords(sent)
    if unread:
        raise validate.SchemaPolicyError("HOST_SCHEMA_KEYWORD " + "; ".join(f"{key} at {at}" for at, key in unread)
                                         + ": the host's draft-07 check refuses it, or reads it otherwise than the "
                                           "policy's 2020-12 reading (HOST_KEYWORDS)")
    return (json.dumps(sent, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


# What each host is handed for a call's answer (D7, 2026-11-12). Claude Code reads schema.json itself: its
# `--json-schema` check is the draft-07 reading HOST_KEYWORDS was measured for. Codex hands its `--output-schema` to
# OpenAI's strict structured output, which takes a subset of JSON Schema, and the first live Codex judge call was
# refused by the provider before it generated anything (`invalid_json_schema`, status 400). So a Codex call's host
# receives a projection of schema.json made here by code (`provider_schema`); the gate still validates the answer
# against schema.json and holds the projection to this function, so nothing the projection leaves out goes unchecked.
PROVIDER_DIALECTS = {"claude": None, "codex": "openai-strict"}
# The strict subset, from the provider's Structured Outputs guide ("Supported schemas", read 2026-11-12 through its
# documentation index): the supported types; the keywords it lists per type; `additionalProperties: false` on every
# object and every property in `required`; the root an object and not `anyOf`; each `anyOf` branch a schema of the
# subset; definitions by `$defs`; and its limits. `description` is the one annotation its examples carry. A keyword
# the guide lists for no type is refused, the composition keywords it names as unsupported among them.
STRICT_TYPES = frozenset({"string", "number", "boolean", "integer", "object", "array", "null"})
STRICT_COMMON = frozenset({"type", "description", "enum", "const", "anyOf", "$ref"})
_STRICT_NUMBER = frozenset({"multipleOf", "maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum"})
STRICT_BY_TYPE = {"string": frozenset({"pattern", "format"}), "number": _STRICT_NUMBER, "integer": _STRICT_NUMBER,
                  "array": frozenset({"items", "minItems", "maxItems"}),
                  "object": frozenset({"properties", "required", "additionalProperties"}),
                  "boolean": frozenset(), "null": frozenset()}
STRICT_FORMATS = frozenset({"date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"})
STRICT_LIMITS = {"properties": 5000, "depth": 10, "enum_values": 1000, "string_chars": 120_000,
                 "large_enum": 250, "large_enum_chars": 15_000}
# A pattern's syntax beyond what the guide shows is not assumed: its examples anchor with `^` and `$`, and it names no
# regular-expression dialect, so a lookaround or a backreference is refused rather than sent.
STRICT_PATTERN_UNESTABLISHED = re.compile(r"\(\?(?:=|!|<=|<!)|\\[1-9]|\\k<")
# What the projection leaves out: the annotations the subset does not list, and the constraints it does not support,
# which the gate still checks against schema.json.
STRICT_DROPPED = ("$comment", "title", "minLength", "maxLength", "uniqueItems")
# The policy's end of input: a pattern ending in it ends there, which the host reads as `$` (no multiline flag).
END_OF_INPUT = "(?![\\s\\S])"


def strict_problems(schema):
    """What makes `schema` fall outside the strict subset (STRICT_*), each line naming its JSON pointer; empty when
    nothing does. Walked by the schema's structure: names under `properties` and `$defs` are names, and an `enum` or
    `const` value is data."""
    problems, totals = [], {"properties": 0, "enum_values": 0, "string_chars": 0}
    if not isinstance(schema, dict) or schema.get("type") != "object" or "anyOf" in schema:
        problems.append("STRICT_ROOT at #: the root is an object schema, and not anyOf")

    def walk(node, at, depth):
        if not isinstance(node, dict):
            problems.append(f"STRICT_SCHEMA_SHAPE at {at}: a schema of the subset is an object")
            return
        if depth > STRICT_LIMITS["depth"]:
            problems.append(f"STRICT_DEPTH at {at}: more than {STRICT_LIMITS['depth']} levels of nesting")
        declared = node.get("type")
        types = [declared] if isinstance(declared, str) else declared if isinstance(declared, list) else []
        if declared is None and not {"anyOf", "$ref", "enum", "const"} & set(node):
            problems.append(f"STRICT_TYPE_MISSING at {at}: a schema names its type")
        for t in types:
            if t not in STRICT_TYPES:
                problems.append(f"STRICT_TYPE_UNSUPPORTED {t!r} at {at}")
        allowed = set(STRICT_COMMON) | ({"$defs"} if at == "#" else set())
        for t in types:
            allowed |= STRICT_BY_TYPE.get(t, frozenset())
        for key in node:
            if key not in allowed:
                problems.append(f"STRICT_KEYWORD_UNSUPPORTED {key} at {at}")
        if "format" in node and node["format"] not in STRICT_FORMATS:
            problems.append(f"STRICT_FORMAT_UNSUPPORTED {node['format']!r} at {at}")
        if isinstance(node.get("pattern"), str) and STRICT_PATTERN_UNESTABLISHED.search(node["pattern"]):
            problems.append(f"STRICT_PATTERN_UNESTABLISHED at {at}: a lookaround or a backreference")
        if "object" in types:
            props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            if node.get("additionalProperties") is not False:
                problems.append(f"STRICT_ADDITIONAL_PROPERTIES at {at}: every object sets additionalProperties false")
            required = node.get("required") if isinstance(node.get("required"), list) else []
            optional = [name for name in props if name not in required]
            if optional:
                problems.append(f"STRICT_OPTIONAL_PROPERTY at {at}: {optional} not required; the subset requires every "
                                "property, and a nullable stand-in would let the host answer null where schema.json "
                                "refuses it")
            unknown = [name for name in required if name not in props]
            if unknown:
                problems.append(f"STRICT_REQUIRED_UNKNOWN at {at}: {unknown} required and not properties")
            totals["properties"] += len(props)
            totals["string_chars"] += sum(len(name) for name in props)
            for name, sub in props.items():
                walk(sub, f"{at}/properties/{name}", depth + 1)
        if "array" in types and "items" in node:
            walk(node["items"], f"{at}/items", depth + 1)
        for n, sub in enumerate(node.get("anyOf") if isinstance(node.get("anyOf"), list) else []):
            walk(sub, f"{at}/anyOf/{n}", depth)
        if isinstance(node.get("enum"), list):
            values = node["enum"]
            chars = sum(len(v) for v in values if isinstance(v, str))
            totals["enum_values"] += len(values)
            totals["string_chars"] += chars
            if len(values) > STRICT_LIMITS["large_enum"] and chars > STRICT_LIMITS["large_enum_chars"]:
                problems.append(f"STRICT_ENUM_SIZE at {at}: {len(values)} values, {chars} characters")
        if isinstance(node.get("const"), str):
            totals["string_chars"] += len(node["const"])
        for name, sub in (node.get("$defs") if isinstance(node.get("$defs"), dict) else {}).items():
            totals["string_chars"] += len(name)
            walk(sub, f"{at}/$defs/{name}", depth)
    if isinstance(schema, dict):
        walk(schema, "#", 1)
    for key, limit in (("properties", "properties"), ("enum_values", "enum_values"), ("string_chars", "string_chars")):
        if totals[key] > STRICT_LIMITS[limit]:
            problems.append(f"STRICT_LIMIT {key} at #: {totals[key]} over {STRICT_LIMITS[limit]}")
    return problems


def provider_schema(handed, host):
    """`(projection, problems)`: what `host` is handed for a schema whose handed form (schema.json's content) is
    `handed`. A host whose dialect reads schema.json itself gets None, and nothing is projected; for the strict
    dialect the projection leaves out STRICT_DROPPED and ends a pattern ending at END_OF_INPUT with `$`, and its
    problems are `strict_problems` of the result. Nothing is made optional, nullable or open that schema.json closes:
    a schema the subset cannot hold is refused by name, never sent weakened."""
    if host not in PROVIDER_DIALECTS:
        return None, [f"PROVIDER_DIALECT_UNKNOWN {host!r}: no dialect is declared for it"]
    if PROVIDER_DIALECTS[host] is None:
        return None, []

    def project(node):
        if not isinstance(node, dict):
            return node
        out = {}
        for key, value in node.items():
            if key in STRICT_DROPPED:
                continue
            if key == "pattern" and isinstance(value, str) and value.endswith(END_OF_INPUT):
                head = value[:-len(END_OF_INPUT)]
                escaped = (len(head) - len(head.rstrip("\\"))) % 2  # an escaped "(" opens no lookahead
                out[key] = value if escaped else head + "$"
            elif key in ("properties", "$defs") and isinstance(value, dict):
                out[key] = {name: project(sub) for name, sub in value.items()}
            elif key == "items" and isinstance(value, dict):
                out[key] = project(value)
            elif key == "anyOf" and isinstance(value, list):
                out[key] = [project(sub) for sub in value]
            else:
                out[key] = value
        return out
    projected = project(handed)
    return projected, strict_problems(projected)


def provider_schema_bytes(schema_json, host):
    """The bytes `host` is handed beside schema.json (`schema_json`, its bytes), as canonical JSON, or None when the
    host reads schema.json itself. A projection outside the dialect raises SchemaPolicyError naming every problem."""
    projected, problems = provider_schema(json.loads(schema_json), host)
    if problems:
        raise validate.SchemaPolicyError("SCHEMA_UNPROJECTABLE " + "; ".join(problems))
    if projected is None:
        return None
    return (json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def build(call_id, stage, seat, payload, schema=None, repo=REPO):
    """The packet's bytes. `schema` is the bytes of `schema.json`, or None for a schema-less call."""
    block = principles_block(repo)
    reference = f"sha256:{sha256_bytes(schema)}" if schema is not None else "none"
    header = (f"CALL-ID: {call_id}\nSTAGE: {stage}\nSEAT: {seat}\nSCHEMA: {reference}\n"
              f"PRINCIPLES: sha256:{sha256_bytes(block.encode('utf-8'))}\n\n")
    return (header + block + PAYLOAD_MARKER + "\n" + payload).encode("utf-8")


def template_text(name, template_dir=TEMPLATE_DIR):
    try:
        return (pathlib.Path(template_dir) / f"{name}.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateError(f"TEMPLATE_UNAVAILABLE {name}: {exc}") from exc


def template_fields(name, template_dir=TEMPLATE_DIR):
    """The placeholders of one template, sorted."""
    return sorted(set(PLACEHOLDER.findall(template_text(name, template_dir))))


def render(name, fields, template_dir=TEMPLATE_DIR):
    """The payload of template `name` with every placeholder replaced by its field's text, in one pass."""
    text = template_text(name, template_dir)
    wanted = set(PLACEHOLDER.findall(text))
    missing, extra = sorted(wanted - set(fields)), sorted(set(fields) - wanted)
    if missing or extra or not all(isinstance(v, str) for v in fields.values()):
        raise TemplateError(f"TEMPLATE_FIELDS_MISMATCH {name}: missing={missing} extra={extra}; every placeholder "
                            "takes exactly one text field")
    return PLACEHOLDER.sub(lambda m: fields[m.group(1)], text)


def split(packet):
    """(envelope text, payload bytes) at the first marker line, or (whole text, None)."""
    marker = ("\n" + PAYLOAD_MARKER + "\n").encode("utf-8")
    at = packet.find(marker)
    if at < 0:
        return packet.decode("utf-8", "replace"), None
    return packet[:at + 1].decode("utf-8", "replace"), packet[at + len(marker):]


def payload_sha256(packet):
    """The hash of the payload alone; of the whole packet when it carries no marker."""
    payload = split(packet)[1]
    return sha256_bytes(packet if payload is None else payload)


def check(packet, call_id, schema=None, repo=REPO):
    """Every reason `packet` may not be dispatched for `call_id` with `schema` (bytes or None)."""
    errors = []
    envelope, payload = split(packet)
    lines = envelope.splitlines()
    if not lines or lines[0] != f"CALL-ID: {call_id}":
        errors.append(f"CALL_ID_MISSING: the packet's first line is not 'CALL-ID: {call_id}'")
    header = dict(line.split(": ", 1) for line in lines[1:5] if ": " in line)
    block = principles_block(repo)
    if header.get("PRINCIPLES") != f"sha256:{sha256_bytes(block.encode('utf-8'))}" or block not in envelope:
        errors.append("PRINCIPLES_MISSING: the packet does not carry the current principles block and its hash (plan P9)")
    want = f"sha256:{sha256_bytes(schema)}" if schema is not None else "none"
    if header.get("SCHEMA") != want:
        errors.append(f"SCHEMA_REFERENCE_MISSING: the envelope's schema reference is {header.get('SCHEMA')!r}, "
                      f"the call's schema is {want}")
    if not payload:
        errors.append(f"PAYLOAD_MISSING: no payload after a '{PAYLOAD_MARKER}' line")
    return errors


def self_test():
    import tempfile
    failures, ran = [], []

    def control(name, errors, *needles):
        ran.append(name)
        if not needles and errors:
            failures.append(f"{name}: expected no violation, got {errors}")
        for needle in needles:
            if not any(needle in line for line in errors):
                failures.append(f"{name}: expected {needle!r} in {errors}")

    conforming = {"type": "object", "additionalProperties": False, "required": ["answer"],
                  "properties": {"answer": {"type": "string"}}}
    # the product refusing a conforming schema fails this control by its name, never as a traceback that would hide
    # every control after it (WP-08c); the envelope controls below then run on the schema's bytes as written
    try:
        schema, refusal = schema_bytes(conforming), []
    except validate.SchemaPolicyError as exc:
        schema = (json.dumps(conforming, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        refusal = [f"refused: {str(exc)[:200]}"]
    control("schema-builder-takes-a-conforming-schema", refusal)
    payload = "Judge the candidate below.\n{\"candidate\": \"c1\"}\n"
    good = build("r1-S6-c1-a1", "S6", "claude:claude-opus-5-5/high", payload, schema)
    control("conforming-packet", check(good, "r1-S6-c1-a1", schema))  # the positive control, first
    other = build("r1-S6-c1-a2", "S6", "codex:gpt-6-astra/xhigh", payload, schema)
    control("payload-hash-shared-packet-hash-unique",
            [] if payload_sha256(good) == payload_sha256(other) == sha256_bytes(payload.encode())
            and sha256_bytes(good) != sha256_bytes(other) else ["two calls of one judgment did not share only the payload hash"])
    schemaless = build("r1-S8-e1-a1", "S8", "claude:claude-sonnet-5-5/xhigh", payload)
    control("schema-less-packet-says-none", check(schemaless, "r1-S8-e1-a1"))

    block = principles_block()
    control("block-carries-all-five-summaries",
            [] if all(f"## {title} ({guide})\n" in block for title, guide, _ in PRINCIPLE_SOURCES)
            and len(PRINCIPLE_SOURCES) == 5 else ["a principle summary is missing from the block"])
    control("block-is-taken-from-the-guides",
            [] if "one value has one owner" in block and "1. High-level design:" in block
            and "mocks are verification realizations" in block else ["the block is not the guides' own text"])

    control("no-principles-block", check(good.replace(block.encode(), b""), "r1-S6-c1-a1", schema),
            "PRINCIPLES_MISSING")
    control("principles-text-altered", check(good.replace(b"one value has one owner", b"one value, many owners"),
                                             "r1-S6-c1-a1", schema), "PRINCIPLES_MISSING")
    stale = good.replace(f"PRINCIPLES: sha256:{sha256_bytes(block.encode())}".encode(), b"PRINCIPLES: sha256:" + b"0" * 64)
    control("principles-hash-stale", check(stale, "r1-S6-c1-a1", schema), "PRINCIPLES_MISSING")
    control("no-schema-reference", check(good.replace(b"SCHEMA: sha256:", b"SCHEMAX: sha256:"), "r1-S6-c1-a1", schema),
            "SCHEMA_REFERENCE_MISSING")
    control("schema-reference-names-another-schema", check(good, "r1-S6-c1-a1", schema + b" "),
            "SCHEMA_REFERENCE_MISSING")
    control("schema-given-to-a-schema-less-packet", check(schemaless, "r1-S8-e1-a1", schema),
            "SCHEMA_REFERENCE_MISSING")
    control("another-call-id", check(good, "r1-S6-c1-a9", schema), "CALL_ID_MISSING")
    control("no-payload", check(split(good)[0].encode(), "r1-S6-c1-a1", schema), "PAYLOAD_MISSING")
    control("no-marker-hashes-the-whole-packet",
            [] if payload_sha256(b"plain text\n") == sha256_bytes(b"plain text\n") else ["payload of an unmarked packet"])

    def raised(action, error_type, needle):
        try:
            action()
        except error_type as exc:
            return [] if needle in str(exc) else [f"refused without {needle!r}: {exc}"]
        except Exception as exc:
            return [f"raised {exc!r}"]
        return [f"not refused (expected {needle})"]

    control("schema-builder-refuses-an-open-schema",
            raised(lambda: schema_bytes({"type": "object", "properties": {}}), validate.SchemaPolicyError, "open object"))
    # WP-08c: the form a host is handed holds only keywords its draft-07 check and the policy's 2020-12 reading read
    # alike - walked by structure, so a property named like a keyword is a name, and checked on the handed form
    named_like = {"type": "object", "additionalProperties": False, "required": ["items"],
                  "properties": {"items": {"type": "string"}, "required": {"type": "string"},
                                 "dependentRequired": {"type": "string", "enum": ["prefixItems"]}}}
    def handed_keywords(held):
        try:
            return host_keywords(json.loads(schema_bytes(held)))
        except (validate.SchemaPolicyError, ValueError) as exc:
            return [("refused", str(exc)[:120])]
    control("host-schema-takes-properties-named-like-keywords",
            [f"{handed_keywords(named_like)}"] if handed_keywords(named_like) else [])
    planted = {"type": "object", "additionalProperties": False, "required": ["a"],
               "properties": {"a": {"type": "string"}, "b": {"type": "array", "items": {"type": "string"}}},
               "dependentRequired": {"a": ["b"]}}
    control("host-schema-refuses-a-2019-keyword-by-name",
            raised(lambda: schema_bytes(planted), validate.SchemaPolicyError, "HOST_SCHEMA_KEYWORD dependentRequired at #"))
    deep = {"type": "object", "properties": {"b": {"type": "array", "items": {"type": "object", "unevaluatedProperties": False}}}}
    control("host-keywords-name-each-unread-keyword-where-it-stands",
            [] if (host_keywords(deep), host_keywords({"type": "array", "items": [{"type": "string"}]}),
                   host_keywords({"$schema": "x", "$defs": {"s": {"type": "string"}}, "properties": {"a": {"$ref": "#/$defs/s"}}}))
            == ([("#/properties/b/items", "unevaluatedProperties")], [("#", "items")],
                [("#", "$schema"), ("#", "$defs"), ("#/properties/a", "$ref")]) else ["walked otherwise"])
    # the schema a host is handed (WP-08 commit 7, dw2-live1), asked of the schemas S3 hands a host, each of which names
    # the 2020-12 meta-schema and holds references: no meta-schema, no reference and no $defs in the bytes, which the
    # policy still compiles; and the inlined form is derived from the schema itself, so a change to an entry of its
    # $defs shows at every place a reference reached it
    host_bound = {}
    for name in TEMPLATES:
        try:
            held = json.loads((pathlib.Path(__file__).resolve().parents[1] / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
            sent_text = schema_bytes(held).decode("utf-8")
            validate.compile_schema(json.loads(sent_text))
            host_bound[name] = (held, sent_text)
        except Exception as exc:  # noqa: BLE001 - whatever stops a schema here is reported by name
            failures.append(f"positive control: the {name} schema did not load or compile: {exc}")
    control("host-schema-names-no-meta-schema-and-no-reference",
            [] if sorted(host_bound) == sorted(TEMPLATES) and all(
                "$schema" in held and held.get("$defs") and '"$ref"' in json.dumps(held)
                and not any(key in sent for key in ('"$schema"', '"$defs"', '"$ref"')) for held, sent in host_bound.values())
            else [f"a handed schema still names a meta-schema or a reference: "
                  f"{[n for n, (_h, s) in host_bound.items() if any(k in s for k in ('$schema', '$defs', '$ref'))]}"])

    def reached(schema, node=None, seen=frozenset()):
        """How many times each $defs entry is reached from the schema's root, following references through entries."""
        node = {k: v for k, v in schema.items() if k != "$defs"} if node is None else node
        counts = {}
        for value in (node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()):
            if isinstance(value, dict) and "$ref" in value:
                name = value["$ref"][len("#/$defs/"):]
                counts[name] = counts.get(name, 0) + 1
                for inner, n in reached(schema, schema["$defs"][name], seen | {name}).items():
                    counts[inner] = counts.get(inner, 0) + n
            elif isinstance(value, (dict, list)):
                for inner, n in reached(schema, value, seen).items():
                    counts[inner] = counts.get(inner, 0) + n
        return counts
    followed = {}
    for name, (held, sent_text) in host_bound.items():
        marked = json.loads(json.dumps(held))
        for entry, sub in marked["$defs"].items():
            sub["$comment"] = f"FOLLOWS-{name}-{entry}"
        made, problem = None, None
        try:
            made = schema_bytes(marked).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - reported by the control below
            problem = str(exc)
        expected = reached(held)
        followed[name] = (made is not None and made != sent_text and bool(expected) and all(
            made.count(f'"FOLLOWS-{name}-{entry}"') == expected.get(entry, 0) for entry in held["$defs"]), problem)
    control("host-schema-follows-a-change-to-its-defs",
            [] if sorted(followed) == sorted(TEMPLATES) and all(ok for ok, _t in followed.values())
            else [f"a handed schema did not follow its $defs: {followed}"])
    control("host-schema-refuses-a-reference-it-cannot-inline",
            raised(lambda: host_schema({"type": "object", "additionalProperties": False, "$defs": {"a": {"type": "string"}},
                                        "properties": {"x": {"$ref": "#/$defs/a", "title": "beside"}}}),
                   validate.SchemaPolicyError, "HOST_SCHEMA #/$defs/a: a $ref beside"))
    control("host-schema-refuses-a-reference-that-reaches-itself",
            raised(lambda: host_schema({"type": "object", "additionalProperties": False,
                                        "$defs": {"a": {"type": "object", "additionalProperties": False,
                                                        "properties": {"next": {"$ref": "#/$defs/a"}}}},
                                        "properties": {"x": {"$ref": "#/$defs/a"}}}),
                   validate.SchemaPolicyError, "HOST_SCHEMA #/$defs/a: the reference reaches itself"))
    control("host-schema-refuses-a-reference-to-no-entry",
            raised(lambda: host_schema({"type": "object", "additionalProperties": False, "$defs": {"a": {"type": "string"}},
                                        "properties": {"x": {"$ref": "#/$defs/b"}}}),
                   validate.SchemaPolicyError, "HOST_SCHEMA #/$defs/b: the reference names no entry of $defs"))
    # WP-08c (W r2): a reference's name holding a JSON Pointer or URI escape is refused before a host is handed it - by
    # the policy's lint where schema_bytes compiles it, and by host_schema itself when called alone - so the escaped
    # name "a~1b" never reaches a host as the literal entry while jsonschema resolves it as "a/b"
    escaped_names = {"type": "object", "additionalProperties": False, "required": ["x"],
                     "$defs": {"a/b": {"type": "integer"}, "a~1b": {"type": "string"}},
                     "properties": {"x": {"$ref": "#/$defs/a~1b"}}}
    control("schema-builder-refuses-an-escaped-reference-name",
            raised(lambda: schema_bytes(escaped_names), validate.SchemaPolicyError, "as #/$defs/<name>, the name of letters")
            + [line for name in ("a~0b", "a%2Fb") for line in raised(
                lambda name=name: schema_bytes({"type": "object", "additionalProperties": False, "required": ["x"],
                                                "$defs": {name: {"type": "string"}},
                                                "properties": {"x": {"$ref": f"#/$defs/{name}"}}}),
                validate.SchemaPolicyError, "as #/$defs/<name>, the name of letters")])
    control("host-schema-refuses-an-escaped-reference-name",
            raised(lambda: host_schema(escaped_names), validate.SchemaPolicyError,
                   "HOST_SCHEMA #/$defs/a~1b: a reference is #/$defs/<name>"))
    # WP-08c (X and W r1): the handed form is made by walking the schema's structure, so a literal {"$ref": ...} that an
    # enum, a const, a default or an example holds is data, and a property named $ref is a name; and the schema as
    # written and the form a host is handed accept and refuse the same answers, for those and for every schema a host
    # is handed now (read, stitch, and the judge's verdict as dispatch hands it)
    kept_as_data = None
    try:
        kept_as_data = host_schema({"type": "object", "additionalProperties": False, "$defs": {"s": {"type": "string"}},
                                    "properties": {"a": {"type": "object", "default": {"$ref": "#/$defs/s"},
                                                         "examples": [{"$ref": "#/$defs/s"}]},
                                                   "$ref": {"$ref": "#/$defs/s"}}})
    except Exception as exc:  # noqa: BLE001 - whatever stops it is reported by the control's name
        kept_as_data = f"raised {type(exc).__name__}: {exc}"
    control("host-schema-keeps-data-and-names-as-written",
            [] if kept_as_data == {"type": "object", "additionalProperties": False,
                                   "properties": {"a": {"type": "object", "default": {"$ref": "#/$defs/s"},
                                                        "examples": [{"$ref": "#/$defs/s"}]},
                                                  "$ref": {"type": "string"}}} else [f"made {kept_as_data}"])

    def judged_alike(held, answers):
        """`(problem, [(answer, as written, as handed)])`: each answer judged by the schema and by its handed form."""
        try:
            written, handed = validate.compile_schema(held), validate.compile_schema(json.loads(schema_bytes(held)))
        except Exception as exc:  # noqa: BLE001 - a refused or broken schema fails the control by its name
            return f"refused: {type(exc).__name__}: {str(exc)[:160]}", []
        return None, [(json.dumps(a, sort_keys=True), written.is_valid(a), handed.is_valid(a)) for a in answers]
    schemas_dir = pathlib.Path(__file__).resolve().parents[1] / "schemas"
    def held_schema(name):
        return json.loads((schemas_dir / f"{name}.schema.json").read_text(encoding="utf-8"))
    quote = {"quote_id": "q1", "entry": "e1", "text": "x"}
    empty_read = {"quotes": [], "claims": [], "events": [], "decisions": [], "observations": []}
    resolved = {"event_id": "v1", "outcome": "resolved", "claim_ids": ["c1"], "evidence_ids": ["q1"]}
    alike = {
        "a literal $ref in an enum and a const": (
            {"type": "object", "additionalProperties": False, "required": ["payload", "word"], "$defs": {"s": {"type": "string"}},
             "properties": {"payload": {"enum": [{"$ref": "#/$defs/s"}, "plain"]}, "pinned": {"const": {"$ref": "#/$defs/s"}},
                            "word": {"$ref": "#/$defs/s"}}},
            [{"payload": {"$ref": "#/$defs/s"}, "word": "w"}, {"payload": {"type": "string"}, "word": "w"},
             {"payload": "plain", "word": "w", "pinned": {"$ref": "#/$defs/s"}},
             {"payload": "plain", "word": "w", "pinned": {"type": "string"}}, {"payload": "plain", "word": 3}]),
        "a property named $ref": (
            {"type": "object", "additionalProperties": False, "required": ["$ref"], "$defs": {"n": {"type": "integer"}},
             "properties": {"$ref": {"type": "string"}, "count": {"$ref": "#/$defs/n"}}},
            [{"$ref": "a"}, {"$ref": "a", "count": 2}, {"$ref": 1}, {"$ref": "a", "count": "2"}, {}]),
        "read": (held_schema("read"),
                 [empty_read, {**empty_read, "quotes": [quote]}, {**empty_read, "quotes": [{**quote, "quote_id": "q1\n"}]},
                  {**empty_read, "quotes": [{**quote, "entry": "3/message/content"}]},
                  {k: v for k, v in empty_read.items() if k != "observations"}, {**empty_read, "extra": []}]),
        "stitch": (held_schema("stitch"),
                   [{"resolutions": []}, {"resolutions": [resolved]}, {"resolutions": [{**resolved, "outcome": "maybe"}]},
                    {"resolutions": [{**resolved, "claim_ids": ["c1\n"]}]}, {}]),
        "verdict": ({"type": "object", "additionalProperties": False, "required": ["verdict", "why"],
                     "properties": {"verdict": {"enum": ["PRESENT", "ABSENT", "UNCLEAR"]}, "why": {"type": "string"}}},
                    [{"verdict": "ABSENT", "why": "x"}, {"verdict": "NO", "why": "x"}, {"verdict": "ABSENT"}]),
    }
    verdicts = {name: judged_alike(held, answers) for name, (held, answers) in alike.items()}
    control("host-schema-judges-every-answer-as-the-schema-does",
            [f"{name}: {problem or [r for r in rows if r[1] != r[2]] or 'no answer accepted, or none refused'}"
             for name, (problem, rows) in verdicts.items()
             if problem or any(r[1] != r[2] for r in rows) or {r[1] for r in rows} != {True, False}])
    with tempfile.TemporaryDirectory() as td:
        for _title, guide, _part in PRINCIPLE_SOURCES:
            target = pathlib.Path(td) / guide
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((REPO / guide).read_text(encoding="utf-8"), encoding="utf-8")
        control("copied-guides-give-the-same-block", [] if principles_block(td) == block else ["block differs"])
        staged = pathlib.Path(td) / "claude/guides/coding-staged-workflow.md"
        staged.write_text(staged.read_text(encoding="utf-8").replace("## Stages", "## Phases"), encoding="utf-8")
        control("guide-without-its-section", raised(lambda: principles_block(td), Unavailable,
                                                    "PRINCIPLES_UNAVAILABLE claude/guides/coding-staged-workflow.md"))
        concept = pathlib.Path(td) / "claude/guides/concept-economy.md"
        concept.write_text(concept.read_text(encoding="utf-8").replace("core_rules:", "other_rules:"), encoding="utf-8")
        control("guide-without-core-rules", raised(lambda: summary(concept.read_text(encoding="utf-8"), "core_rules",
                                                                   "concept-economy.md"), Unavailable,
                                                   "PRINCIPLES_UNAVAILABLE concept-economy.md"))
        (pathlib.Path(td) / "claude/guides/verification-discipline.md").unlink()
        control("guide-missing", raised(lambda: principles_block(td), Unavailable,
                                        "PRINCIPLES_UNAVAILABLE claude/guides/verification-discipline.md"))
        control("template-missing", raised(lambda: render("read", {}, template_dir=td), TemplateError,
                                           "TEMPLATE_UNAVAILABLE read"))

    # S3's two templates (plan WP-08): each takes exactly the fields its stage fills, the packet it makes passes the
    # linter, and the part every call of it carries - envelope, principles, template, schema - leaves room in the
    # overhead the windows were cut with for what the call adds (its omissions and expected observations). The room
    # is reported, not judged: what one call adds is counted with the call, by the dispatcher's bound check.
    from runlib import bound
    schemas = pathlib.Path(__file__).resolve().parents[1] / "schemas"
    filled_by = {"read": ["expected", "omissions", "window"], "stitch": ["claims", "events"],
                 "form": ["claims", "clusters", "events"], "judge": ["candidate", "claims", "context", "entries", "units"],
                 "sweep": ["candidates", "inventory", "units"], "cross_review": ["candidate", "units"],
                 "reconsider": ["candidate", "claims", "context", "units"]}
    room = {}
    for name in TEMPLATES:
        try:
            fields = template_fields(name)
            answer = schema_bytes(json.loads((schemas / f"{name}.schema.json").read_text(encoding="utf-8")))
        except (TemplateError, OSError, ValueError, validate.SchemaPolicyError) as exc:
            failures.extend(f"{name}-{what}: not run (the {name} template or schema did not load: {str(exc)[:160]})"
                            for what in ("template-takes-the-fields-its-stage-fills", "packet-passes-the-linter",
                                         "fixed-part-fits-the-overhead"))
            continue
        control(f"{name}-template-takes-the-fields-its-stage-fills",
                [] if fields == filled_by[name] else [f"placeholders {fields}, filled {filled_by[name]}"])
        call = f"r1-S3-{name}-a1"
        made = build(call, "S3", "claude:claude-sonnet-5-5/high", render(name, {f: f"<{f}>" for f in fields}), answer)
        control(f"{name}-packet-passes-the-linter", check(made, call, answer))
        if name not in WINDOW_TEMPLATES:
            continue  # S4's packet is bounded by its own stage (plan WP-09), not by the overhead S3's windows were cut with
        fixed = len(build(call, "S3", "claude:claude-sonnet-5-5/high", render(name, {f: "" for f in fields}), answer)) \
            + len(answer)
        room[name] = bound.PACKET_OVERHEAD - fixed
        control(f"{name}-fixed-part-fits-the-overhead",
                [] if room[name] > 0 else [f"{fixed} fixed bytes, overhead {bound.PACKET_OVERHEAD}"])
    control("template-field-missing", raised(lambda: render("read", {"window": "w", "omissions": "o"}), TemplateError,
                                             "TEMPLATE_FIELDS_MISMATCH read: missing=['expected']"))
    control("template-field-extra", raised(lambda: render("stitch", {"events": "e", "claims": "c", "window": "w"}),
                                           TemplateError, "TEMPLATE_FIELDS_MISMATCH stitch: missing=[] extra=['window']"))
    control("template-field-not-text", raised(lambda: render("stitch", {"events": "e", "claims": 3}), TemplateError,
                                              "TEMPLATE_FIELDS_MISMATCH stitch"))
    # a template that no longer takes these fields fails this control by its name, never as a traceback that would
    # hide every failure recorded before it
    try:
        once = render("read", {"window": "a record quoting {{omissions}}", "omissions": "ONLY-HERE", "expected": "none"})
        expanded = [] if "a record quoting {{omissions}}" in once and once.count("ONLY-HERE") == 1 else ["a field was expanded"]
    except TemplateError as exc:
        expanded = [f"RAISED {exc}"]
    control("a-field-is-never-read-as-a-template", expanded)

    # D7: every schema a Codex seat can be sent projects into the strict subset. The stages are the ones seats.json
    # gives a Codex seat, and the schemas each sends are the ones its own module builds, so a Codex seat added to
    # another stage fails this control until that stage's schemas are named here.
    try:
        from runlib import stage_judge as sj, stage_review_korean as s9b, stage_review_proposals as s7b
        sent_by = {"S6": {"judge": sj.schema, "sweep": sj.sweep_schema, "cross_review": sj.cross_schema,
                          "reconsider": sj.reconsider_schema},
                   "S7b": {"s7b": lambda: json.loads(s7b.schema_bytes())},
                   "S9b": {"s9b": lambda: json.loads(s9b.schema_bytes())}}
        seats_doc = json.loads((REPO / "session-distill" / "seats.json").read_text(encoding="utf-8"))
        codex_stages = {stage for stage, held in seats_doc["stage_seats"].items()
                        if not stage.startswith("$") and any(str(seat).startswith("codex:") for seat in held)}
        handed = {name: json.loads(schema_bytes(make())) for stage in sent_by for name, make in sent_by[stage].items()}
        found = {name: provider_schema(held, "codex") for name, held in handed.items()}
        reached = []
    except Exception as exc:  # noqa: BLE001 - a module that no longer builds its schema fails the control by name
        codex_stages, handed, found, reached = set(), {}, {}, [f"RAISED {type(exc).__name__}: {str(exc)[:160]}"]
    # S7b's contract leaves five properties optional, which the subset cannot hold without letting the host answer
    # null where s7b.schema.json refuses it: its owner decides the contract (lane L, reported 2026-11-12), and until
    # then a Codex S7b call is refused before anything is sent. Named here by site, so the declaration lapses with them.
    unprojectable = {"s7b": {"#", "#/properties/alternative", "#/properties/alternative/properties/destination",
                             "#/properties/destination_review", "#/properties/disposition_review"}}
    wrong = list(reached)
    if codex_stages != set(sent_by) or not handed:
        wrong.append(f"the stages with a Codex seat are {sorted(codex_stages)}, the ones named here {sorted(sent_by)}")
    for name, (projected, problems) in sorted(found.items()):
        sites = {line.split(" at ", 1)[1].split(":", 1)[0] for line in problems if line.startswith("STRICT_OPTIONAL_PROPERTY")}
        expected = unprojectable.get(name, set())
        if projected is None or sites != expected or len(problems) != len(expected):
            wrong.append(f"{name}: {problems[:3]}")
    control("every-schema-a-codex-seat-can-be-sent-projects-into-the-strict-subset", wrong)

    # the projection weakens nothing schema.json closes: at every pointer the same types, properties, required,
    # additionalProperties, enum, const, items and bounds; only STRICT_DROPPED goes, and an end of input becomes `$`
    def weakened(full, sent, at):
        out = []
        if not isinstance(full, dict) or not isinstance(sent, dict):
            return [] if full == sent else [f"{at}: not the same schema"]
        for key in set(full) | set(sent):
            if key in STRICT_DROPPED:
                if key in sent:
                    out.append(f"{at}: {key} kept")
            elif key not in full or key not in sent:
                out.append(f"{at}: {key} only on one side")
            elif key in ("properties", "$defs"):
                if set(full[key]) != set(sent[key]):
                    out.append(f"{at}/{key}: other names")
                out += [line for name in full[key] for line in weakened(full[key][name], sent[key].get(name), f"{at}/{key}/{name}")]
            elif key == "items":
                out += weakened(full[key], sent[key], f"{at}/items")
            elif key == "anyOf":
                out += [line for n, (a, b) in enumerate(zip(full[key], sent[key])) for line in weakened(a, b, f"{at}/anyOf/{n}")]
                if len(full[key]) != len(sent[key]):
                    out.append(f"{at}/anyOf: another number of branches")
            elif key == "pattern":
                if sent[key] not in (full[key], full[key][:-len(END_OF_INPUT)] + "$" if full[key].endswith(END_OF_INPUT) else None):
                    out.append(f"{at}: pattern {sent[key]!r} is not {full[key]!r}")
            elif full[key] != sent[key]:
                out.append(f"{at}: {key} differs")
        return out
    control("the-projection-weakens-nothing-schema-json-closes",
            ([] if found else ["nothing projected"])
            + [f"{name} {line}" for name, (projected, _p) in sorted(found.items()) for line in weakened(handed[name], projected, "#")])

    # each strict rule refuses by name, each on a schema of its own (so none stops testing when a real schema changes)
    def closed(**props):
        return {"type": "object", "additionalProperties": False, "required": sorted(props), "properties": props}
    text = {"type": "string"}
    nested = text
    for _ in range(11):
        nested = closed(x=nested)
    planted = (
        ("a-planted-unsupported-keyword", closed(a={"type": "array", "items": text, "uniqueItems": True}),
         "STRICT_KEYWORD_UNSUPPORTED uniqueItems at #/properties/a"),
        ("a-planted-composition-keyword", closed(a={"allOf": [text], "type": "string"}),
         "STRICT_KEYWORD_UNSUPPORTED allOf at #/properties/a"),
        ("a-planted-open-object", {**closed(a=text), "additionalProperties": True}, "STRICT_ADDITIONAL_PROPERTIES at #"),
        ("a-planted-optional-property", {**closed(a=text, b=text), "required": ["a"]}, "STRICT_OPTIONAL_PROPERTY at #"),
        ("a-planted-anyof-root", {"anyOf": [closed(a=text)]}, "STRICT_ROOT at #"),
        ("a-planted-lookahead", closed(a={"type": "string", "pattern": "^(?=a)b$"}),
         "STRICT_PATTERN_UNESTABLISHED at #/properties/a"),
        ("a-planted-format", closed(a={"type": "string", "format": "uri"}), "STRICT_FORMAT_UNSUPPORTED 'uri' at #/properties/a"),
        ("a-planted-type", closed(a={"type": "tuple"}), "STRICT_TYPE_UNSUPPORTED 'tuple' at #/properties/a"),
        ("a-planted-depth", nested, "STRICT_DEPTH at #/properties/x/properties/x/properties/x/properties/x/properties/x/"
                                    "properties/x/properties/x/properties/x/properties/x/properties/x"),
        ("a-planted-property-count", closed(**{f"p{n}": text for n in range(5001)}), "STRICT_LIMIT properties at #"),
        ("a-planted-enum-count", closed(**{f"e{n}": {"type": "string", "enum": [f"v{m}" for m in range(11)]}
                                           for n in range(100)}), "STRICT_LIMIT enum_values at #"),
        ("a-planted-large-enum", closed(a={"type": "string", "enum": [f"{n:03d}" + "v" * 60 for n in range(251)]}),
         "STRICT_ENUM_SIZE at #/properties/a"))
    for name, schema, needle in planted:
        control(name, strict_problems(schema), needle)
    control("a-conforming-schema-is-in-the-subset", strict_problems(closed(a=text, b={"type": ["string", "null"]})))
    # the end of input becomes `$`, an escaped backslash before it included; Claude reads schema.json itself
    ended, _ = provider_schema(closed(a={"type": "string", "pattern": "^n[1-9][0-9]*" + END_OF_INPUT},
                                      b={"type": "string", "pattern": "^a\\\\" + END_OF_INPUT}), "codex")
    control("an-end-of-input-is-sent-as-dollar",
            [] if ended and ended["properties"]["a"]["pattern"] == "^n[1-9][0-9]*$"
            and ended["properties"]["b"]["pattern"] == "^a\\\\$" else [f"{ended}"])
    control("claude-reads-schema-json-itself", [] if provider_schema(closed(a=text), "claude") == (None, []) else ["projected"])
    control("an-undeclared-host-has-no-dialect", provider_schema(closed(a=text), "gemini")[1], "PROVIDER_DIALECT_UNKNOWN 'gemini'")
    control("an-unprojectable-schema-is-refused-with-its-problems",
            raised(lambda: provider_schema_bytes(b'{"type":"object","properties":{"a":{"type":"string"}},"required":[],'
                                                 b'"additionalProperties":false}', "codex"),
                   validate.SchemaPolicyError, "SCHEMA_UNPROJECTABLE STRICT_OPTIONAL_PROPERTY at #"))

    for failure in failures:
        print(f"packet --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"packet --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + "; room left in the "
          f"{bound.PACKET_OVERHEAD}-byte overhead: " + ", ".join(f"{k} {v}" for k, v in room.items()) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: packet.py --self-test")
    sys.exit(self_test())
