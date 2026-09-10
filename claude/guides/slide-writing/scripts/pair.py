#!/usr/bin/env python3
"""Immutable writer/reader/judge jobs consuming the slide criterion guide.

The semantic criteria live only in the primary guide beside this companion
directory. This program deliberately validates structure, snapshots, and
provenance; it does not score a deck.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


PROTOCOL = "slide-pair/v1"
CRITERION_RE = re.compile(
    r"<!-- criterion:([^\s>]+) -->(?:\r?\n)?(.*?)<!-- /criterion -->", re.DOTALL
)
LEADING_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)
RESERVED_CRITERION_MARKER_RE = re.compile(r"<!--\s*(?:criterion\b[^>]*|/criterion\b[^>]*)-->")
OPEN_CRITERION_MARKER_RE = re.compile(r"<!-- criterion:([^\s>]+) -->")
CLOSE_CRITERION_MARKER_RE = re.compile(r"<!-- /criterion -->")
# This is the sole structural authority for actor-provided item fields. Dynamic
# page, source-line, and criterion membership checks remain code-owned below.
RESPONSE_PROPERTY_MAP: dict[str, dict[str, dict[str, Any]]] = {
    "observation_page": {
        "page_id": {"type": "string", "nonempty": True},
        "text_reading": {"type": "string", "nonempty": True},
        "visual_reading": {"type": "string", "nonempty": True},
        "uncertainties": {"type": "string", "nonempty": False},
    },
    "judge_item": {
        "criterion_id": {"type": "string", "nonempty": True},
        "verdict": {
            "type": "string",
            "nonempty": True,
            "enum": ["satisfied", "revise", "uncertain", "not_applicable"],
        },
        "covered_pages": {"type": "array", "items": "string", "nonempty": True},
        "evidence_refs": {"type": "array", "items": "string", "nonempty": True},
        "reason": {"type": "string", "nonempty": True},
        "proposed_change": {"type": "string", "nonempty": False},
    },
}
OBSERVATION_FIELDS = tuple(RESPONSE_PROPERTY_MAP["observation_page"])
JUDGE_ITEM_FIELDS = tuple(RESPONSE_PROPERTY_MAP["judge_item"])


class ContractError(Exception):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"required file is missing: {path}")
    return sha256_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temp_name = handle.name
    os.replace(temp_name, path)


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid {label}: {path}") from exc


def require_object(value: Any, label: str, keys: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    if keys is not None and set(value) != keys:
        raise ContractError(f"{label} has unsupported, missing, or runtime-owned fields")
    return value


def require_string(value: Any, label: str, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ContractError(f"{label} must be" + (" a nonempty" if nonempty else "") + " string")
    return value


def require_number(value: Any, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{label} must be a finite number")
    return value


def property_schema(kind: str) -> dict[str, Any]:
    properties = RESPONSE_PROPERTY_MAP[kind]
    return {"type": "object", "required": list(properties), "properties": properties}


def validate_properties(value: Any, label: str, kind: str) -> dict[str, Any]:
    properties = RESPONSE_PROPERTY_MAP[kind]
    row = require_object(value, label, set(properties))
    for field, rule in properties.items():
        field_label = f"{label} {field}"
        field_value = row[field]
        if rule["type"] == "string":
            require_string(field_value, field_label, bool(rule["nonempty"]))
            if "enum" in rule and field_value not in rule["enum"]:
                raise ContractError(f"{field_label} is invalid")
        elif rule["type"] == "array":
            if not isinstance(field_value, list) or (rule["nonempty"] and not field_value):
                raise ContractError(f"{field_label} must be" + (" a nonempty" if rule["nonempty"] else "") + " array")
            if rule.get("items") == "string" and any(not isinstance(item, str) for item in field_value):
                raise ContractError(f"{field_label} items must be strings")
        else:  # Defensive: an internal schema edit must not silently weaken validation.
            raise ContractError(f"unsupported response property type for {field}")
    return row


def template_value(rule: dict[str, Any]) -> Any:
    if "enum" in rule:
        return "uncertain" if "uncertain" in rule["enum"] else rule["enum"][0]
    if rule["type"] == "array":
        return []
    return "<nonempty string>" if rule["nonempty"] else ""


def typed_item_template(kind: str) -> dict[str, Any]:
    return {field: template_value(rule) for field, rule in RESPONSE_PROPERTY_MAP[kind].items()}


def base_paths(base: Path) -> tuple[Path, Path, Path]:
    """Return the primary guide and runtime members for a companion directory."""
    base = base.resolve()
    guide = base.parent / f"{base.name}.md"
    script = base / "scripts" / "pair.py"
    renderer = base / "scripts" / "render.mjs"
    return guide, script, renderer


def validate_criterion_markers(data: str) -> None:
    """Reject malformed, nested, or unbalanced reserved criterion boundaries."""
    open_id: str | None = None
    for marker in RESERVED_CRITERION_MARKER_RE.finditer(data):
        token = marker.group(0)
        opening = OPEN_CRITERION_MARKER_RE.fullmatch(token)
        closing = CLOSE_CRITERION_MARKER_RE.fullmatch(token)
        if opening is None and closing is None:
            raise ContractError("criterion guide has an invalid reserved criterion marker")
        if opening is not None:
            if open_id is not None:
                raise ContractError("criterion guide has nested or unbalanced criterion markers")
            open_id = opening.group(1)
        elif open_id is None:
            raise ContractError("criterion guide has a closing criterion marker without an opening marker")
        else:
            open_id = None
    if open_id is not None:
        raise ContractError("criterion guide has an unclosed criterion marker")


def parse_criteria(data: str) -> list[dict[str, str]]:
    """Parse the primary guide, ignoring only its bounded leading frontmatter."""
    frontmatter = LEADING_FRONTMATTER_RE.match(data)
    criteria_source = data[frontmatter.end():] if frontmatter else data
    validate_criterion_markers(criteria_source)
    criteria: list[dict[str, str]] = []
    cursor = 0
    seen: set[str] = set()
    for match in CRITERION_RE.finditer(criteria_source):
        outside = criteria_source[cursor:match.start()]
        if outside.strip():
            raise ContractError("criterion guide has substantive text outside criterion blocks")
        criterion_id, text = match.group(1), match.group(2)
        if not criterion_id or criterion_id in seen:
            raise ContractError("criterion IDs must be nonempty, unique, and stable")
        if not text.strip():
            raise ContractError(f"criterion {criterion_id} is empty")
        criteria.append({"id": criterion_id, "text": text})
        seen.add(criterion_id)
        cursor = match.end()
    remainder = criteria_source[cursor:]
    if remainder.strip():
        raise ContractError("criterion guide has substantive text outside criterion blocks")
    if not criteria:
        raise ContractError("criterion guide has no criterion blocks")
    return criteria


def protocol_fingerprints(base: Path) -> dict[str, str]:
    _, _, renderer = base_paths(base)
    # --base selects criteria/assets; it must not misidentify the executing engine.
    return {"pair_py": sha256_file(Path(__file__).resolve()), "render_mjs": sha256_file(renderer)}


def oracle_for_guide(base: Path, guide_bytes: bytes) -> tuple[list[dict[str, str]], bytes]:
    """Derive the job-only oracle from one exact primary-guide byte snapshot."""
    try:
        source = guide_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("criterion guide is not valid UTF-8") from exc
    criteria = parse_criteria(source)
    block_bytes = canonical(criteria)
    oracle = {
        "protocol": PROTOCOL,
        "criteria": criteria,
        "source_fingerprint": sha256_bytes(block_bytes),
        "source_document_fingerprint": sha256_bytes(guide_bytes),
        "source_document": source,
        "bundle_fingerprint": sha256_bytes(canonical({"protocol": PROTOCOL, "criteria": criteria})),
        "protocol_fingerprints": protocol_fingerprints(base),
    }
    return criteria, canonical(oracle)


def read_guide_snapshot(base: Path) -> tuple[Path, bytes, list[dict[str, str]], bytes]:
    """Read the guide once, so its oracle, origin hash, and job copy agree exactly."""
    guide, _, _ = base_paths(base)
    try:
        guide_bytes = guide.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read criterion guide: {guide}") from exc
    criteria, oracle_bytes = oracle_for_guide(base, guide_bytes)
    return guide, guide_bytes, criteria, oracle_bytes


def check_guide(base: Path) -> list[dict[str, str]]:
    """Validate the current source structure without creating a projection."""
    _, _, criteria, _ = read_guide_snapshot(base)
    return criteria


def common_criteria(criteria: list[dict[str, str]]) -> str:
    """The sole renderer for the identical semantic block in all role packets."""
    return "\n\n".join(f"<!-- criterion:{item['id']} -->\n{item['text']}<!-- /criterion -->" for item in criteria) + "\n"


def relative_job_path(job: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(job.resolve()).as_posix()
    except ValueError as exc:
        raise ContractError(f"path escapes job directory: {path}") from exc


def manifest_path(job: Path) -> Path:
    return job / "manifest.json"


def load_manifest(job: Path) -> dict[str, Any]:
    return require_object(read_json(manifest_path(job), "manifest"), "manifest")


def write_manifest(job: Path, manifest: dict[str, Any]) -> None:
    write_atomic(manifest_path(job), canonical(manifest))


def packet_context(manifest: dict[str, Any]) -> str:
    material = {
        "job_id": manifest["job_id"],
        "protocol": manifest["protocol"],
        "origins": manifest["origins"],
        "fingerprints": manifest["fingerprints"],
    }
    return sha256_bytes(canonical(material))


def writer_request(job: Path, manifest: dict[str, Any], criteria: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "stage": "writer",
        "request_id": manifest["requests"]["writer"],
        "job_id": manifest["job_id"],
        "context": packet_context(manifest),
        "criteria": common_criteria(criteria),
        "inputs": manifest["snapshots"],
        "output": "output/deck.html",
    }


def writer_markdown(request: dict[str, Any]) -> str:
    assets = request["inputs"]["assets"]
    asset_lines = "\n".join(f"- `{value}`" for value in assets) or "- (none)"
    return (
        "# Writer request\n\n"
        "Use only the frozen source, work spec, and assets below. Write the deck HTML to `output/deck.html`. "
        "Input paths are relative to the job root; from that HTML, asset URLs use `../input/assets/<name>`.\n\n"
        f"- Source: `{request['inputs']['source']}`\n- Spec: `{request['inputs']['spec']}`\n- Assets:\n{asset_lines}\n\n"
        "## Canonical criteria\n\n" + request["criteria"]
    )


def reader_response_contract(page_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["pages"],
        "properties": {"pages": {"type": "array", "exact_members": page_ids, "items": property_schema("observation_page")}},
    }


def judge_response_contract(criteria: list[dict[str, str]], page_ids: list[str], source_line_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["items"],
        "properties": {"items": {"type": "array", "exact_members": [item["id"] for item in criteria], "items": property_schema("judge_item")}},
        "dynamic_constraints": {
            "covered_pages": {"exact_members": page_ids},
            "evidence_refs": {
                "nonempty": True,
                "allowed_exact": ["spec"],
                "allowed_forms": [
                    f"source:L<n>, where 1 <= n <= {source_line_count}",
                    "page:<page_id>",
                    "measurement:<page_id>",
                ],
                "allowed_page_ids": page_ids,
            },
        },
    }


def reader_response_template(page_ids: list[str]) -> dict[str, Any]:
    pages = []
    for page_id in page_ids:
        item = typed_item_template("observation_page")
        item["page_id"] = page_id
        pages.append(item)
    return {"pages": pages}


def judge_response_template(criteria: list[dict[str, str]], page_ids: list[str]) -> dict[str, Any]:
    items = []
    for criterion in criteria:
        item = typed_item_template("judge_item")
        item["criterion_id"] = criterion["id"]
        item["covered_pages"] = list(page_ids)
        item["evidence_refs"] = ["spec"]
        items.append(item)
    return {"items": items}


def reader_request(job: Path, manifest: dict[str, Any], criteria: list[dict[str, str]]) -> dict[str, Any]:
    render = manifest.get("render")
    if not isinstance(render, dict):
        raise ContractError("reader request requires a completed render")
    return {
        "protocol": PROTOCOL,
        "stage": "reader",
        "request_id": manifest["requests"]["reader"],
        "job_id": manifest["job_id"],
        "context": packet_context(manifest),
        "criteria": common_criteria(criteria),
        "rendered_pages": render["pages"],
        "rendered_artifacts": render["reader_artifacts"],
        "response_contract": reader_response_contract(render["pages"]),
    }


def reader_markdown(request: dict[str, Any]) -> str:
    pages = "\n".join(f"- `{path}`" for path in request["rendered_artifacts"])
    response = reader_response_template(request["rendered_pages"])
    return "".join((
        "# Reader request\n\n",
        "Read only the listed rendered artifacts. Before any later source comparison, record what text and visual structure are observable for each page.\n\n",
        f"## Rendered page IDs\n\n{canonical(request['rendered_pages']).decode('utf-8')}\n",
        f"## Rendered artifacts\n\n{pages}\n\n## Canonical criteria\n\n{request['criteria']}",
        "## Response contract\n\n```json\n", canonical(request["response_contract"]).decode("utf-8"), "```\n",
        "## Response JSON\n\n```json\n", canonical(response).decode("utf-8"), "```\n",
    ))


def source_lines(job: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    source = job / manifest["snapshots"]["source"]
    return [{"line": index, "text": value} for index, value in enumerate(source.read_text(encoding="utf-8").splitlines(), 1)]


def judge_request(job: Path, manifest: dict[str, Any], criteria: list[dict[str, str]]) -> dict[str, Any]:
    observations = read_json(job / "observations.json", "observations")
    frozen_source_lines = source_lines(job, manifest)
    page_ids = manifest["render"]["pages"]
    return {
        "protocol": PROTOCOL,
        "stage": "judge",
        "request_id": manifest["requests"]["judge"],
        "job_id": manifest["job_id"],
        "context": packet_context(manifest),
        "criteria": common_criteria(criteria),
        "source_lines": frozen_source_lines,
        "spec": read_json(job / manifest["snapshots"]["spec"], "frozen work spec"),
        "observations": observations,
        "rendered_artifacts": manifest["render"]["reader_artifacts"],
        "response_contract": judge_response_contract(criteria, page_ids, len(frozen_source_lines)),
    }


def judge_markdown(request: dict[str, Any]) -> str:
    response = judge_response_template(
        [{"id": item_id} for item_id in request["response_contract"]["properties"]["items"]["exact_members"]],
        request["response_contract"]["dynamic_constraints"]["covered_pages"]["exact_members"],
    )
    return "".join((
        "# Judge request\n\n",
        "Use the frozen source, spec, observations, and rendered artifacts. Return one item for every canonical criterion.\n\n",
        "## Canonical criteria\n\n", request["criteria"],
        "## Frozen source lines\n\n```json\n", canonical(request["source_lines"]).decode("utf-8"), "```\n",
        "## Frozen work spec\n\n```json\n", canonical(request["spec"]).decode("utf-8"), "```\n",
        "## Fixed observations\n\n```json\n", canonical(request["observations"]).decode("utf-8"), "```\n",
        "## Rendered artifacts\n\n```json\n", canonical(request["rendered_artifacts"]).decode("utf-8"), "```\n",
        "## Response contract\n\n```json\n", canonical(request["response_contract"]).decode("utf-8"), "```\n",
        "## Response JSON\n\n```json\n", canonical(response).decode("utf-8"), "```\n",
    ))


def write_packet(path: Path, value: dict[str, Any], markdown_path: Path, markdown: str) -> None:
    write_atomic(path, canonical(value))
    write_atomic(markdown_path, markdown.encode("utf-8"))


def copy_snapshot(origin: Path, destination: Path) -> str:
    if not origin.is_file():
        raise ContractError(f"input must be a file: {origin}")
    try:
        source_bytes = origin.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot freeze input: {origin}") from exc
    origin_hash = sha256_bytes(source_bytes)
    write_atomic(destination, source_bytes)
    if sha256_file(destination) != origin_hash:
        raise ContractError(f"input changed while being frozen: {origin}")
    return origin_hash


def command_check(args: argparse.Namespace) -> None:
    check_guide(args.base.resolve())


def command_prepare(args: argparse.Namespace) -> None:
    base = args.base.resolve()
    guide, guide_bytes, criteria, oracle_bytes = read_guide_snapshot(base)
    job = args.job.resolve()
    if job.exists():
        raise ContractError(f"job directory already exists: {job}")
    source, spec = args.source.resolve(), args.spec.resolve()
    if not source.is_file() or not spec.is_file():
        raise ContractError("--source and --spec must name existing files")
    read_json(spec, "work spec")
    assets = [asset.resolve() for asset in args.asset]
    basenames = [asset.name for asset in assets]
    if len(set(basenames)) != len(basenames):
        raise ContractError("asset basename collisions are not allowed")
    for asset in assets:
        if not asset.is_file():
            raise ContractError(f"asset must be a file: {asset}")
    job.mkdir(parents=True)
    try:
        source_dest = job / "input" / "source" / source.name
        spec_dest = job / "input" / "spec.json"
        asset_dests = [job / "input" / "assets" / asset.name for asset in assets]
        source_hash = copy_snapshot(source, source_dest)
        spec_hash = copy_snapshot(spec, spec_dest)
        asset_hashes = {str(asset): {"path": relative_job_path(job, dest), "sha256": copy_snapshot(asset, dest)} for asset, dest in zip(assets, asset_dests)}
        guide_dest = job / "input" / guide.name
        oracle_json_dest = job / "input" / "ORACLE.json"
        write_atomic(guide_dest, guide_bytes)
        guide_hash = sha256_bytes(guide_bytes)
        if sha256_file(guide_dest) != guide_hash:
            raise ContractError(f"criterion guide changed while being frozen: {guide}")
        write_atomic(oracle_json_dest, oracle_bytes)
        manifest: dict[str, Any] = {
            "protocol": PROTOCOL,
            "job_id": str(uuid.uuid4()),
            "state": "prepared",
            "origins": {
                "source": {"path": str(source), "sha256": source_hash},
                "spec": {"path": str(spec), "sha256": spec_hash},
                "assets": asset_hashes,
                "guide": {"path": str(guide.resolve()), "sha256": guide_hash},
            },
            "snapshots": {
                "source": relative_job_path(job, source_dest),
                "spec": relative_job_path(job, spec_dest),
                "assets": [relative_job_path(job, item) for item in asset_dests],
                "guide": relative_job_path(job, guide_dest),
                "oracle": relative_job_path(job, oracle_json_dest),
            },
            "fingerprints": {
                "oracle": sha256_bytes(oracle_bytes),
                "protocol": protocol_fingerprints(base),
            },
            "requests": {"writer": str(uuid.uuid4())},
        }
        (job / "output").mkdir()
        request = writer_request(job, manifest, criteria)
        write_packet(job / "writer-request.json", request, job / "writer.md", writer_markdown(request))
        write_manifest(job, manifest)
    except Exception:
        # A failed creation is not a usable job, and no existing job was touched.
        raise


def current_request(job: Path, manifest: dict[str, Any], stage: str, base: Path) -> dict[str, Any]:
    criteria = frozen_criteria(job, manifest, base)
    if stage == "writer":
        return writer_request(job, manifest, criteria)
    if stage == "reader":
        return reader_request(job, manifest, criteria)
    if stage == "judge":
        return judge_request(job, manifest, criteria)
    raise ContractError(f"unknown request stage: {stage}")


def assert_packet(job: Path, manifest: dict[str, Any], stage: str, base: Path) -> dict[str, Any]:
    expected = current_request(job, manifest, stage, base)
    name = f"{stage}-request.json"
    actual_path = job / name
    if not actual_path.is_file() or actual_path.read_bytes() != canonical(expected):
        raise ContractError(f"{name} is stale or edited")
    markdown = {"writer": writer_markdown, "reader": reader_markdown, "judge": judge_markdown}[stage](expected).encode("utf-8")
    markdown_path = job / f"{stage}.md"
    if not markdown_path.is_file() or markdown_path.read_bytes() != markdown:
        raise ContractError(f"{markdown_path.name} is stale or edited")
    return expected


def validate_measurements(path: Path) -> list[str]:
    data = require_object(read_json(path, "measurements"), "measurements")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ContractError("measurements must contain a nonempty pages list")
    ids: list[str] = []
    for position, page in enumerate(pages, 1):
        page_obj = require_object(page, f"measurements page {position}")
        page_id = require_string(page_obj.get("id"), f"measurements page {position} id", True)
        require_string(page_obj.get("source_page"), f"measurements page {position} source_page")
        require_string(page_obj.get("title"), f"measurements page {position} title")
        require_number(page_obj.get("width"), f"measurements page {position} width")
        require_number(page_obj.get("height"), f"measurements page {position} height")
        text_items = page_obj.get("text")
        if not isinstance(text_items, list) or not isinstance(page_obj.get("outside"), list):
            raise ContractError("measurements pages require text and outside lists")
        for text_position, text_item in enumerate(text_items, 1):
            text_obj = require_object(text_item, f"measurements text {position}.{text_position}")
            require_string(text_obj.get("text"), f"measurements text {position}.{text_position} text")
            for field in ("font_px", "x", "y", "width", "height"):
                require_number(text_obj.get(field), f"measurements text {position}.{text_position} {field}")
            require_string(text_obj.get("alignment"), f"measurements text {position}.{text_position} alignment")
        ids.append(page_id)
    if len(set(ids)) != len(ids):
        raise ContractError("rendered page IDs must be unique")
    return ids


def render_artifacts(job: Path, page_ids: list[str]) -> dict[str, Any]:
    render = job / "render"
    files = [render / "deck.pdf", render / "measurements.json"]
    files.extend(render / f"page-{index:04d}.png" for index in range(1, len(page_ids) + 1))
    for file in files:
        if not file.is_file() or file.stat().st_size == 0:
            raise ContractError(f"renderer did not produce required artifact: {file.name}")
    return {relative_job_path(job, file): sha256_file(file) for file in files}


def declared_page_count(job: Path, manifest: dict[str, Any]) -> int | None:
    """Honor an explicit positive integer pages contract without inferring one."""
    spec = read_json(job / manifest["snapshots"]["spec"], "frozen work spec")
    if isinstance(spec, dict):
        value = spec.get("pages")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def executable_path(value: Path, label: str) -> str:
    """Resolve an executable explicitly while preserving a PATH-style CLI value."""
    raw = str(value)
    if os.sep not in raw:
        found = shutil.which(raw)
        if found:
            return found
    path = value.resolve()
    if not path.is_file():
        raise ContractError(f"{label} executable is missing: {value}")
    return str(path)


def command_render(args: argparse.Namespace) -> None:
    job = args.job.resolve()
    base = args.base.resolve()
    manifest = load_manifest(job)
    if manifest.get("state") != "prepared" or "render" in manifest:
        raise ContractError("render is allowed once for a prepared job")
    preflight(job, manifest, base)
    assert_packet(job, manifest, "writer", base)
    output_html = job / "output" / "deck.html"
    if not output_html.is_file() or output_html.stat().st_size == 0:
        raise ContractError("writer output/deck.html is required before rendering")
    sealed = job / "sealed"
    render = job / "render"
    if sealed.exists() or render.exists():
        raise ContractError("sealed or render output already exists; create a new job revision")
    (sealed / "output").mkdir(parents=True)
    shutil.copyfile(output_html, sealed / "output" / "deck.html")
    if manifest["snapshots"]["assets"]:
        shutil.copytree(job / "input" / "assets", sealed / "input" / "assets")
    render.mkdir()
    _, _, renderer = base_paths(base)
    env = os.environ.copy()
    env["SLIDE_PLAYWRIGHT_MODULE"] = str(args.playwright.resolve())
    env["SLIDE_BROWSER_EXECUTABLE"] = str(args.browser.resolve())
    command = [executable_path(args.node, "node"), str(renderer.resolve()), str((sealed / "output" / "deck.html").resolve()), str(render.resolve()), str(sealed.resolve())]
    try:
        result = subprocess.run(command, shell=False, cwd=str(base), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    except OSError as exc:
        raise ContractError(f"renderer could not start: {exc.strerror or exc}") from exc
    write_atomic(render / "stdout.txt", (result.stdout or "").encode("utf-8"))
    if result.returncode != 0:
        raise ContractError(f"renderer exited with status {result.returncode}")
    page_ids = validate_measurements(render / "measurements.json")
    expected_pages = declared_page_count(job, manifest)
    if expected_pages is not None and len(page_ids) != expected_pages:
        raise ContractError(f"renderer produced {len(page_ids)} pages but work spec requires {expected_pages}")
    artifacts = render_artifacts(job, page_ids)
    artifacts[relative_job_path(job, render / "stdout.txt")] = sha256_file(render / "stdout.txt")
    if sha256_file(output_html) != sha256_file(sealed / "output" / "deck.html"):
        raise ContractError("writer HTML changed during rendering")
    sealed_files = [sealed / "output" / "deck.html"]
    sealed_files.extend(sealed / "input" / "assets" / Path(asset).name for asset in manifest["snapshots"]["assets"])
    if any(not item.is_file() for item in sealed_files):
        raise ContractError("sealed snapshots are incomplete")
    # The renderer is a subprocess: re-read every mutable dependency before
    # registering its output as current.
    verify_origins_and_snapshots(job, manifest, base)
    for snapshot in manifest["snapshots"]["assets"]:
        sealed_asset = sealed / "input" / "assets" / Path(snapshot).name
        if sha256_file(job / snapshot) != sha256_file(sealed_asset):
            raise ContractError("sealed asset differs from frozen input")
    manifest["render"] = {
        "pages": page_ids,
        "artifacts": artifacts,
        "sealed": {relative_job_path(job, item): sha256_file(item) for item in sealed_files},
        "reader_artifacts": [relative_job_path(job, job / "render" / "measurements.json")]
        + [relative_job_path(job, job / "render" / f"page-{index:04d}.png") for index in range(1, len(page_ids) + 1)],
        "renderer": {"exit_code": result.returncode, "command": command},
    }
    manifest["requests"]["reader"] = str(uuid.uuid4())
    manifest["state"] = "rendered"
    criteria = frozen_criteria(job, manifest, base)
    request = reader_request(job, manifest, criteria)
    write_packet(job / "reader-request.json", request, job / "reader.md", reader_markdown(request))
    write_manifest(job, manifest)


def exact_request(job: Path, request_path: Path, manifest: dict[str, Any], stage: str, base: Path) -> dict[str, Any]:
    expected_path = (job / f"{stage}-request.json").resolve()
    if request_path.resolve() != expected_path:
        raise ContractError(f"{stage} request must be this job's current request")
    return assert_packet(job, manifest, stage, base)


LIFECYCLE_RECORDS = ((), ("render",), ("render", "observations"), ("render", "observations", "review"))
LIFECYCLE_STATES = ("prepared", "rendered", "observed", "submitted")
MANIFEST_BASE_FIELDS = {"protocol", "job_id", "state", "origins", "snapshots", "fingerprints", "requests"}


def validate_lifecycle(manifest: dict[str, Any]) -> str:
    """Bind the stored lifecycle label to the complete registered record prefix."""
    state = manifest.get("state")
    if state not in LIFECYCLE_STATES:
        raise ContractError("job lifecycle state is invalid")
    unknown = set(manifest) - MANIFEST_BASE_FIELDS - {"render", "observations", "review"}
    if unknown:
        raise ContractError("manifest has unknown lifecycle fields")
    registered = tuple(name for name in ("render", "observations", "review") if name in manifest)
    try:
        lifecycle_index = LIFECYCLE_RECORDS.index(registered)
    except ValueError as exc:
        raise ContractError("job lifecycle records are missing prerequisites or out of order") from exc
    derived_state = LIFECYCLE_STATES[lifecycle_index]
    if state != derived_state:
        raise ContractError(f"job state {state} does not match registered lifecycle records ({derived_state})")
    requests = require_object(manifest.get("requests"), "manifest requests")
    expected_request_stages = ("writer", "reader", "judge")[: lifecycle_index + 1]
    if set(requests) != set(expected_request_stages):
        raise ContractError("manifest request stages do not match lifecycle state")
    for stage in expected_request_stages:
        require_string(requests[stage], f"manifest {stage} request ID", True)
    for record in registered:
        if not isinstance(manifest[record], dict):
            raise ContractError(f"manifest {record} record must be an object")
    return state


def preflight(job: Path, manifest: dict[str, Any], base: Path) -> None:
    """Run the complete freshness chain before consuming a lifecycle stage."""
    validate_lifecycle(manifest)
    verify_origins_and_snapshots(job, manifest, base)
    verify_render(job, manifest, base)
    verify_records(job, manifest, base)


def validate_observation_payload(payload: Any, pages: list[str]) -> list[dict[str, Any]]:
    obj = require_object(payload, "observation payload", {"pages"})
    entries = obj["pages"]
    if not isinstance(entries, list) or len(entries) != len(pages):
        raise ContractError("observation payload must include every rendered page exactly once")
    seen: set[str] = set()
    for item in entries:
        row = validate_properties(item, "observation page", "observation_page")
        page_id = row["page_id"]
        seen.add(page_id)
    if seen != set(pages) or len(seen) != len(entries):
        raise ContractError("observation page IDs must match rendered pages exactly")
    return entries


def command_observe(args: argparse.Namespace) -> None:
    job, base = args.job.resolve(), args.base.resolve()
    manifest = load_manifest(job)
    if manifest.get("state") != "rendered" or "observations" in manifest:
        raise ContractError("observe is allowed once after a completed render")
    preflight(job, manifest, base)
    request = exact_request(job, args.request, manifest, "reader", base)
    payload = read_json(args.payload.resolve(), "observation payload")
    pages = validate_observation_payload(payload, manifest["render"]["pages"])
    preflight(job, manifest, base)
    record = {"protocol": PROTOCOL, "job_id": manifest["job_id"], "reader_request_sha256": sha256_bytes(canonical(request)), "pages": pages}
    write_atomic(job / "observations.json", canonical(record))
    manifest["observations"] = {"path": "observations.json", "sha256": sha256_file(job / "observations.json")}
    manifest["requests"]["judge"] = str(uuid.uuid4())
    manifest["state"] = "observed"
    criteria = frozen_criteria(job, manifest, base)
    request_judge = judge_request(job, manifest, criteria)
    write_packet(job / "judge-request.json", request_judge, job / "judge.md", judge_markdown(request_judge))
    write_manifest(job, manifest)


def allowed_evidence(reference: str, page_ids: list[str], source_line_count: int) -> bool:
    if reference == "spec":
        return True
    match = re.fullmatch(r"source:L([1-9][0-9]*)", reference)
    if match:
        return int(match.group(1)) <= source_line_count
    match = re.fullmatch(r"(?:page|measurement):(.+)", reference)
    return bool(match and match.group(1) in page_ids)


def validate_submit_payload(payload: Any, criteria: list[dict[str, str]], page_ids: list[str], source_line_count: int) -> list[dict[str, Any]]:
    obj = require_object(payload, "judge payload", {"items"})
    items = obj["items"]
    if not isinstance(items, list) or len(items) != len(criteria):
        raise ContractError("judge payload must include every canonical criterion exactly once")
    by_id: dict[str, dict[str, Any]] = {}
    permitted = {item["id"] for item in criteria}
    for item in items:
        row = validate_properties(item, "judge item", "judge_item")
        criterion_id = row["criterion_id"]
        if criterion_id not in permitted or criterion_id in by_id:
            raise ContractError("judge payload has duplicate or unknown criterion IDs")
        if not isinstance(row["covered_pages"], list) or set(row["covered_pages"]) != set(page_ids) or len(row["covered_pages"]) != len(page_ids) or any(not isinstance(value, str) for value in row["covered_pages"]):
            raise ContractError("covered_pages must declare every rendered page exactly once")
        if not isinstance(row["evidence_refs"], list) or not row["evidence_refs"] or any(not isinstance(value, str) or not allowed_evidence(value, page_ids, source_line_count) for value in row["evidence_refs"]):
            raise ContractError("evidence_refs must be nonempty supported references")
        by_id[criterion_id] = row
    if set(by_id) != permitted:
        raise ContractError("judge payload is missing canonical criterion IDs")
    return [by_id[item["id"]] for item in criteria]


def review_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# Slide review", "",
        "Structural validation confirms packet and payload shape only. It does not prove semantic quality or that an actor dispatched or read the artifacts.", "",
        f"- Job: `{review['job_id']}`",
        f"- Judge request SHA-256: `{review['judge_request_sha256']}`", "",
    ]
    for item in review["items"]:
        lines.extend([
            f"## {item['criterion_id']} — {item['verdict']}", "",
            "### Covered pages", "", *[f"- `{page}`" for page in item["covered_pages"]], "",
            "### Evidence references", "", *[f"- `{reference}`" for reference in item["evidence_refs"]], "",
            "### Reason", "", item["reason"], "",
            "### Proposed change", "", item["proposed_change"], "",
        ])
    return "\n".join(lines)


def command_submit(args: argparse.Namespace) -> None:
    job, base = args.job.resolve(), args.base.resolve()
    manifest = load_manifest(job)
    if manifest.get("state") != "observed" or "review" in manifest:
        raise ContractError("submit is allowed once after observations")
    preflight(job, manifest, base)
    request = exact_request(job, args.request, manifest, "judge", base)
    criteria = frozen_criteria(job, manifest, base)
    payload = read_json(args.payload.resolve(), "judge payload")
    items = validate_submit_payload(payload, criteria, manifest["render"]["pages"], len(source_lines(job, manifest)))
    preflight(job, manifest, base)
    review = {"protocol": PROTOCOL, "job_id": manifest["job_id"], "judge_request_sha256": sha256_bytes(canonical(request)), "items": items}
    write_atomic(job / "review.json", canonical(review))
    write_atomic(job / "review.md", review_markdown(review).encode("utf-8"))
    manifest["review"] = {"json": {"path": "review.json", "sha256": sha256_file(job / "review.json")}, "markdown": {"path": "review.md", "sha256": sha256_file(job / "review.md")}}
    manifest["state"] = "submitted"
    write_manifest(job, manifest)


def frozen_criteria(job: Path, manifest: dict[str, Any], base: Path) -> list[dict[str, str]]:
    """Read the sealed guide and require its job oracle to be its exact projection."""
    try:
        guide_bytes = (job / manifest["snapshots"]["guide"]).read_bytes()
        actual_oracle = (job / manifest["snapshots"]["oracle"]).read_bytes()
    except OSError as exc:
        raise ContractError("frozen criterion guide or ORACLE is missing") from exc
    criteria, expected_oracle = oracle_for_guide(base, guide_bytes)
    if actual_oracle != expected_oracle or sha256_bytes(actual_oracle) != manifest["fingerprints"]["oracle"]:
        raise ContractError("frozen ORACLE changed")
    return criteria


def verify_origins_and_snapshots(job: Path, manifest: dict[str, Any], base: Path) -> None:
    if manifest.get("protocol") != PROTOCOL:
        raise ContractError("job protocol is unsupported")
    if manifest.get("fingerprints", {}).get("protocol") != protocol_fingerprints(base):
        raise ContractError("job protocol implementation has changed")
    for kind in ("source", "spec", "guide"):
        origin = manifest["origins"][kind]
        if sha256_file(Path(origin["path"])) != origin["sha256"]:
            raise ContractError(f"origin {kind} changed after prepare")
        snapshot = job / manifest["snapshots"][kind]
        if sha256_file(snapshot) != origin["sha256"]:
            raise ContractError(f"frozen {kind} snapshot changed")
    for origin_path, detail in manifest["origins"]["assets"].items():
        if sha256_file(Path(origin_path)) != detail["sha256"] or sha256_file(job / detail["path"]) != detail["sha256"]:
            raise ContractError("origin asset or frozen asset changed")
    frozen_criteria(job, manifest, base)


def verify_render(job: Path, manifest: dict[str, Any], base: Path) -> None:
    render = manifest.get("render")
    if not isinstance(render, dict):
        return
    renderer = require_object(render.get("renderer"), "renderer record", {"exit_code", "command"})
    exit_code = renderer["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
        raise ContractError("renderer record must retain integer exit code 0")
    command = renderer["command"]
    if not isinstance(command, list) or len(command) != 5 or any(not isinstance(item, str) for item in command):
        raise ContractError("renderer record command is invalid")
    require_string(command[0], "renderer executable", True)
    _, _, renderer_path = base_paths(base)
    expected_tail = [
        str(renderer_path.resolve()),
        str((job / "sealed" / "output" / "deck.html").resolve()),
        str((job / "render").resolve()),
        str((job / "sealed").resolve()),
    ]
    if command[1:] != expected_tail:
        raise ContractError("renderer record command does not match this job")
    if validate_measurements(job / "render" / "measurements.json") != render["pages"]:
        raise ContractError("rendered page IDs changed")
    for path, digest in render["artifacts"].items():
        if sha256_file(job / path) != digest:
            raise ContractError(f"rendered artifact changed: {path}")
    for path, digest in render["sealed"].items():
        if sha256_file(job / path) != digest:
            raise ContractError(f"sealed snapshot changed: {path}")
    if sha256_file(job / "output" / "deck.html") != sha256_file(job / "sealed" / "output" / "deck.html"):
        raise ContractError("writer output differs from sealed rendered HTML")


def verify_records(job: Path, manifest: dict[str, Any], base: Path) -> None:
    assert_packet(job, manifest, "writer", base)
    if "render" not in manifest:
        return
    assert_packet(job, manifest, "reader", base)
    if "observations" not in manifest:
        return
    observations = read_json(job / "observations.json", "observations")
    expected_keys = {"protocol", "job_id", "reader_request_sha256", "pages"}
    require_object(observations, "observations", expected_keys)
    validate_observation_payload({"pages": observations["pages"]}, manifest["render"]["pages"])
    if observations["protocol"] != PROTOCOL or observations["job_id"] != manifest["job_id"]:
        raise ContractError("observations context is invalid")
    reader_request = assert_packet(job, manifest, "reader", base)
    if observations["reader_request_sha256"] != sha256_bytes(canonical(reader_request)):
        raise ContractError("observations are bound to a different reader request")
    observation_record = require_object(manifest["observations"], "manifest observations", {"path", "sha256"})
    if observation_record["path"] != "observations.json":
        raise ContractError("observations record path is not canonical")
    require_string(observation_record["sha256"], "observations record SHA-256", True)
    if sha256_file(job / "observations.json") != observation_record["sha256"]:
        raise ContractError("observations changed")
    judge_request_value = assert_packet(job, manifest, "judge", base)
    if "review" not in manifest:
        return
    review = read_json(job / "review.json", "review")
    require_object(review, "review", {"protocol", "job_id", "judge_request_sha256", "items"})
    criteria = frozen_criteria(job, manifest, base)
    validate_submit_payload({"items": review["items"]}, criteria, manifest["render"]["pages"], len(source_lines(job, manifest)))
    if review["protocol"] != PROTOCOL or review["job_id"] != manifest["job_id"]:
        raise ContractError("review context is invalid")
    if review["judge_request_sha256"] != sha256_bytes(canonical(judge_request_value)):
        raise ContractError("review is bound to a different judge request")
    for detail in manifest["review"].values():
        if sha256_file(job / detail["path"]) != detail["sha256"]:
            raise ContractError("review output changed")
    if (job / "review.md").read_text(encoding="utf-8") != review_markdown(review):
        raise ContractError("review markdown is not the canonical projection")


def command_verify(args: argparse.Namespace) -> None:
    job, base = args.job.resolve(), args.base.resolve()
    manifest = load_manifest(job)
    preflight(job, manifest, base)
    state = validate_lifecycle(manifest)
    print(f"verified {state} job {manifest['job_id']}")


def parser() -> argparse.ArgumentParser:
    default_base = Path(__file__).resolve().parent.parent
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--base", type=Path, default=default_base, help="slide-writing companion directory")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--spec", type=Path, required=True)
    prepare.add_argument("--job", type=Path, required=True)
    prepare.add_argument("--asset", type=Path, action="append", default=[])
    render = commands.add_parser("render")
    render.add_argument("--job", type=Path, required=True)
    render.add_argument("--node", type=Path, required=True)
    render.add_argument("--playwright", type=Path, required=True)
    render.add_argument("--browser", type=Path, required=True)
    observe = commands.add_parser("observe")
    observe.add_argument("--job", type=Path, required=True)
    observe.add_argument("--request", type=Path, required=True)
    observe.add_argument("--payload", type=Path, required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--job", type=Path, required=True)
    submit.add_argument("--request", type=Path, required=True)
    submit.add_argument("--payload", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--job", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        {"check": command_check, "prepare": command_prepare, "render": command_render, "observe": command_observe, "submit": command_submit, "verify": command_verify}[args.command](args)
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(f"error: malformed or incomplete contract data ({exc})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
