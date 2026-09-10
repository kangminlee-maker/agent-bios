#!/usr/bin/env python3
"""Canonical corpus inventory and private snapshot compiler.

The catalog is intentionally a read-only view over package manifests and the
canonical Claude source tree.  It does not know configuration-home paths and
never writes outside the destination handed to :func:`compile_items`.

The module is the first consumer of the stable ``item_id`` values in
``domains.json``.  Those ids identify authored items; emitted paths and content
are deliberately derived separately so a body or surface edit cannot change a
CorpusRef.
"""
from __future__ import annotations

import ast
import json
import hashlib
import os
import pathlib
import re
import shlex
import sys
import tempfile
from collections.abc import Iterable
from typing import Any

try:
    from pkgid import CORE, is_valid as valid_package_id
except ImportError:  # pragma: no cover - package import from repository root
    from compose.pkgid import CORE, is_valid as valid_package_id


SCHEMA_VERSION = 1
SURFACES = frozenset(("always", "relevant", "requested", "event", "delegated"))
KINDS = frozenset(("rule", "guide", "skill", "hook", "agent"))
TIERS = frozenset(("core", "domain", "env-personal", "infra"))
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CLAUDE_HOOK_EVENTS = frozenset((
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification",
    "UserPromptSubmit", "SessionStart", "SessionEnd", "Stop", "SubagentStart",
    "SubagentStop", "PreCompact", "PermissionRequest", "TeammateIdle",
    "TaskCompleted", "ConfigChange", "WorktreeCreate", "WorktreeRemove",
))


class CatalogError(ValueError):
    """A catalog cannot be compiled safely."""


def validate_hook_binding(hook: Any) -> None:
    if not isinstance(hook, dict) or set(hook) != {"event", "matcher"}:
        raise CatalogError("hook binding must contain only event and matcher")
    event, matcher = hook.get("event"), hook.get("matcher")
    if not isinstance(event, str) or event not in CLAUDE_HOOK_EVENTS:
        raise CatalogError(f"unsupported Claude hook event {event!r}")
    if not isinstance(matcher, str) or not matcher or any(char in matcher for char in "\n\r\x00"):
        raise CatalogError("hook matcher must be one non-empty line")


def _read_utf8(path: pathlib.Path) -> str:
    if path.is_symlink():
        raise CatalogError(f"symlink input is not a corpus member: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogError(f"corpus member is not UTF-8: {path}") from exc
    except OSError as exc:
        raise CatalogError(f"cannot read corpus member: {path}") from exc


def _relative_path(value: str, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{context}: member path must be a non-empty string")
    pure = pathlib.PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise CatalogError(f"{context}: unsafe member path {value!r}")
    if any(not _SAFE_COMPONENT.match(part) for part in pure.parts):
        raise CatalogError(f"{context}: unsafe member path {value!r}")
    return pure.as_posix()


def _item_ref(package_id: str, item_id: str) -> str:
    return f"{package_id}:{item_id}"


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy through JSON to make the return value safe for UI callers."""
    return json.loads(json.dumps(item, ensure_ascii=False))


def _content_members(item: dict[str, Any]) -> dict[str, str]:
    """Validate and copy the member map used as the content authority."""
    members = item.get("members")
    if not isinstance(members, dict) or not members:
        raise CatalogError("content members must be a non-empty object")
    context = str(item.get("ref", "content"))
    normalized: dict[str, str] = {}
    for path, content in members.items():
        path = _relative_path(path, context)
        if path in normalized:
            raise CatalogError(f"{context}: duplicate member path {path!r}")
        if not isinstance(content, str):
            raise CatalogError(f"{context}: member {path!r} must be UTF-8 text")
        normalized[path] = content
    return normalized


def _legacy_primary_member(body: str, members: dict[str, str]) -> str | None:
    """Resolve only deterministic legacy representations; never guess intent."""
    matching = [path for path, content in members.items() if content == body]
    if len(matching) == 1:
        return matching[0]
    skills = [path for path in members if path == "SKILL.md" or path.endswith("/SKILL.md")]
    if len(skills) == 1:
        return skills[0]
    # Generated rule entries historically exposed the line without the file's
    # one trailing newline.  It is a known serialization difference, not intent.
    rules = [path for path, content in members.items() if path == "rule.md" and content == body + "\n"]
    if len(rules) == 1:
        return rules[0]
    return None


def _deterministic_primary_path(members: dict[str, str]) -> str | None:
    """Find a legacy path only where the path itself is unambiguous."""
    skills = [path for path in members if path == "SKILL.md" or path.endswith("/SKILL.md")]
    if len(skills) == 1:
        return skills[0]
    if len(members) == 1:
        return next(iter(members))
    return None


def _content_conflict(body: str, members: dict[str, str]) -> dict[str, Any]:
    return {
        "reason": "legacy body has no unambiguous matching primary_member",
        "members": sorted(members),
    }


def normalize_content(item: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    """Return a copied item whose ``body`` is derived from ``primary_member``.

    Old snapshots may lack ``primary_member``.  They are only migrated in
    memory when a deterministic source member exists.  An unresolved snapshot
    remains readable with ``content_conflict`` and its original body/members;
    callers must not compile it until an explicit update reconciles it.
    """
    if not isinstance(item, dict):
        raise CatalogError("content item must be an object")
    result = _public_item(item)
    members = _content_members(result)
    result["members"] = members
    primary = result.get("primary_member")
    if primary is not None:
        if not isinstance(primary, str) or primary not in members:
            raise CatalogError("primary_member must name an existing member")
        body = result.get("body")
        if body is not None and not isinstance(body, str):
            raise CatalogError("content body must be UTF-8 text")
        generated_rule_newline = isinstance(body, str) and primary == "rule.md" and members[primary] == body + "\n"
        if body is not None and body != members[primary] and not generated_rule_newline:
            if not allow_legacy:
                raise CatalogError("body conflicts with primary_member member content")
            result.pop("primary_member", None)
            result["content_conflict"] = _content_conflict(body, members)
            return result
        result["primary_member"] = primary
        result["body"] = members[primary]
        result.pop("content_conflict", None)
        return result
    if not allow_legacy:
        raise CatalogError("primary_member is required")
    body = result.get("body")
    if not isinstance(body, str):
        raise CatalogError("content body must be UTF-8 text")
    primary = _legacy_primary_member(body, members)
    if primary is not None:
        result["primary_member"] = primary
        result["body"] = members[primary]
        result.pop("content_conflict", None)
        return result
    result.pop("primary_member", None)
    result["content_conflict"] = _content_conflict(body, members)
    return result


def update_content(item: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a content patch while keeping member content the only authority.

    A body-only edit writes the established primary member.  Member-only and
    primary-member-only edits derive the returned body.  Concurrent body and
    primary-member edits must agree, so two representations cannot silently
    select different text.
    """
    if not isinstance(patch, dict):
        raise CatalogError("content patch must be an object")
    base = normalize_content(item, allow_legacy=True)
    result = _public_item(base)
    copied_patch = _public_item(patch)
    result.update(copied_patch)
    body_supplied = "body" in copied_patch
    members_supplied = "members" in copied_patch
    primary_supplied = "primary_member" in copied_patch
    members = _content_members(result)
    result["members"] = members

    primary = result.get("primary_member")
    if primary is not None and (not isinstance(primary, str) or primary not in members):
        raise CatalogError("primary_member must name an existing member")
    if body_supplied and not isinstance(copied_patch["body"], str):
        raise CatalogError("content body must be UTF-8 text")
    if primary is None and body_supplied:
        matches = [path for path, content in members.items() if content == copied_patch["body"]]
        primary = matches[0] if len(matches) == 1 else _deterministic_primary_path(members)
        if primary is None:
            raise CatalogError("content_conflict: body edit needs primary_member or one matching member")
    if primary is None and members_supplied:
        primary = _deterministic_primary_path(members)
    if body_supplied and primary is not None:
        member_body = members[primary]
        if members_supplied and member_body != copied_patch["body"]:
            raise CatalogError("body conflicts with primary_member member content")
        if not members_supplied:
            members[primary] = copied_patch["body"]

    if primary is not None:
        result["primary_member"] = primary
        result["body"] = members[primary]
        result.pop("content_conflict", None)
        return result
    if primary_supplied:
        # The explicit key was present but invalid; keep this error distinct
        # from a legacy conflict so callers can repair the named path.
        raise CatalogError("primary_member must name an existing member")
    return normalize_content(result, allow_legacy=True)


def _validate_item(item: dict[str, Any], package_id: str, seen: set[str]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise CatalogError("item must be an object")
    if not valid_package_id(package_id):
        raise CatalogError(f"invalid package_id for item: {package_id!r}")
    result = _public_item(item)
    item_id = result.get("item_id")
    if not isinstance(item_id, str) or not _SAFE_COMPONENT.match(item_id):
        raise CatalogError(f"{package_id}: item_id must be a safe stable identifier")
    ref = _item_ref(package_id, item_id)
    if ref in seen:
        raise CatalogError(f"duplicate corpus ref: {ref}")
    seen.add(ref)
    result["package_id"] = package_id
    result["ref"] = ref
    if not isinstance(result.get("title"), str) or not result["title"].strip():
        raise CatalogError(f"{ref}: title is required")
    if not isinstance(result.get("body"), str):
        raise CatalogError(f"{ref}: body must be UTF-8 text")
    if result.get("surface") not in SURFACES:
        raise CatalogError(f"{ref}: invalid surface {result.get('surface')!r}")
    if result.get("tier") not in TIERS:
        raise CatalogError(f"{ref}: invalid tier {result.get('tier')!r}")
    if result.get("kind") not in KINDS:
        raise CatalogError(f"{ref}: invalid kind {result.get('kind')!r}")
    domains = result.get("domains", [])
    if not isinstance(domains, list) or any(not isinstance(d, str) or not d for d in domains):
        raise CatalogError(f"{ref}: domains must be a list of names")
    result["domains"] = list(dict.fromkeys(domains))
    try:
        result = normalize_content(result, allow_legacy=True)
    except CatalogError as exc:
        raise CatalogError(f"{ref}: {exc}") from exc
    for key in ("routes", "dependencies"):
        values = result.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise CatalogError(f"{ref}: {key} must be a list of refs")
        result[key] = list(dict.fromkeys(values))
    origin = result.get("origin", {})
    if not isinstance(origin, dict):
        raise CatalogError(f"{ref}: origin must be an object")
    result["origin"] = origin
    if "hook" in result:
        try:
            validate_hook_binding(result["hook"])
        except CatalogError as exc:
            raise CatalogError(f"{ref}: {exc}") from exc
    return result


def _bullet_bodies(monolith: str, manifest: dict[str, Any]) -> dict[str, str]:
    bullets = [line for line in monolith.splitlines() if line.startswith("- ")]
    result: dict[str, str] = {}
    for entry in manifest.get("bullets", []):
        anchor = entry.get("anchor")
        if not isinstance(anchor, str):
            raise CatalogError("bullet without anchor")
        matches = [line for line in bullets if anchor in line]
        if len(matches) != 1:
            raise CatalogError(f"bullet anchor {anchor!r} matches {len(matches)} source lines")
        result[anchor] = matches[0]
    return result


def _manifest_item(
    *, package_id: str, item_id: str, title: str, body: str, surface: str,
    tier: str, domains: list[str], kind: str, members: dict[str, str],
    source_path: str, primary_member: str, anchor: str | None = None, dependencies: Iterable[str] = (),
) -> dict[str, Any]:
    origin: dict[str, Any] = {"source_path": source_path}
    if anchor is not None:
        origin["anchor"] = anchor
    return {
        "ref": _item_ref(package_id, item_id),
        "package_id": package_id,
        "item_id": item_id,
        "title": title,
        "body": body,
        "surface": surface,
        "tier": tier,
        "domains": list(domains),
        "kind": kind,
        "members": members,
        "primary_member": primary_member,
        "origin": origin,
        "routes": list(dependencies),
        "dependencies": list(dependencies),
    }


def _surface_for(kind: str) -> str:
    return {
        "rule": "always",
        "guide": "relevant",
        "skill": "requested",
        "hook": "event",
        "agent": "delegated",
    }[kind]


def _template_hook_bindings(repo: pathlib.Path) -> dict[str, dict[str, str]]:
    """Hook bindings are read from the actual Claude registration template.

    The template is the registration authority.  A hook source path appearing in
    a manifest description is not a registration and must never make executable
    behavior appear in a private snapshot.
    """
    path = repo / "claude" / "settings.template.json"
    try:
        settings = json.loads(_read_utf8(path))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"invalid Claude hook settings template: {path}") from exc
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks, dict):
        raise CatalogError("Claude hook settings template has no hooks object")
    result: dict[str, dict[str, str]] = {}
    for event, entries in hooks.items():
        if event not in CLAUDE_HOOK_EVENTS or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("matcher"), str):
                continue
            for hook in entry.get("hooks", []):
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    continue
                command = hook.get("command")
                if not isinstance(command, str):
                    continue
                try:
                    tokens = shlex.split(command)
                except ValueError:
                    continue
                for token in tokens:
                    match = re.fullmatch(r"(?:\.?/)?central/hooks/([A-Za-z0-9][A-Za-z0-9._-]*\.py)", token)
                    if not match:
                        continue
                    name = match.group(1)
                    if name in result:
                        raise CatalogError(f"Claude hook script registered more than once: {name}")
                    result[name] = {"event": event, "matcher": entry["matcher"]}
    return result


def _core_catalog(repo: pathlib.Path) -> dict[str, Any]:
    manifest_path = repo / "compose" / "domains.json"
    manifest = json.loads(_read_utf8(manifest_path))
    package_id = manifest.get("package_id", CORE)
    if not valid_package_id(package_id):
        raise CatalogError(f"invalid core package id: {package_id!r}")
    if manifest.get("version") != 1:
        raise CatalogError("unsupported core manifest version")
    domains = manifest.get("domains")
    if not isinstance(domains, dict) or not domains:
        raise CatalogError("core manifest domains must be non-empty")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in domains.items()):
        raise CatalogError("core manifest domains must map names to descriptions")
    monolith_path = repo / "claude" / "CLAUDE.md"
    monolith = _read_utf8(monolith_path)
    bullet_bodies = _bullet_bodies(monolith, manifest)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    hook_bindings = _template_hook_bindings(repo)
    for entry in manifest.get("bullets", []):
        item_id = entry.get("item_id")
        anchor = entry.get("anchor")
        if not isinstance(item_id, str):
            raise CatalogError(f"bullet {anchor!r} lacks persistent item_id")
        body = bullet_bodies[anchor]
        items.append(_validate_item(_manifest_item(
            package_id=package_id, item_id=item_id, title=anchor, body=body,
            surface=_surface_for("rule"), tier=entry["tier"], domains=entry.get("domains", []),
            kind="rule", members={"rule.md": body + "\n"}, primary_member="rule.md",
            source_path="claude/CLAUDE.md",
            anchor=anchor,
        ), package_id, seen))

    section_specs = (
        ("guides", "guide", "claude/guides"),
        ("hooks", "hook", "claude/hooks"),
        ("agents", "agent", "claude/agents"),
    )
    for section, kind, source_dir in section_specs:
        entries = manifest.get(section, {})
        if not isinstance(entries, dict):
            raise CatalogError(f"core manifest {section} must be an object")
        for name, entry in entries.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("item_id"), str):
                raise CatalogError(f"{section}/{name} lacks persistent item_id")
            source = repo / source_dir / name
            body = _read_utf8(source)
            members = {f"{kind}s/{name}": body}
            if kind == "guide":
                try:
                    from assemble import guide_members
                except ImportError:
                    from .assemble import guide_members
                try:
                    members = {f"guides/{member}": _read_utf8(repo / source_dir / member)
                               for member in guide_members(repo / source_dir, name)}
                except ValueError as exc:
                    raise CatalogError(f"invalid guide bundle {name}: {exc}") from exc
            item = _manifest_item(
                package_id=package_id, item_id=entry["item_id"], title=name, body=body,
                surface=_surface_for(kind), tier=entry["tier"], domains=entry.get("domains", []),
                kind=kind, members=members,
                primary_member=f"{kind}s/{name}", source_path=f"{source_dir}/{name}",
            )
            if kind == "hook" and name in hook_bindings:
                item["hook"] = hook_bindings[name]
            items.append(_validate_item(item, package_id, seen))

    skills = manifest.get("skills", {})
    if not isinstance(skills, dict):
        raise CatalogError("core manifest skills must be an object")
    for name, entry in skills.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("item_id"), str):
            raise CatalogError(f"skills/{name} lacks persistent item_id")
        root = repo / "claude" / "skills" / name
        if root.is_symlink() or not root.is_dir():
            raise CatalogError(f"skill source is not a directory: {root}")
        members: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise CatalogError(f"symlink input is not a corpus member: {path}")
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                members[f"skills/{name}/{relative}"] = _read_utf8(path)
        if f"skills/{name}/SKILL.md" not in members:
            raise CatalogError(f"skill source lacks SKILL.md: {root}")
        items.append(_validate_item(_manifest_item(
            package_id=package_id, item_id=entry["item_id"], title=name,
            body=members[f"skills/{name}/SKILL.md"], surface=_surface_for("skill"),
            tier=entry["tier"], domains=entry.get("domains", []), kind="skill",
            members=members, primary_member=f"skills/{name}/SKILL.md", source_path=f"claude/skills/{name}",
        ), package_id, seen))
    if not items:
        raise CatalogError("core catalog is empty")
    return {
        "schema_version": SCHEMA_VERSION,
        "packages": [{"package_id": package_id, "domains": domains}],
        "items": items,
    }


def _external_catalog(package_root: pathlib.Path) -> dict[str, Any]:
    manifest_path = package_root / "manifest.json"
    manifest = json.loads(_read_utf8(manifest_path))
    if manifest.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise CatalogError("unsupported external package schema")
    package_id = manifest.get("package_id")
    if not valid_package_id(package_id):
        raise CatalogError(f"invalid package_id: {package_id!r}")
    domains = manifest.get("domains", {})
    if not isinstance(domains, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                            for k, v in domains.items()):
        raise CatalogError("external package domains must map names to descriptions")
    raw_items = manifest.get("items")
    if raw_items is None:
        item_path = package_root / "items.json"
        raw_items = json.loads(_read_utf8(item_path)).get("items") if item_path.is_file() else None
    if not isinstance(raw_items, list) or not raw_items:
        raise CatalogError("external package must contain non-empty items")
    seen: set[str] = set()
    items = [_validate_item(item, package_id, seen) for item in raw_items]
    return {"schema_version": SCHEMA_VERSION,
            "packages": [{"package_id": package_id, "domains": domains}], "items": items}


def load_catalog(repo: pathlib.Path) -> dict[str, Any]:
    """Load a core repository, or an external package root with ``manifest.json``.

    An external manifest uses the normalized item shape returned here, keeping a
    single validation authority for built-in, personal, and imported packages.
    """
    root = pathlib.Path(repo).resolve()
    if root.is_symlink():
        raise CatalogError(f"catalog root must not be a symlink: {root}")
    if (root / "compose" / "domains.json").is_file():
        return _core_catalog(root)
    if (root / "manifest.json").is_file():
        return _external_catalog(root)
    raise CatalogError(f"no core catalog or package manifest at {root}")


def _destination_path(destination: pathlib.Path, relative: str) -> pathlib.Path:
    relative = _relative_path(relative, "compiler")
    path = destination / relative
    # ``relative`` has already excluded traversal. resolve() after joining still
    # detects a pre-existing symlink in a caller-provided destination.
    try:
        path.resolve().relative_to(destination.resolve())
    except ValueError as exc:
        raise CatalogError(f"compiler destination escapes root: {relative!r}") from exc
    return path


def _write_private(path: pathlib.Path, content: str) -> None:
    if path.is_symlink():
        raise CatalogError(f"compiler refuses symlink output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x', encoding='utf-8') as output:
            output.write(content)
    except FileExistsError as exc:
        raise CatalogError(f"compiler output already exists or aliases another member: {path}") from exc


def _replace_private_owned(path: pathlib.Path, content: str) -> None:
    """Atomically rewrite a member this compiler emitted earlier in this run."""
    if path.is_symlink() or not path.is_file():
        raise CatalogError(f"compiler cannot replace unowned native member: {path}")
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _resource_rewrites(items: list[dict[str, Any]], destination: pathlib.Path) -> dict[str, str]:
    """Known canonical source paths -> the corresponding private copied member.

    We only rewrite source links which name a catalog member.  Broad replacement
    of config-home variables would mutate unrelated prose and reintroduce a
    global-home dependency.
    """
    rewrites: dict[str, str] = {}
    for item in items:
        source = item.get("origin", {}).get("source_path")
        if not isinstance(source, str):
            continue
        members = item["members"]
        if item["kind"] == "skill":
            continue
        primary = item.get("primary_member")
        if primary not in members:
            continue
        emitted_root = destination / "items" / _safe_ref_path(item["ref"])
        emitted = emitted_root / primary
        rewrites[source] = str(emitted)
        # Current corpus prose uses these two host config forms.  The generated
        # target is private and host-neutral; no generic variable substitution.
        if source.startswith("claude/guides/"):
            tail = source.removeprefix("claude/guides/")
            rewrites[f"${{CLAUDE_CONFIG_DIR:-$HOME/.claude}}/guides/{tail}"] = str(emitted)
            rewrites[f"${{CODEX_HOME:-$HOME/.codex}}/guides/{tail}"] = str(emitted)
            primary_dir = pathlib.PurePosixPath(primary).parent
            for member in members:
                relative = pathlib.PurePosixPath(member)
                if not relative.is_relative_to(primary_dir):
                    continue
                suffix = relative.relative_to(primary_dir).as_posix()
                member_source = pathlib.PurePosixPath(source).parent / suffix
                member_target = str(emitted_root / member)
                rewrites[member_source.as_posix()] = member_target
                member_tail = member_source.as_posix().removeprefix("claude/guides/")
                rewrites[f"${{CLAUDE_CONFIG_DIR:-$HOME/.claude}}/guides/{member_tail}"] = member_target
                rewrites[f"${{CODEX_HOME:-$HOME/.codex}}/guides/{member_tail}"] = member_target
    return rewrites


def _safe_ref_path(ref: str) -> str:
    # package refs contain '@', '/', and ':'; preserve identity without allowing
    # their separators to create destination hierarchy outside this item root.
    return "item-" + re.sub(r"[^A-Za-z0-9._-]", "_", ref)


def _rewrite_resources(text: str, rewrites: dict[str, str]) -> str:
    for source, replacement in sorted(rewrites.items(), key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(source, replacement)
    return text


def _rewrite_native_hook_guide(item: dict[str, Any], text: str, rewrites: dict[str, str]) -> str:
    """Resolve the hook's own relative guide constant only in a native plugin."""
    source = item.get("origin", {}).get("source_path")
    if item.get("kind") != "hook" or not isinstance(source, str):
        return text
    if not source.startswith("claude/hooks/"):
        return text
    match = re.search(r'(?m)^GUIDE = "guides/([A-Za-z0-9][A-Za-z0-9._-]*\.md)"$', text)
    if not match:
        return text
    target = rewrites.get(f"claude/guides/{match.group(1)}")
    if target is None:
        return text
    return text[:match.start()] + f'GUIDE = {target!r}' + text[match.end():]


def _procedure_description(item: dict[str, Any]) -> str:
    """A compact, authored-first summary for requested procedure access."""
    explicit = item.get("description")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    match = re.search(r"^description:\s*(.+)$", item["body"], flags=re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"')
    for line in item["body"].splitlines():
        text = line.strip()
        if text and text != "---" and not text.startswith("#"):
            return text
    return "Private procedure"


def _router_text(relevant: list[dict[str, Any]], destination: pathlib.Path) -> str:
    lines = ["# Generated relevant-corpus router", "",
             "Use a listed guide only when the task matches its domains.", ""]
    for item in sorted(relevant, key=lambda x: x["ref"]):
        primary = item["_emitted_members"][item["primary_member"]]
        domains = ", ".join(item["domains"]) or "all selected environments"
        front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", item["body"], flags=re.DOTALL)
        description = re.search(r"^description:[ \t]*(.+)$", front.group(1), flags=re.MULTILINE) if front else None
        condition = description.group(1).strip().strip('\"\'') if description else ""
        detail = f"{condition} — {domains}" if condition else domains
        lines.append(f"- [{item['title']}]({primary}) — {detail} ({item['ref']})")
    return "\n".join(lines) + "\n"


def _plugin_namespace(ref: str) -> str:
    """A compact namespace derived from the complete, package-qualified ref."""
    return "agent-bios-" + hashlib.sha256(ref.encode("utf-8")).hexdigest()[:24]


def _native_hook_carrier(item: dict[str, Any]) -> tuple[str, dict[str, str]]:
    source = item.get("origin", {}).get("source_path")
    if item.get("kind") != "hook" or not isinstance(source, str):
        raise CatalogError("event item has no installed Claude hook carrier provenance")
    matched = re.fullmatch(r"claude/hooks/([A-Za-z0-9][A-Za-z0-9._-]*\.py)", source)
    if not matched:
        raise CatalogError("event item origin is not an installed Claude hooks/*.py carrier")
    member = f"hooks/{matched.group(1)}"
    if member not in item["members"]:
        raise CatalogError("event item no longer retains its installed hook entrypoint")
    try:
        ast.parse(item["members"][member], filename=member)
    except SyntaxError as exc:
        raise CatalogError(f"native hook entrypoint is not valid Python: {exc.msg}") from exc
    binding = item.get("hook")
    if not isinstance(binding, dict):
        raise CatalogError("event item has no registered Claude hook binding")
    return member, binding


def _native_agent_carrier(item: dict[str, Any]) -> tuple[str, str]:
    source = item.get("origin", {}).get("source_path")
    if item.get("kind") != "agent" or not isinstance(source, str):
        raise CatalogError("delegated item has no installed Claude agent carrier provenance")
    matched = re.fullmatch(r"claude/agents/([A-Za-z0-9][A-Za-z0-9._-]*\.md)", source)
    if not matched:
        raise CatalogError("delegated item origin is not an installed Claude agents/*.md carrier")
    filename = matched.group(1)
    member = f"agents/{filename}"
    if member not in item["members"]:
        raise CatalogError("delegated item no longer retains its installed agent entrypoint")
    # Claude advertises the frontmatter name, not the filename. Read only the
    # bounded routing slug; leave all other native YAML interpretation to Claude.
    header = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", item["members"][member], re.S)
    names = re.findall(r"(?m)^name:[ \t]*([^\r\n]*)", header.group(1)) if header else []
    if len(names) != 1:
        raise CatalogError("native agent needs one top-level frontmatter name")
    name = names[0].strip()
    if len(name) >= 2 and name[0] == name[-1] and name[0] in "\"'":
        name = name[1:-1]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise CatalogError("native agent name must be a plain or quoted routing slug")
    return member, name


def _assert_native_member_safety(item: dict[str, Any], carrier: str, surface: str) -> None:
    """A plugin root may not smuggle a second discovered capability into launch."""
    agent_members = {member for member in item["members"] if re.fullmatch(r"agents/[^/]+\.md", member)}
    if surface == "delegated" and agent_members != {carrier}:
        raise CatalogError("delegated item must retain exactly its one agents/*.md carrier")
    for member in item["members"]:
        first = pathlib.PurePosixPath(member).parts[0]
        if first in {"skills", "commands", ".claude-plugin"}:
            raise CatalogError(f"native plugin member would auto-discover {member!r}")
        if member == "hooks/hooks.json" or member == "settings.json":
            raise CatalogError(f"native plugin member would override generated registration {member!r}")
        if first == "agents" and member != carrier:
            raise CatalogError(f"native plugin member adds an unselected agent carrier {member!r}")
        # Hook code and ordinary reference/assets remain valid. The generated
        # hooks.json calls only the proven carrier, so support files stay inert.


def _write_plugin_manifest(root: pathlib.Path, namespace: str, item: dict[str, Any]) -> str:
    relative = pathlib.PurePosixPath(".claude-plugin") / "plugin.json"
    _write_private(root / relative, json.dumps({
        "name": namespace,
        "version": "1.0.0",
        "description": f"Private agent-bios corpus item {item['ref']}",
    }, ensure_ascii=False, separators=(",", ":")) + "\n")
    return relative.as_posix()


def _emit_native_claude_item(
    item: dict[str, Any], destination: pathlib.Path, namespace: str, base_instruction_text: str,
) -> tuple[list[str], dict[str, Any] | None]:
    root = destination / "items" / _safe_ref_path(item["ref"])
    if item["surface"] == "event":
        member, binding = _native_hook_carrier(item)
        _assert_native_member_safety(item, member, "event")
        emitted = [_write_plugin_manifest(root, namespace, item)]
        command = f'{shlex.quote(sys.executable)} "${{CLAUDE_PLUGIN_ROOT}}/{member}"'
        hooks = {"hooks": {binding["event"]: [{
            "matcher": binding["matcher"],
            "hooks": [{"type": "command", "command": command}],
        }]}}
        relative = pathlib.PurePosixPath("hooks") / "hooks.json"
        _write_private(root / relative, json.dumps(hooks, ensure_ascii=False, separators=(",", ":")) + "\n")
        emitted.append(relative.as_posix())
        return emitted, {"ref": item["ref"], "plugin": namespace, "hook": binding, "entrypoint": member}
    if item["surface"] == "delegated":
        member, name = _native_agent_carrier(item)
        _assert_native_member_safety(item, member, "delegated")
        # Carrier validation happens before any plugin write. The child receives
        # the ordinary compiled snapshot, while its qualified route is added to
        # the parent instruction later so it cannot recurse into this body.
        target = root / member
        _replace_private_owned(target, _read_utf8(target) + "\n\n" + base_instruction_text)
        emitted = [_write_plugin_manifest(root, namespace, item)]
        return emitted, {"ref": item["ref"], "plugin": namespace, "agent_name": name,
                         "route": f"{namespace}:{name}"}
    raise CatalogError(f"unsupported native Claude surface {item['surface']!r}")


def compile_items(items: list[dict[str, Any]], destination: pathlib.Path, host: str,
                  native: bool = False) -> dict[str, Any]:
    """Emit selected items into one private destination.

    ``host`` is currently a validation seam for adapters.  Claude and Codex use
    the same private file layout, while the caller injects ``instruction_text``
    through the corresponding per-session adapter.
    """
    if host not in {"claude", "codex"}:
        raise CatalogError(f"unsupported host: {host!r}")
    if not isinstance(native, bool):
        raise CatalogError("native must be boolean")
    if not isinstance(items, list):
        raise CatalogError("compiler requires an item list")
    destination = pathlib.Path(destination)
    if destination.exists() and destination.is_symlink():
        raise CatalogError(f"compiler destination must not be a symlink: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    normalized = [_validate_item(item, item.get("package_id", ""), seen) for item in items]
    unresolved = [item["ref"] for item in normalized if item.get("content_conflict")]
    if unresolved:
        raise CatalogError(f"content_conflict: selected item needs reconciliation: {', '.join(unresolved)}")
    rewrites = _resource_rewrites(normalized, destination)
    files: list[str] = []
    for item in normalized:
        emitted: dict[str, str] = {}
        root = destination / "items" / _safe_ref_path(item["ref"])
        for member, content in item["members"].items():
            relative = pathlib.PurePosixPath("items") / _safe_ref_path(item["ref"]) / member
            target = _destination_path(destination, relative.as_posix())
            rewritten = _rewrite_resources(content, rewrites)
            if native and host == "claude" and item["surface"] == "event":
                rewritten = _rewrite_native_hook_guide(item, rewritten, rewrites)
            _write_private(target, rewritten)
            emitted[member] = str(target)
            files.append(relative.as_posix())
        item["_emitted_members"] = emitted

    always = [item for item in normalized if item["surface"] == "always"]
    relevant = [item for item in normalized if item["surface"] == "relevant"]
    requested = [item for item in normalized if item["surface"] == "requested"]
    router_path = None
    if relevant:
        router_relative = "router/relevant.md"
        router_path = _destination_path(destination, router_relative)
        _write_private(router_path, _router_text(relevant, destination))
        files.append(router_relative)
    instruction_parts = ["# Activated private corpus", ""]
    if always:
        instruction_parts.append("## Always in this environment")
        instruction_parts.append("")
        instruction_parts.extend(_rewrite_resources(item["body"], rewrites).rstrip("\n") for item in always)
        instruction_parts.append("")
    if router_path is not None:
        instruction_parts.append(f"Relevant procedures: {router_path}")
    if requested:
        instruction_parts.append("Requested procedures:")
        for item in requested:
            primary = item["_emitted_members"][item["primary_member"]]
            instruction_parts.append(
                f"- {item['title']} — {_procedure_description(item)}: {primary} ({item['ref']})")
    base_instruction_text = "\n".join(instruction_parts).rstrip() + "\n"
    unavailable: list[dict[str, str]] = []
    assets: dict[str, Any] = {}
    plugin_names: dict[str, str] = {}
    plugin_roots: list[str] = []
    agent_routes: list[dict[str, str]] = []
    for item in normalized:
        if item["surface"] not in {"event", "delegated"}:
            continue
        if not native:
            unavailable.append({"ref": item["ref"], "surface": item["surface"],
                                "reason": f"native {item['surface']} consumption is disabled; opt in with --corpus-native"})
            continue
        if host != "claude":
            unavailable.append({"ref": item["ref"], "surface": item["surface"],
                                "reason": f"native {item['surface']} adapter is unsupported for {host}"})
            continue
        namespace = _plugin_namespace(item["ref"])
        prior = plugin_names.get(namespace)
        if prior is not None and prior != item["ref"]:
            raise CatalogError(f"Claude plugin namespace collision: {prior} and {item['ref']}")
        plugin_names[namespace] = item["ref"]
        try:
            emitted, route = _emit_native_claude_item(item, destination, namespace, base_instruction_text)
        except CatalogError as exc:
            unavailable.append({"ref": item["ref"], "surface": item["surface"], "reason": str(exc)})
            continue
        root_relative = (pathlib.PurePosixPath("items") / _safe_ref_path(item["ref"])).as_posix()
        plugin_roots.append(root_relative)
        files.extend((pathlib.PurePosixPath(root_relative) / path).as_posix() for path in emitted)
        if route and item["surface"] == "delegated":
            agent_routes.append(route)
    if native and host == "claude":
        assets["claude_plugins"] = sorted(plugin_roots)
    instruction_text = base_instruction_text
    if agent_routes:
        instruction_text += "\nNative delegated agents:\n"
        for route in sorted(agent_routes, key=lambda row: row["ref"]):
            instruction_text += f"- {route['route']} ({route['ref']})\n"
    instruction_relative = "launch-content/instructions.md"
    _write_private(_destination_path(destination, instruction_relative), instruction_text)
    files.append(instruction_relative)
    for item in normalized:
        item.pop("_emitted_members", None)
    return {
        "instruction_text": instruction_text,
        "files": sorted(files),
        "item_refs": [item["ref"] for item in normalized],
        "unavailable": unavailable,
        "assets": assets,
    }
