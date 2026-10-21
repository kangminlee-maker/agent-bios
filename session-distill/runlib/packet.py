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

Linter failures are named CALL_ID_MISSING, PRINCIPLES_MISSING, SCHEMA_REFERENCE_MISSING and
PAYLOAD_MISSING; a guide without its section is PRINCIPLES_UNAVAILABLE.

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
    """The bytes `schema.json` holds: the schema compiled through the policy, as canonical JSON."""
    validate.compile_schema(schema)
    return (json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def build(call_id, stage, seat, payload, schema=None, repo=REPO):
    """The packet's bytes. `schema` is the bytes of `schema.json`, or None for a schema-less call."""
    block = principles_block(repo)
    reference = f"sha256:{sha256_bytes(schema)}" if schema is not None else "none"
    header = (f"CALL-ID: {call_id}\nSTAGE: {stage}\nSEAT: {seat}\nSCHEMA: {reference}\n"
              f"PRINCIPLES: sha256:{sha256_bytes(block.encode('utf-8'))}\n\n")
    return (header + block + PAYLOAD_MARKER + "\n" + payload).encode("utf-8")


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

    for failure in failures:
        print(f"packet --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"packet --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: packet.py --self-test")
    sys.exit(self_test())
