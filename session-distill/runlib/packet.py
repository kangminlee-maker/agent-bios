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
refuses.

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
TEMPLATES = ("read", "stitch")      # S3's two calls (plan WP-08)
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


def schema_bytes(schema):
    """The bytes `schema.json` holds, which are the schema the host is handed: the schema compiled through the policy,
    as canonical JSON, without its `$schema`. The policy pins draft 2020-12 in code (`validate.compile_schema`), so the
    key decides nothing here; Claude Code's `--json-schema` check builds Ajv's draft-07 class, refuses a schema whose
    `$schema` names a meta-schema it does not hold - the 2020-12 one every distill schema names - and exits before any
    request (WP-08 commit 7, live leg dw2-live1)."""
    validate.compile_schema(schema)
    sent = {key: value for key, value in schema.items() if key != "$schema"}
    return (json.dumps(sent, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


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

    schema = schema_bytes({"type": "object", "additionalProperties": False, "required": ["answer"],
                           "properties": {"answer": {"type": "string"}}})
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
    # the bytes a host is handed carry no $schema (WP-08 commit 7, dw2-live1): asked of the schemas S3 hands a host,
    # each of which names the 2020-12 meta-schema, and the bytes must still be the same schema to the policy
    host_bound = {}
    for name in TEMPLATES:
        try:
            held = json.loads((pathlib.Path(__file__).resolve().parents[1] / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
            sent = json.loads(schema_bytes(held))
            validate.compile_schema(sent)
            host_bound[name] = (held, sent)
        except Exception as exc:  # noqa: BLE001 - whatever stops a schema here is reported by name
            failures.append(f"positive control: the {name} schema did not load or compile: {exc}")
    control("host-schema-carries-no-$schema",
            [] if sorted(host_bound) == sorted(TEMPLATES) and all(
                "$schema" in held and sent == {k: v for k, v in held.items() if k != "$schema"} for held, sent in host_bound.values())
            else [f"a schema handed a host still names its meta-schema: {[n for n, (_h, s) in host_bound.items() if '$schema' in s]}"])
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
    filled_by = {"read": ["expected", "omissions", "window"], "stitch": ["claims", "events"]}
    room = {}
    for name in TEMPLATES:
        try:
            fields = template_fields(name)
            answer = schema_bytes(json.loads((schemas / f"{name}.schema.json").read_text(encoding="utf-8")))
        except (TemplateError, OSError, ValueError) as exc:
            failures.append(f"positive control: the {name} template or schema did not load: {exc}")
            continue
        control(f"{name}-template-takes-the-fields-its-stage-fills",
                [] if fields == filled_by[name] else [f"placeholders {fields}, filled {filled_by[name]}"])
        call = f"r1-S3-{name}-a1"
        made = build(call, "S3", "claude:claude-sonnet-5-5/high", render(name, {f: f"<{f}>" for f in fields}), answer)
        control(f"{name}-packet-passes-the-linter", check(made, call, answer))
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
