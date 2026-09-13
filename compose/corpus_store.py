#!/usr/bin/env python3
"""Private, revision-checked storage for an activated corpus.

The store deliberately owns source state and immutable projections only.  It
does not alter a host configuration or claim that a snapshot was loaded by a
host; that is the launch adapter's job.
"""
from __future__ import annotations

import copy
import contextlib
import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import uuid
from typing import Any, Iterator

try:
    from corpus_transaction import transaction_lock, guard_pending, pending_operations, operation_scope_active
except ImportError:
    from .corpus_transaction import transaction_lock, guard_pending, pending_operations, operation_scope_active

SCHEMA_VERSION = 1
LOCAL_PACKAGE = "@local/personal"
SURFACES = {"always", "relevant", "requested", "event", "delegated"}
KINDS = {"rule", "guide", "skill", "hook", "agent"}
ITEM_FIELDS = {
    "ref", "package_id", "item_id", "title", "body", "surface", "tier",
    "domains", "kind", "members", "origin", "routes", "dependencies",
    "active", "learning_source", "hook", "primary_member",
}
RUNTIME_FIELDS = {
    "digest", "revision", "content_ref", "path", "state", "created_at",
    "updated_at", "baseline_ref", "plan_id", "history_id",
    "enabled", "enabled_override",
}
LEARNING_FIELDS = {"schema_version", "learning_id", "lesson", "domain", "created", "supporting_sessions",
                   "criteria", "classification", "proposed_domain", "context"}
LEARNING_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class CorpusStoreError(RuntimeError):
    pass


class StaleRevision(CorpusStoreError):
    pass


class ValidationError(CorpusStoreError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _safe_part(value: str, label: str = "path") -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValidationError(f"invalid {label}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValidationError(f"unowned {label}: {value!r}")
    return value


def _host(value: str) -> str:
    if value not in {"claude", "codex"}:
        raise ValidationError(f"unsupported host: {value!r}")
    return value


def _reject_symlink_path(path: Path, *, leaf: bool = True) -> None:
    """Refuse a symlink at the store-owned path boundary.

    Platform temporary directories commonly sit below system symlink aliases
    (macOS `/var` is one), so the boundary deliberately stops at the configured
    store path or its direct parent.  Every store-created nested root is checked
    when it becomes the direct parent of a write; the lock itself also uses
    ``O_NOFOLLOW`` against a final-component substitution race.
    """
    target = path if leaf else path.parent
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            raise CorpusStoreError(f"symlink is not a corpus-store path: {target}")


def _json_read(path: Path, default: Any = None) -> Any:
    _reject_symlink_path(path)
    if not path.is_file():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusStoreError(f"unreadable state at {path}: {exc}") from exc


def _atomic_write(path: Path, value: Any) -> None:
    _reject_symlink_path(path)
    _reject_symlink_path(path, leaf=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _canonical(value) + b"\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            tmp.chmod(path.stat().st_mode & 0o777)
        os.replace(tmp, path)
        # Persist the directory entry as well as the file bytes.
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def _copy_json(value: Any) -> Any:
    return json.loads(_canonical(value))


def _rewrite_staged_paths(staging: Path, destination: Path) -> None:
    """Replace compiler-internal absolute staging links before publication."""
    old, new = str(staging), str(destination)
    for path in staging.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CorpusStoreError(f"snapshot compiler emitted non-text member: {path}") from exc
        if old in text:
            path.write_text(text.replace(old, new), encoding="utf-8")


def _snapshot_relative_paths(files: Any) -> list[str]:
    if not isinstance(files, list) or not files or not all(isinstance(path, str) for path in files):
        raise ValidationError("snapshot compiler returned an empty or invalid file set")
    normalized = [_safe_part(path, "snapshot file") for path in files]
    if len(set(normalized)) != len(normalized):
        raise ValidationError("snapshot compiler returned duplicate files")
    return sorted(normalized)


def _snapshot_file_digests(root: Path, files: list[str]) -> dict[str, str]:
    expected = sorted(set(files) | {"output.json"})
    result: dict[str, str] = {}
    for relative in expected:
        path = root / _safe_part(relative, "snapshot file")
        if path.is_symlink() or not path.is_file():
            raise CorpusStoreError(f"snapshot output is missing or symlinked: {relative}")
        result[relative] = _digest(path.read_bytes())
    return result


def _snapshot_assets(value: Any, files: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"claude_plugins", "codex_hooks"}:
        raise ValidationError("invalid snapshot native assets")
    if "codex_hooks" in value:
        try:
            from corpus_catalog import CatalogError, validate_native_hook_config
        except ImportError:
            from .corpus_catalog import CatalogError, validate_native_hook_config
        try:
            validate_native_hook_config(value["codex_hooks"], "codex")
        except CatalogError as exc:
            raise ValidationError(f"invalid snapshot native hooks: {exc}") from exc
    plugins = value.get("claude_plugins", [])
    if not isinstance(plugins, list) or not all(isinstance(path, str) for path in plugins):
        raise ValidationError("snapshot plugins must be relative paths")
    if len(plugins) != len(set(plugins)):
        raise ValidationError("duplicate snapshot plugin")
    for relative in plugins:
        _safe_part(relative, "snapshot plugin")
        if PurePosixPath(relative).as_posix() != relative:
            raise ValidationError("snapshot plugin path is not canonical")
        if f"{relative}/.claude-plugin/plugin.json" not in files:
            raise ValidationError("snapshot plugin has no inventoried manifest")
    return _copy_json(value)


def verify_snapshot(path: Path, expected_content_ref: str) -> dict[str, Any]:
    """Validate a persisted snapshot without consulting current authoring state."""
    root = Path(path)
    _safe_part(expected_content_ref, "content ref")
    if root.is_symlink() or not root.is_dir():
        raise ValidationError(f"snapshot is missing or symlinked: {root}")
    inventory = _json_read(root / "inventory.json")
    output = _json_read(root / "output.json")
    if not isinstance(inventory, dict) or not isinstance(output, dict):
        raise ValidationError("snapshot metadata is unreadable")
    inputs = inventory.get("inputs")
    if not isinstance(inputs, dict) or _digest(inputs) != expected_content_ref:
        raise ValidationError("snapshot content ref does not match canonical inputs")
    files = _snapshot_relative_paths(output.get("files"))
    _snapshot_assets(output.get("assets", {}), files)
    digests = inventory.get("file_digests")
    if not isinstance(digests, dict) or not digests:
        raise ValidationError("snapshot has no file digest inventory")
    expected = set(files) | {"output.json"}
    if set(digests) != expected:
        raise ValidationError("snapshot digest file set is not exact")
    actual_files: set[str] = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise ValidationError(f"snapshot contains symlink: {candidate.relative_to(root)}")
        if candidate.is_file() and candidate != root / "inventory.json":
            actual_files.add(candidate.relative_to(root).as_posix())
    if actual_files != expected:
        raise ValidationError("snapshot persisted file set is not exact")
    for relative, digest in digests.items():
        if not isinstance(digest, str) or _digest((root / relative).read_bytes()) != digest:
            raise ValidationError(f"snapshot file digest mismatch: {relative}")
    return {"content_ref": expected_content_ref, "path": str(root), "inputs": inputs,
            "items": inventory.get("items"), "file_digests": digests, "output": output}


class CorpusStore:
    """The private corpus source, transaction journal, and snapshot compiler.

    ``state_root`` is deploy/runtime-owned. ``user_root`` is deliberately a
    separate authority: install never overwrites it.
    """

    def __init__(self, repo: Path, state_root: Path | None = None, user_root: Path | None = None):
        self.repo = Path(repo).resolve()
        self.state_root = Path(state_root or os.environ.get(
            "AGENT_BIOS_STATE_DIR", str(Path.home() / ".local/share/agent-bios")
        )).expanduser()
        self.user_root = Path(user_root or os.environ.get(
            "AGENT_BIOS_CORPUS_DIR", str(Path.home() / ".config/agent-bios/corpus")
        )).expanduser()
        self.runtime = self.state_root / "runtime"
        self.sessions = self.state_root / "sessions"

    # ---- layout and locking -------------------------------------------------

    @property
    def _runtime_state_path(self) -> Path:
        return self.runtime / "state.json"

    @property
    def _user_state_path(self) -> Path:
        return self.user_root / "state.json"

    @contextlib.contextmanager
    def _lock(self) -> Iterator[None]:
        _reject_symlink_path(self.state_root, leaf=False)
        _reject_symlink_path(self.state_root)
        _reject_symlink_path(self.user_root, leaf=False)
        _reject_symlink_path(self.user_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        with transaction_lock(self.state_root):
            yield

    def _empty_runtime(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "last_successful_install_ref": None,
            "selected_baseline_ref": None,
        }

    def _empty_user(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "items": {},
            "overrides": {},
            "tombstones": {},
            "selection": None,
            "learning_suppressions": {"claude": [], "codex": []},
        }

    def _runtime_state(self) -> dict[str, Any]:
        state = _json_read(self._runtime_state_path, self._empty_runtime())
        if state.get("schema_version") != SCHEMA_VERSION:
            raise CorpusStoreError("runtime state schema mismatch")
        return state

    def _user_state(self) -> dict[str, Any]:
        state = _json_read(self._user_state_path, self._empty_user())
        if state.get("schema_version") != SCHEMA_VERSION:
            raise CorpusStoreError("personal state schema mismatch")
        # v1 sources created before reset acquired this projection field.  It
        # has a deterministic empty meaning and is persisted on the next
        # authoring transaction rather than rewritten by a read.
        state.setdefault("learning_suppressions", {"claude": [], "codex": []})
        for field, typ in (("items", dict), ("overrides", dict), ("tombstones", dict), ("learning_suppressions", dict)):
            if not isinstance(state.get(field), typ):
                raise CorpusStoreError(f"personal state has invalid {field}")
        # Optional, so reading an older state does not change its revision or the
        # exact before/after documents used by prepared-transaction recovery.
        self._enabled_overrides(state)
        self._selection_mode(state, {})
        return state

    @staticmethod
    def _enabled_overrides(user: dict[str, Any]) -> dict[str, bool]:
        values = user.get("enabled_overrides", {})
        if (not isinstance(values, dict) or any(
                not isinstance(ref, str) or ":" not in ref or not isinstance(value, bool)
                for ref, value in values.items())):
            raise CorpusStoreError("personal state has invalid enabled_overrides")
        return values

    @staticmethod
    def _selection_mode(user: dict[str, Any], defaults: dict[str, Any], requested: str | None = None) -> str:
        value = requested if requested is not None else user.get("selection_mode", defaults.get("selection_mode", "default"))
        if not isinstance(value, str) or value not in {"default", "selected", "none"}:
            raise ValidationError("selection_mode must be default, selected, or none")
        return value

    def _write_transaction(self, tx_id: str, record: dict[str, Any]) -> None:
        _atomic_write(self.runtime / "transactions" / tx_id / "journal.json", record)

    def _recover_locked(self) -> None:
        """Finish a source publication interrupted after its PREPARED journal.

        User and runtime sources have separate ownership roots and cannot share
        one rename.  The journal therefore records both candidate documents
        before either pointer moves.  Recovery accepts only an exact prior/next
        pair and finishes the known transaction; any third value is evidence of
        an out-of-band writer and remains a fail-loud recovery record.
        """
        guard_pending(self.state_root)
        root = self.runtime / "transactions"
        if not root.is_dir():
            return
        for journal_path in sorted(root.glob("*/journal.json")):
            journal = _json_read(journal_path)
            if isinstance(journal, dict) and journal.get("state") == "NEEDS_RECOVERY":
                raise CorpusStoreError(f"transaction {journal_path.parent.name} needs manual recovery")
            if not isinstance(journal, dict) or journal.get("state") != "PREPARED":
                continue
            plan = journal.get("plan")
            if not isinstance(plan, dict) or not isinstance(plan.get("before"), dict) or not isinstance(plan.get("after"), dict):
                raise CorpusStoreError(f"invalid prepared transaction {journal_path.parent.name}")
            current_runtime = _json_read(self._runtime_state_path, self._empty_runtime())
            current_user = _json_read(self._user_state_path, self._empty_user())
            prior, candidate = plan["before"], plan["after"]
            known_runtime = current_runtime in (prior.get("runtime"), candidate.get("runtime"))
            known_user = current_user in (prior.get("user"), candidate.get("user"))
            if not known_runtime or not known_user:
                journal["state"] = "NEEDS_RECOVERY"
                journal["recovery_error"] = "source differs from prepared transaction prior and candidate"
                _atomic_write(journal_path, journal)
                raise CorpusStoreError(f"transaction {journal_path.parent.name} needs manual recovery")
            history_id = journal.get("history_id")
            if history_id is None:
                instant = plan.get("created_at", journal.get("prepared_at", _utcnow()))
                history_id = f"{instant.replace(':', '').replace('+00:00', 'Z')}-{journal_path.parent.name[:12]}"
                journal["history_id"] = history_id
                _atomic_write(journal_path, journal)
            history = {"runtime": prior["runtime"], "user": prior["user"],
                       "revision": plan.get("expected_revision"), "details": plan.get("details", {})}
            history_path = self.user_root / "history" / history_id / "state.json"
            if not history_path.exists():
                _atomic_write(history_path, history)
            if plan.get("details", {}).get("operation") == "reset":
                trash_path = self.user_root / "trash" / history_id / "state.json"
                if not trash_path.exists():
                    _atomic_write(trash_path, history)
            _atomic_write(self._user_state_path, candidate["user"])
            _atomic_write(self._runtime_state_path, candidate["runtime"])
            journal["state"] = "RECOVERED_COMMITTED"
            journal["recovered_at"] = _utcnow()
            _atomic_write(journal_path, journal)

    # ---- baseline and source resolution ------------------------------------

    def _catalog_module(self):
        try:
            return importlib.import_module("corpus_catalog")
        except ModuleNotFoundError:
            # Package execution is useful in tests and is harmless in a checkout.
            import sys
            sys.path.insert(0, str(self.repo / "compose"))
            try:
                return importlib.import_module("corpus_catalog")
            except ModuleNotFoundError as exc:
                raise CorpusStoreError("compose/corpus_catalog.py is required") from exc

    def _baseline_dir(self, ref: str) -> Path:
        _safe_part(ref, "baseline reference")
        return self.runtime / "baselines" / ref

    def _normalize_content(self, item: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
        return self._catalog_module().normalize_content(item, allow_legacy=allow_legacy)

    def _read_baseline(self, ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
        root = self._baseline_dir(ref)
        inventory = _json_read(root / "inventory.json")
        defaults = _json_read(root / "defaults.json")
        if not isinstance(inventory, dict) or not isinstance(defaults, dict):
            raise CorpusStoreError(f"missing baseline tuple {ref}")
        return inventory, defaults

    def _baseline_promotions(self, ref: str) -> dict[str, Any]:
        data = _json_read(self._baseline_dir(ref) / "promotions.json", {"version": 0, "promotions": []})
        if not isinstance(data, dict) or not isinstance(data.get("promotions"), list):
            raise CorpusStoreError(f"invalid promotion data in baseline {ref}")
        return data

    def _selected_baseline(self, runtime: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        ref = runtime.get("selected_baseline_ref")
        if not isinstance(ref, str):
            raise CorpusStoreError("no installed baseline; run install first")
        inventory, defaults = self._read_baseline(ref)
        return ref, inventory, defaults

    def _learning_events(self, host: str) -> list[dict[str, Any]]:
        _host(host)
        _reject_symlink_path(self.user_root)
        _reject_symlink_path(self.user_root / "learnings")
        _reject_symlink_path(self.user_root / "learnings" / host)
        path = self.user_root / "learnings" / host / "events.jsonl"
        _reject_symlink_path(path)
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except ValueError as exc:
                raise CorpusStoreError(f"invalid learning event {path}:{line_no}") from exc
            if not isinstance(event, dict):
                raise CorpusStoreError(f"invalid learning event {path}:{line_no}")
            events.append(event)
        return events

    def _learning_item(self, host: str, event: dict[str, Any]) -> dict[str, Any] | None:
        learning_id = event["learning_id"]
        body = event["lesson"]
        return {
            "ref": f"@local/learnings-{host}:{learning_id}",
            "package_id": f"@local/learnings-{host}", "item_id": learning_id,
            "title": event["domain"],
            "body": body, "surface": event.get("surface", "always"),
            "tier": event.get("tier", "env-personal"), "domains": ["personal"], "kind": "rule",
            "members": {"learning.md": body}, "origin": {"type": "learning", "host": host},
            "learning_source": True,
        }

    @staticmethod
    def _learning_host_from_ref(ref: str) -> str | None:
        prefix = "@local/learnings-"
        if not ref.startswith(prefix) or ":" not in ref:
            return None
        host = ref[len(prefix):].split(":", 1)[0]
        return host if host in {"claude", "codex"} else None

    def _effective_items(
        self, runtime: dict[str, Any], user: dict[str, Any], host: str | None = None, include_suppressed: bool = False
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], str]:
        baseline_ref, inventory, defaults = self._selected_baseline(runtime)
        source = inventory.get("items")
        if not isinstance(source, list):
            raise CorpusStoreError(f"baseline {baseline_ref} has no item inventory")
        items: dict[str, dict[str, Any]] = {}
        for raw in source:
            item = self._validate_item(raw, allow_origin=True)
            items[item["ref"]] = item
        for ref, raw in user["items"].items():
            item = self._validate_item(raw, allow_origin=True)
            if item["ref"] != ref or item["package_id"] != LOCAL_PACKAGE:
                raise CorpusStoreError("personal item identity mismatch")
            items[ref] = item
        if host:
            suppressed = set(user.get("learning_suppressions", {}).get(host, []))
            for event in self._learning_events(host):
                suppressed_event = _digest(event) in suppressed
                if suppressed_event and not include_suppressed:
                    continue
                item = self._learning_item(host, event)
                if item is not None:
                    if suppressed_event:
                        item["active"] = False
                    items[item["ref"]] = self._validate_item(item, allow_origin=True)
        for ref, override in user["overrides"].items():
            if ref not in items:
                continue
            base_digest = override.get("base_digest")
            patch = override.get("patch")
            if not isinstance(base_digest, str) or not isinstance(patch, dict):
                raise CorpusStoreError(f"invalid override for {ref}")
            # An upstream change to the same base is not silently merged.
            if _digest(items[ref]) != base_digest:
                items[ref]["conflict"] = {"base_digest": base_digest, "current_digest": _digest(items[ref])}
                continue
            merged = {**items[ref], **patch}
            items[ref] = self._validate_item(merged, allow_origin=True)
        for ref in user["tombstones"]:
            if include_suppressed and self._learning_host_from_ref(ref) == host and ref in items:
                items[ref]["active"] = False
            else:
                items.pop(ref, None)
        return [self._normalize_content(item, allow_legacy=True) for item in items.values()], inventory, defaults, baseline_ref

    def _resolve_promotions(
        self, selected: list[dict[str, Any]], user: dict[str, Any], host: str, baseline_ref: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Suppress only a source event proven replaced in this exact snapshot."""
        promotions = self._baseline_promotions(baseline_ref)
        by_id: dict[str, list[dict[str, Any]]] = {}
        warnings: list[dict[str, Any]] = []
        for row in promotions["promotions"]:
            if not isinstance(row, dict):
                warnings.append({"reason": "invalid_promotion_row"})
                continue
            required = {"learning_id", "host", "source_digest", "target_ref", "target_digest"}
            if not required <= set(row):
                # v2 rows are audience claims only.  They must never cause a
                # source deletion merely because an anchor happens to match.
                if isinstance(row.get("learning_id"), str):
                    warnings.append({"ref": f"@local/learnings-{host}:{row['learning_id']}",
                                     "reason": "promotion_mapping_incomplete"})
                continue
            if all(isinstance(row.get(field), str) for field in required):
                by_id.setdefault(row["learning_id"], []).append(row)
            else:
                warnings.append({"reason": "invalid_promotion_row"})
        chosen = {item["ref"]: item for item in selected}
        retained: list[dict[str, Any]] = []
        for item in selected:
            if item.get("origin", {}).get("type") != "learning" or item.get("origin", {}).get("host") != host:
                retained.append(item)
                continue
            learning_id = item["item_id"]
            event = next((event for event in self._learning_events(host)
                          if (event.get("learning_id") or event.get("id")) == learning_id), None)
            candidates = [row for row in by_id.get(learning_id, [])
                          if row["host"] == host and event is not None and row["source_digest"] == _digest(event)]
            if not candidates:
                retained.append(item)
                continue
            row = candidates[0]
            target = chosen.get(row["target_ref"])
            if target is None:
                retained.append(item)
                continue
            if row["target_digest"] != _digest(target):
                warnings.append({"ref": item["ref"], "reason": "promotion_target_digest_mismatch"})
                retained.append(item)
                continue
            member = row.get("target_member")
            if row.get("exclusive") is True and target["body"] == item["body"]:
                continue
            if isinstance(member, str) and target.get("members", {}).get(member) == item["body"]:
                baseline_inventory, _defaults = self._read_baseline(baseline_ref)
                original = next((raw for raw in baseline_inventory["items"] if raw.get("ref") == row["target_ref"]), None)
                if not isinstance(original, dict) or not isinstance(original.get("members"), dict):
                    raise ValidationError(f"learning_rebase_conflict: {item['ref']}")
                if set(original["members"]) - set(target["members"]):
                    raise ValidationError(f"learning_rebase_conflict: {item['ref']}")
                continue
            raise ValidationError(f"learning_rebase_conflict: {item['ref']}")
        return retained, warnings

    def _authoring_revision(self, runtime: dict[str, Any], user: dict[str, Any]) -> str:
        learning = {}
        for host in ("claude", "codex"):
            events = self._learning_events(host)
            learning[host] = _digest(events)
        return _digest({
            "selected_baseline_ref": runtime.get("selected_baseline_ref"),
            "last_successful_install_ref": runtime.get("last_successful_install_ref"),
            "user": user, "learning": learning,
        })

    # ---- validation ---------------------------------------------------------

    def _validate_item(self, raw: Any, *, allow_origin: bool = False) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValidationError("item must be an object")
        unknown = set(raw) - ITEM_FIELDS - {"conflict", "content_conflict"}
        if unknown:
            raise ValidationError(f"unknown item fields: {', '.join(sorted(unknown))}")
        runtime = set(raw) & RUNTIME_FIELDS
        if runtime:
            raise ValidationError(f"runtime-owned item fields: {', '.join(sorted(runtime))}")
        item = _copy_json(raw)
        required = ("ref", "package_id", "item_id", "title", "body", "surface", "tier", "domains", "kind", "members")
        missing = [field for field in required if field not in item]
        if missing:
            raise ValidationError(f"item missing fields: {', '.join(missing)}")
        for field in ("ref", "package_id", "item_id", "title", "tier"):
            if not isinstance(item[field], str) or not item[field]:
                raise ValidationError(f"invalid item {field}")
        if not isinstance(item["body"], str):
            raise ValidationError("invalid item body")
        if item["ref"] != f"{item['package_id']}:{item['item_id']}":
            raise ValidationError("item ref does not match package_id and item_id")
        catalog = self._catalog_module()
        surfaces = getattr(catalog, "SURFACES", SURFACES)
        kinds = getattr(catalog, "KINDS", KINDS)
        if item["surface"] not in surfaces or item["kind"] not in kinds:
            raise ValidationError("invalid consumption surface or kind")
        if "hook" in item:
            try:
                catalog.validate_hook_binding(item["hook"])
            except (ValueError, AttributeError) as exc:
                raise ValidationError(f"invalid hook binding: {exc}") from exc
        if not isinstance(item["domains"], list) or not all(isinstance(x, str) for x in item["domains"]):
            raise ValidationError("invalid item domains")
        if not isinstance(item["members"], dict):
            raise ValidationError("invalid item members")
        for path, body in item["members"].items():
            _safe_part(path, "member path")
            if not isinstance(body, str):
                raise ValidationError("member body must be text")
        if "origin" in item and not isinstance(item["origin"], dict):
            raise ValidationError("invalid item origin")
        if not allow_origin and "origin" in item:
            raise ValidationError("origin is catalog-owned")
        return item

    def _validate_patch(self, patch: Any) -> dict[str, Any]:
        if not isinstance(patch, dict) or not patch:
            raise ValidationError("update needs a non-empty patch")
        unknown = set(patch) - (ITEM_FIELDS - {"ref", "package_id", "item_id", "origin", "active", "learning_source"})
        if unknown:
            raise ValidationError(f"unknown or immutable patch fields: {', '.join(sorted(unknown))}")
        if set(patch) & RUNTIME_FIELDS:
            raise ValidationError("runtime-owned field in patch")
        return _copy_json(patch)

    def _validate_selection(self, selection: Any, inventory: dict[str, Any]) -> list[str] | None:
        if selection is None:
            return None
        if not isinstance(selection, list) or not all(isinstance(x, str) for x in selection):
            raise ValidationError("selection must be a list of qualified refs/domains")
        packages = {p.get("package_id") for p in inventory.get("packages", []) if isinstance(p, dict)}
        for value in selection:
            if value == "all" or value in packages:
                continue
            if ":" in value:
                continue
            if value.startswith("@local/"):
                continue
            if "/" not in value or not value.startswith("@"):
                raise ValidationError(f"selection must be fully qualified: {value!r}")
            package = value.rsplit("/", 1)[0]
            if package not in packages and package != LOCAL_PACKAGE and not package.startswith("@local/"):
                raise ValidationError(f"unknown package in selection: {value!r}")
        return sorted(set(selection))

    def _normalized_install_selection(self, domains: list[str] | None, catalog: dict[str, Any]) -> list[str]:
        """Translate legacy bare domain inputs at the installer boundary once."""
        if domains is None:
            return []
        if not isinstance(domains, list) or not all(isinstance(domain, str) for domain in domains):
            raise ValidationError("install domains must be a list of strings")
        packages = catalog.get("packages", [])
        if not packages or not isinstance(packages[0], dict) or not isinstance(packages[0].get("package_id"), str):
            raise ValidationError("catalog lacks a core package")
        core_package = packages[0]["package_id"]
        normalized = [domain if domain == "all" or domain.startswith("@") else f"{core_package}/{domain}" for domain in domains]
        return self._validate_selection(normalized, catalog) or []

    @staticmethod
    def _effective_selection(user: dict[str, Any], defaults: dict[str, Any], requested: list[str] | None) -> list[str] | None:
        if requested is not None:
            return requested
        if user.get("selection") is not None:
            return user["selection"]
        return defaults.get("selection")

    def _validate_snapshot_selection(self, selection: list[str] | None, inventory: dict[str, Any], items: list[dict[str, Any]]) -> None:
        if selection is None:
            return
        if not isinstance(selection, list) or not all(isinstance(value, str) for value in selection):
            raise ValidationError("selection must be a list")
        packages = {entry["package_id"]: set((entry.get("domains") or {}).keys())
                    for entry in inventory.get("packages", []) if isinstance(entry, dict) and isinstance(entry.get("package_id"), str)}
        packages.update({LOCAL_PACKAGE: {"personal"}, "@local/learnings-claude": {"personal"},
                         "@local/learnings-codex": {"personal"}})
        refs = {item["ref"] for item in items}
        for value in selection:
            if value == "all":
                continue
            if ":" in value:
                if value not in refs:
                    raise ValidationError(f"unknown corpus selection ref: {value}")
                continue
            if value in packages:
                continue
            if not value.startswith("@") or "/" not in value:
                raise ValidationError(f"selection must be package/domain-qualified: {value!r}")
            package, domain = value.rsplit("/", 1)
            if package not in packages or domain not in packages[package]:
                raise ValidationError(f"unknown corpus selection domain: {value}")

    def _selection_subjects(self, runtime: dict[str, Any], user: dict[str, Any],
                            items: list[dict[str, Any]], selection: list[str] | None) -> list[dict[str, Any]]:
        """Validate stored host-qualified selections without delivering another host's items."""
        subjects = list(items)
        refs = {item["ref"] for item in subjects}
        for host in ("claude", "codex"):
            prefix = f"@local/learnings-{host}:"
            if any(value.startswith(prefix) and value not in refs for value in selection or []):
                subjects.extend(item for item in self._effective_items(runtime, user, host=host)[0]
                                if item.get("active", True))
        return subjects

    def _validate_candidate_projection(self, runtime: dict[str, Any], user: dict[str, Any]) -> None:
        """Use the real compiler as a plan validator without publishing output."""
        catalog = self._catalog_module()
        try:
            with tempfile.TemporaryDirectory(prefix="agent-bios-plan-") as temp:
                for host in ("claude", "codex"):
                    items, _inventory, defaults, _baseline = self._effective_items(runtime, user, host=host)
                    active = [item for item in items if item.get("active", True) is not False]
                    selection = self._effective_selection(user, defaults, None)
                    self._validate_snapshot_selection(selection, _inventory,
                                                      self._selection_subjects(runtime, user, active, selection))
                    selected = self._selected_items(active, selection, self._enabled_overrides(user),
                                                    mode=self._selection_mode(user, defaults), host=host)
                    self._require_resolved(selected)
                    catalog.compile_items(_copy_json(selected), Path(temp) / host, host)
        except Exception as exc:
            # The catalog names the concrete member/ref; retain that actionable
            # evidence but keep the manager's public validation contract stable.
            raise ValidationError(f"candidate projection is invalid: {exc}") from exc

    @staticmethod
    def _require_resolved(items: list[dict[str, Any]]) -> None:
        conflicts = [item["ref"] for item in items if item.get("conflict") or item.get("content_conflict")]
        if conflicts:
            raise ValidationError("unresolved corpus conflict: " + ", ".join(sorted(conflicts)))

    def _rebase_overlays(self, old_inventory: dict[str, Any], new_inventory: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        """Three-way field/member comparison shared by forward and reverse switches."""
        result = _copy_json(user)
        old_items = {item["ref"]: item for item in old_inventory.get("items", []) if isinstance(item, dict)}
        new_items = {item["ref"]: item for item in new_inventory.get("items", []) if isinstance(item, dict)}
        conflicts: list[str] = []
        for ref, override in list(result["overrides"].items()):
            learning_host = self._learning_host_from_ref(ref)
            if learning_host is not None:
                event = next((event for event in self._learning_events(learning_host)
                              if ref == f"@local/learnings-{learning_host}:{event['learning_id']}"), None)
                if event is None or override.get("base_digest") != _digest(self._learning_item(learning_host, event)):
                    conflicts.append(ref)
                continue
            old, new = old_items.get(ref), new_items.get(ref)
            if old is None or not isinstance(override, dict):
                conflicts.append(ref)
                continue
            if override.get("base_digest") != _digest(old) or not isinstance(override.get("patch"), dict):
                conflicts.append(ref)
                continue
            base = self._normalize_content(old, allow_legacy=True)
            personal = self._normalize_content({**old, **override["patch"]}, allow_legacy=True)
            if personal == base:
                result["overrides"].pop(ref, None)
                continue
            if new is None:
                conflicts.append(ref)
                continue
            target = self._normalize_content(new, allow_legacy=True)
            self._require_resolved([base, target, personal])
            merged = _copy_json(target)
            missing = object()
            for field in ITEM_FIELDS - {"body"}:
                if field == "members":
                    output = dict(target["members"])
                    for member in set(base["members"]) | set(personal["members"]) | set(target["members"]):
                        prior = base["members"].get(member, missing)
                        mine = personal["members"].get(member, missing)
                        theirs = target["members"].get(member, missing)
                        if mine == prior:
                            continue
                        if theirs != prior and mine != theirs:
                            conflicts.append(f"{ref} members/{member}")
                        elif mine is missing:
                            output.pop(member, None)
                        else:
                            output[member] = mine
                    merged[field] = output
                else:
                    prior, mine, theirs = base.get(field, missing), personal.get(field, missing), target.get(field, missing)
                    if mine == prior:
                        continue
                    if theirs != prior and mine != theirs:
                        conflicts.append(f"{ref} {field}")
                    elif mine is missing:
                        merged.pop(field, None)
                    else:
                        merged[field] = mine
            # body is a view of the merged primary member, not a second merge input.
            merged.pop("body", None)
            merged = self._normalize_content(merged)
            patch = {field: value for field, value in merged.items()
                     if field in ITEM_FIELDS and value != new.get(field)}
            if patch:
                result["overrides"][ref] = {"base_digest": _digest(new), "patch": patch}
            else:
                result["overrides"].pop(ref, None)
        if conflicts:
            raise ValidationError("baseline_update_conflict: " + ", ".join(sorted(conflicts)))
        return result

    # ---- public read API ----------------------------------------------------

    def install(self, domains: list[str] | None = None, *, selection_mode: str | None = None,
                replace_selection: bool = False) -> dict[str, Any]:
        """Install one immutable validated baseline tuple without touching user data."""
        with self._lock():
            return self.commit_install(self.prepare_install(domains, selection_mode=selection_mode,
                                                           replace_selection=replace_selection))

    def prepare_install(self, domains: list[str] | None = None, *, selection_mode: str | None = None,
                        replace_selection: bool = False) -> dict[str, Any]:
        """Stage a validated baseline and source plan without advancing any pointer."""
        with self._lock():
            self._recover_locked()
            catalog = self._catalog_module().load_catalog(self.repo)
            if not isinstance(catalog, dict) or catalog.get("schema_version") != SCHEMA_VERSION:
                raise ValidationError("catalog schema mismatch")
            raw_items = catalog.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raise ValidationError("catalog inventory is empty")
            items = [self._validate_item(item, allow_origin=True) for item in raw_items]
            if len({item["ref"] for item in items}) != len(items):
                raise ValidationError("catalog has duplicate corpus refs")
            mode = self._selection_mode({}, {}, selection_mode)
            selected = self._normalized_install_selection(domains, catalog)
            if mode == "none" and selected:
                raise ValidationError("no-corpus installation cannot include selection targets")
            defaults = {"schema_version": SCHEMA_VERSION, "selection": selected}
            if mode == "default":
                defaults["selection"] += [LOCAL_PACKAGE, "@local/learnings-claude", "@local/learnings-codex"]
            if selection_mode is not None:
                defaults["selection_mode"] = mode
            promotion_path = self.repo / "learn" / "promotions.json"
            promotions = _json_read(promotion_path, {"version": 0, "promotions": []})
            if not isinstance(promotions, dict) or not isinstance(promotions.get("promotions"), list):
                raise ValidationError("promotion manifest is invalid")
            compiler = self.repo / "compose" / "corpus_catalog.py"
            tuple_data = {
                "schema_version": SCHEMA_VERSION, "catalog": catalog, "defaults": defaults,
                "promotions": promotions,
                "compiler_digest": _digest(compiler.read_bytes()) if compiler.is_file() else None,
            }
            baseline_ref = _digest(tuple_data)
            root = self._baseline_dir(baseline_ref)
            existing = root / "inventory.json"
            if existing.exists() and _json_read(existing) != catalog:
                raise CorpusStoreError(f"immutable baseline collision: {baseline_ref}")
            runtime = self._runtime_state()
            user = self._user_state()
            prior_last = runtime.get("last_successful_install_ref")
            next_user = user
            adopt = runtime.get("selected_baseline_ref") == prior_last
            if adopt and isinstance(prior_last, str) and prior_last != baseline_ref:
                old_inventory, _old_defaults = self._read_baseline(prior_last)
                # A conflict refuses before either the baseline pointer or the
                # successful-install record changes.
                next_user = self._rebase_overlays(old_inventory, catalog, user)
            before = {"runtime": _copy_json(runtime), "user": _copy_json(user)}
            if replace_selection:
                next_user = _copy_json(next_user)
                next_user["selection"] = _copy_json(defaults["selection"])
                next_user["selection_mode"] = mode
                next_user.pop("enabled_overrides", None)
            _atomic_write(root / "inventory.json", catalog)
            _atomic_write(root / "defaults.json", defaults)
            _atomic_write(root / "promotions.json", promotions)
            runtime["last_successful_install_ref"] = baseline_ref
            if runtime.get("selected_baseline_ref") is None or adopt:
                runtime["selected_baseline_ref"] = baseline_ref
            self._validate_candidate_projection(runtime, next_user)
            transaction_id = uuid.uuid4().hex
            details = {"baseline_ref": baseline_ref, "selected_baseline_ref": runtime["selected_baseline_ref"], "items": len(items)}
            candidate = {"transaction_id": transaction_id, "before": before,
                         "after": {"runtime": runtime, "user": next_user}, "details": details,
                         "expected_revision": self._authoring_revision(before["runtime"], before["user"])}
            self._write_transaction(transaction_id, {"state": "PLANNED", "kind": "install", "plan": candidate})
            return _copy_json(candidate)

    def commit_install(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Publish a staged installation; repeated recovery consumes the same journal."""
        transaction_id = _safe_part(candidate.get("transaction_id"), "transaction id")
        with self._lock():
            self._recover_locked()
            record = _json_read(self.runtime / "transactions" / transaction_id / "journal.json")
            if (self.runtime / "private-install.json").exists() and not operation_scope_active(self.state_root):
                raise ValidationError("managed installations must publish through agent-bios install")
            if not isinstance(record, dict) or record.get("kind") != "install":
                raise ValidationError("unknown installation candidate")
            plan = record["plan"]
            if len(candidate) > 1 and candidate != plan:
                raise ValidationError("installation candidate differs from its recorded plan")
            if record["state"] in {"COMMITTED", "RECOVERED_COMMITTED"}:
                return _copy_json(plan["details"])
            runtime, user = self._runtime_state(), self._user_state()
            if record["state"] != "PLANNED" or self._authoring_revision(runtime, user) != plan["expected_revision"]:
                raise StaleRevision("installation candidate is stale")
            self._validate_candidate_projection(plan["after"]["runtime"], plan["after"]["user"])
            record["state"] = "PREPARED"
            self._write_transaction(transaction_id, record)
            self._recover_locked()
            return _copy_json(plan["details"])

    def status(self) -> dict[str, Any]:
        with self._lock():
            pending = [entry for entry in pending_operations(self.state_root)
                       if entry["state"] == "NEEDS_RECOVERY"
                       or "resets" in Path(entry["path"]).parts
                       or _json_read(Path(entry["path"])).get("owner") == "installer"]
            if pending:
                return {"schema_version": SCHEMA_VERSION, "needs_recovery": pending,
                        "installed": self._runtime_state().get("last_successful_install_ref") is not None}
            self._recover_locked()
            runtime, user = self._runtime_state(), self._user_state()
            revision = self._authoring_revision(runtime, user)
            refs = list((self.runtime / "baselines").glob("*/inventory.json"))
            defaults = self._selected_baseline(runtime)[2] if runtime.get("selected_baseline_ref") else {}
            return {
                "schema_version": SCHEMA_VERSION, "installed": runtime.get("last_successful_install_ref") is not None,
                "last_successful_install_ref": runtime.get("last_successful_install_ref"),
                "selected_baseline_ref": runtime.get("selected_baseline_ref"),
                "revision": revision, "baseline_count": len(refs),
                "personal_items": len(user["items"]), "overrides": len(user["overrides"]),
                "tombstones": len(user["tombstones"]), "selection": self._effective_selection(user, defaults, None),
                "selection_mode": self._selection_mode(user, defaults),
                "enabled_overrides": _copy_json(self._enabled_overrides(user)),
            }

    def list_items(self, include_removed: bool = True) -> list[dict[str, Any]]:
        with self._lock():
            self._recover_locked()
            runtime, user = self._runtime_state(), self._user_state()
            selected_ref, inventory, defaults = self._selected_baseline(runtime)
            all_items, _, _, _ = self._effective_items(runtime, user)
            effective = {item["ref"]: item for item in all_items}
            for host in ("claude", "codex"):
                effective.update({item["ref"]: item for item in self._effective_items(runtime, user, host=host, include_suppressed=True)[0]})
            source = {item["ref"]: self._validate_item(item, allow_origin=True) for item in inventory["items"]}
            overrides = self._enabled_overrides(user)
            selection = self._effective_selection(user, defaults, None)
            enabled = {item["ref"] for item in self._selected_items(
                [item for item in effective.values() if item.get("active", True) is not False], selection, overrides,
                mode=self._selection_mode(user, defaults))}
            revision = self._authoring_revision(runtime, user)
            rows: list[dict[str, Any]] = []
            for ref in sorted(set(source) | set(user["items"]) | set(effective)):
                base = source.get(ref)
                item = effective.get(ref)
                removed = ref in user["tombstones"] or (item is not None and item.get("active", True) is False)
                if removed and not include_removed:
                    continue
                row = _copy_json(item or base or user["items"][ref])
                row["state"] = "removed" if removed else ("conflict" if item and (item.get("conflict") or item.get("content_conflict")) else "active")
                row["digest"] = _digest(item or base or user["items"][ref])
                row["baseline_ref"] = selected_ref if base else None
                row["enabled"] = not removed and ref in enabled
                row["enabled_override"] = overrides.get(ref)
                row["revision"] = revision
                rows.append(row)
            return rows

    def show(self, ref: str, view: str = "effective") -> dict[str, Any]:
        if view not in {"effective", "installed", "change", "diff", "history"}:
            raise ValidationError("unknown corpus view")
        with self._lock():
            self._recover_locked()
            runtime, user = self._runtime_state(), self._user_state()
            baseline_ref, inventory, _defaults = self._selected_baseline(runtime)
            base = next((self._validate_item(x, allow_origin=True) for x in inventory["items"] if x.get("ref") == ref), None)
            learning_host = self._learning_host_from_ref(ref)
            effective = {x["ref"]: x for x in self._effective_items(runtime, user, host=learning_host, include_suppressed=learning_host is not None)[0]}.get(ref)
            if base is None and ref not in user["items"] and effective is None:
                raise ValidationError(f"unknown corpus ref: {ref}")
            if view == "installed":
                return {"ref": ref, "baseline_ref": baseline_ref, "item": base}
            if view == "change":
                return {"ref": ref, "override": user["overrides"].get(ref), "tombstone": user["tombstones"].get(ref), "personal": user["items"].get(ref)}
            if view == "diff":
                return {"ref": ref, "installed": base, "effective": effective, "change": user["overrides"].get(ref), "removed": ref in user["tombstones"]}
            if view == "history":
                return {"ref": ref, "history": self.history(ref)}
            removed = ref in user["tombstones"] or (effective is not None and effective.get("active", True) is False)
            state = "removed" if removed else ("conflict" if effective and (effective.get("conflict") or effective.get("content_conflict")) else "active")
            overrides = self._enabled_overrides(user)
            enabled = bool(effective and not removed and self._selected_items(
                [effective], self._effective_selection(user, _defaults, None), overrides))
            return {"ref": ref, "item": effective, "digest": _digest(effective) if effective else None, "state": state,
                    "enabled": enabled, "enabled_override": overrides.get(ref)}

    # ---- plans --------------------------------------------------------------

    def _next_personal_id(self, user: dict[str, Any]) -> str:
        """Allocate against retained sources and plans, including retired identities."""
        issued = set(user["items"])
        for path in (self.user_root / "history").glob("*/state.json"):
            record = _json_read(path)
            issued.update((record.get("user") or {}).get("items", {}))
        for path in (self.runtime / "transactions").glob("*/journal.json"):
            record = _json_read(path)
            plan = record.get("plan") or {}
            issued.update(((plan.get("after") or {}).get("user") or {}).get("items", {}))
            if ref := (plan.get("details") or {}).get("ref"):
                issued.add(ref)
        for _attempt in range(16):
            item_id = f"personal-{uuid.uuid4().hex}"
            if f"{LOCAL_PACKAGE}:{item_id}" not in issued:
                return item_id
        raise CorpusStoreError("could not allocate an unused personal identity")

    def _prepare_operation(self, payload: dict[str, Any], runtime: dict[str, Any], user: dict[str, Any],
                           *, allocated_item_id: str | None = None,
                           allocated_item_ids: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValidationError("plan payload must be an object")
        op = payload.get("operation", payload.get("op"))
        if not isinstance(op, str) or op not in {"create", "update", "remove", "restore", "recover", "reset", "rollback", "select", "enable", "import"}:
            raise ValidationError("unknown corpus operation")
        allowed = {
            "create": {"operation", "op", "item", "package_id", "expected_revision"},
            "update": {"operation", "op", "ref", "patch", "item_digest", "expected_revision"},
            "remove": {"operation", "op", "ref", "item_digest", "expected_revision"},
            "restore": {"operation", "op", "ref", "expected_revision"},
            "recover": {"operation", "op", "ref", "expected_revision"},
            "reset": {"operation", "op", "expected_revision"},
            "rollback": {"operation", "op", "baseline_ref", "history_id", "expected_revision"},
            "select": {"operation", "op", "selection", "selection_mode", "expected_revision"},
            "enable": {"operation", "op", "items", "expected_revision"},
            "import": {"operation", "op", "capture_id", "candidates", "excluded", "expected_revision"},
        }[op]
        unknown = set(payload) - allowed
        if unknown:
            raise ValidationError(f"unknown plan fields: {', '.join(sorted(unknown))}")
        current = self._authoring_revision(runtime, user)
        given = payload.get("expected_revision")
        if given is not None and given != current:
            raise StaleRevision(f"expected revision {given} is stale; current is {current}")
        next_runtime, next_user = _copy_json(runtime), _copy_json(user)
        items, inventory, defaults, _baseline_ref = self._effective_items(runtime, user)
        effective = {item["ref"]: item for item in items}
        details: dict[str, Any] = {"operation": op}
        if op == "import":
            import importlib
            name = "compose.corpus_import" if __package__ else "corpus_import"
            prepared_import = importlib.import_module(name).prepare_items(self, payload, user)
            refs = prepared_import["existing_refs"]
            receipt = prepared_import["receipt"]
            rows = prepared_import["items"]
            if rows:
                if allocated_item_ids is None or len(allocated_item_ids) != len(rows):
                    raise ValidationError("import needs recorded runtime-owned identities")
                refs = []
                for raw, item_id in zip(rows, allocated_item_ids):
                    _safe_part(item_id, "personal item id")
                    raw = _copy_json(raw)
                    raw.update(package_id=LOCAL_PACKAGE, item_id=item_id, ref=f"{LOCAL_PACKAGE}:{item_id}")
                    item = self._validate_item(self._normalize_content(raw), allow_origin=True)
                    if item["ref"] in effective or item["ref"] in next_user["items"]:
                        raise ValidationError("import identity is already in use")
                    next_user["items"][item["ref"]] = item
                    refs.append(item["ref"])
                receipt["refs"] = refs
                receipt["item_digests"] = {ref: _digest(next_user["items"][ref]) for ref in refs}
                next_user.setdefault("imports", {})[receipt["request_digest"]] = receipt
            details.update(refs=refs, import_receipt=receipt, already_imported=not bool(rows))
        elif op == "create":
            raw = _copy_json(payload.get("item"))
            if not isinstance(raw, dict):
                raise ValidationError("create needs item")
            if set(raw) & {"item_id", "ref", "content_conflict", "conflict"}:
                raise ValidationError("creation identity and conflict metadata are runtime-owned")
            if allocated_item_id is None:
                raise ValidationError("creation needs a recorded runtime-owned identity")
            package = payload.get("package_id", raw.get("package_id", LOCAL_PACKAGE))
            if package != LOCAL_PACKAGE:
                raise ValidationError("V1 creation targets @local/personal")
            raw["package_id"] = LOCAL_PACKAGE
            raw["item_id"] = allocated_item_id
            raw["ref"] = f"{LOCAL_PACKAGE}:{raw['item_id']}"
            raw.setdefault("surface", "requested")
            raw.setdefault("tier", "env-personal")
            raw.setdefault("domains", ["personal"])
            raw.setdefault("kind", "rule")
            if "members" not in raw:
                raw.setdefault("body", "")
                raw["members"] = {"content.md": raw["body"]}
                raw["primary_member"] = "content.md"
            elif "body" not in raw:
                primary = raw.get("primary_member")
                if not isinstance(raw["members"], dict) or not isinstance(primary, str) or primary not in raw["members"]:
                    raise ValidationError("members-only creation needs primary_member")
                raw["body"] = raw["members"][primary]
            try:
                item = self._validate_item(self._normalize_content(raw, allow_legacy=True))
                self._require_resolved([item])
                if "body" in payload["item"] and item["body"] != raw["body"]:
                    raise ValidationError("body conflicts with primary_member member content")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            if item["kind"] not in {"rule", "guide", "skill"}:
                raise ValidationError("V1 personal creation supports rule, guide, and skill items")
            if item["ref"] in effective or item["ref"] in next_user["items"]:
                raise ValidationError(f"corpus ref already exists: {item['ref']}")
            next_user["items"][item["ref"]] = item
            details.update({"ref": item["ref"], "item_digest": _digest(item)})
        elif op == "update":
            ref = payload.get("ref")
            if isinstance(ref, str) and ref not in effective:
                learning_host = self._learning_host_from_ref(ref)
                if learning_host is not None:
                    effective = {item["ref"]: item for item in self._effective_items(runtime, user, host=learning_host, include_suppressed=True)[0]}
            if not isinstance(ref, str) or ref not in effective:
                raise ValidationError("update needs an active corpus ref")
            item = effective[ref]
            supplied_digest = payload.get("item_digest")
            item_digest = _digest(item)
            if not isinstance(supplied_digest, str) or supplied_digest != item_digest:
                raise StaleRevision(f"item digest for {ref} is stale")
            patch = self._validate_patch(payload.get("patch"))
            try:
                candidate = self._validate_item(self._catalog_module().update_content(item, patch), allow_origin=True)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            self._require_resolved([candidate])
            if ref in next_user["items"]:
                next_user["items"][ref] = candidate
            else:
                base = next((row for row in inventory["items"] if row["ref"] == ref), None)
                if base is None:
                    host = self._learning_host_from_ref(ref)
                    event = next(event for event in self._learning_events(host)
                                 if f"@local/learnings-{host}:{event['learning_id']}" == ref)
                    base = self._learning_item(host, event)
                normalized_base = self._normalize_content(base, allow_legacy=True)
                delta = {field: value for field, value in candidate.items()
                         if field in ITEM_FIELDS and value != normalized_base.get(field)}
                if delta:
                    next_user["overrides"][ref] = {"base_digest": _digest(base), "patch": delta}
                else:
                    next_user["overrides"].pop(ref, None)
            details.update({"ref": ref, "prior_item_digest": item_digest, "item_digest": _digest(candidate)})
        elif op == "remove":
            ref = payload.get("ref")
            if isinstance(ref, str) and ref not in effective:
                learning_host = self._learning_host_from_ref(ref)
                if learning_host is not None:
                    effective = {item["ref"]: item for item in self._effective_items(runtime, user, host=learning_host, include_suppressed=True)[0]}
            if not isinstance(ref, str) or ref not in effective:
                raise ValidationError("remove needs an active corpus ref")
            supplied_digest = payload.get("item_digest")
            if supplied_digest is not None and supplied_digest != _digest(effective[ref]):
                raise StaleRevision(f"item digest for {ref} is stale")
            if ref in next_user["items"]:
                next_user["items"][ref]["active"] = False
            else:
                # The plan must have a stable result digest.  Audit time belongs in
                # its journal, not in authoring state that is recomputed at Apply.
                next_user["tombstones"][ref] = {"base_digest": _digest(effective[ref])}
            details["ref"] = ref
        elif op == "restore":
            ref = payload.get("ref")
            if not isinstance(ref, str):
                raise ValidationError("restore needs corpus ref")
            if ref not in {x.get("ref") for x in inventory.get("items", [])}:
                raise ValidationError("restore is available only for selected installed baseline items")
            next_user["overrides"].pop(ref, None)
            next_user["tombstones"].pop(ref, None)
            details["ref"] = ref
        elif op == "recover":
            ref = payload.get("ref")
            learning_host = self._learning_host_from_ref(ref) if isinstance(ref, str) else None
            if learning_host is not None:
                event = next((event for event in self._learning_events(learning_host)
                              if f"@local/learnings-{learning_host}:{event['learning_id']}" == ref), None)
                if event is None:
                    raise ValidationError("recover needs personal corpus ref")
                next_user["tombstones"].pop(ref, None)
                suppressions = next_user.setdefault("learning_suppressions", {}).setdefault(learning_host, [])
                if _digest(event) in suppressions:
                    suppressions.remove(_digest(event))
            elif not isinstance(ref, str) or ref not in next_user["items"]:
                raise ValidationError("recover needs personal corpus ref")
            else:
                next_user["items"][ref].pop("active", None)
            details["ref"] = ref
        elif op == "enable":
            choices = payload.get("items")
            if not isinstance(choices, dict) or not choices:
                raise ValidationError("enable needs a non-empty mapping of refs to booleans or null")
            available = dict(effective)
            for host in ("claude", "codex"):
                available.update({item["ref"]: item for item in self._effective_items(runtime, user, host=host)[0]})
            overrides = dict(self._enabled_overrides(user))
            known = set(available) | set(overrides) | set(user["items"]) | {item["ref"] for item in inventory["items"]}
            for ref, value in choices.items():
                if not isinstance(ref, str) or ref not in known:
                    raise ValidationError(f"unknown corpus enablement ref: {ref}")
                if value is None:
                    overrides.pop(ref, None)
                elif not isinstance(value, bool):
                    raise ValidationError("enable values must be booleans or null")
                elif ref not in available or available[ref].get("active", True) is False:
                    raise ValidationError("recover or restore a removed item before enabling it")
                else:
                    overrides[ref] = value
            if overrides:
                next_user["enabled_overrides"] = overrides
            else:
                next_user.pop("enabled_overrides", None)
            details["items"] = _copy_json(choices)
        elif op == "select":
            selection = self._validate_selection(payload.get("selection"), inventory)
            if "selection_mode" in payload:
                if payload["selection_mode"] is None:
                    raise ValidationError("selection_mode cannot be null")
                mode = self._selection_mode({}, {}, payload["selection_mode"])
                if mode == "none" and selection:
                    raise ValidationError("no-corpus selection cannot include targets")
                next_user["selection_mode"] = mode
                details["selection_mode"] = mode
            next_user["selection"] = selection
            details["selection"] = selection
        elif op == "reset":
            suppressions = {host: [_digest(event) for event in self._learning_events(host)]
                            for host in ("claude", "codex")}
            next_user = self._empty_user()
            next_user["learning_suppressions"] = suppressions
            latest = next_runtime.get("last_successful_install_ref")
            if not latest:
                raise CorpusStoreError("cannot reset before install")
            next_runtime["selected_baseline_ref"] = latest
            _inv, latest_defaults = self._read_baseline(latest)
            next_user["selection"] = latest_defaults.get("selection")
            if "selection_mode" in latest_defaults:
                next_user["selection_mode"] = latest_defaults["selection_mode"]
            details["baseline_ref"] = latest
        elif op == "rollback":
            history_id = payload.get("history_id")
            baseline_ref = payload.get("baseline_ref")
            if history_id is not None:
                _safe_part(history_id, "history id")
                record = _json_read(self.user_root / "history" / str(history_id) / "state.json")
                if not isinstance(record, dict) or "user" not in record or "runtime" not in record:
                    raise ValidationError("unknown rollback history")
                next_user = record["user"]
                # History rollback replays authoring state but preserves the current successful-install pointer.
                next_runtime["selected_baseline_ref"] = record["runtime"].get("selected_baseline_ref")
                self._read_baseline(next_runtime["selected_baseline_ref"])
                details["history_id"] = history_id
            else:
                if not isinstance(baseline_ref, str):
                    raise ValidationError("rollback needs baseline_ref or history_id")
                target, _target_defaults = self._read_baseline(baseline_ref)
                next_user = self._rebase_overlays(inventory, target, next_user)
                next_runtime["selected_baseline_ref"] = baseline_ref
                details["baseline_ref"] = baseline_ref
        return next_runtime, next_user, details

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock():
            self._recover_locked()
            runtime, user = self._runtime_state(), self._user_state()
            before = self._authoring_revision(runtime, user)
            op = payload.get("operation", payload.get("op")) if isinstance(payload, dict) else None
            allocated = self._next_personal_id(user) if op == "create" else None
            allocated_many = None
            if op == "import":
                import importlib
                name = "compose.corpus_import" if __package__ else "corpus_import"
                importer = importlib.import_module(name)
                payload = importer.sanitize_import_payload(payload)
                prepared_import = importer.prepare_items(self, payload, user)
                allocated_many, reserved = [], _copy_json(user)
                for _item in prepared_import["items"]:
                    item_id = self._next_personal_id(reserved)
                    allocated_many.append(item_id)
                    reserved["items"][f"{LOCAL_PACKAGE}:{item_id}"] = {}
            next_runtime, next_user, details = self._prepare_operation(payload, runtime, user, allocated_item_id=allocated,
                                                                      allocated_item_ids=allocated_many)
            self._validate_candidate_projection(next_runtime, next_user)
            after = self._authoring_revision(next_runtime, next_user)
            plan_id = uuid.uuid4().hex
            plan = {
                "schema_version": SCHEMA_VERSION, "plan_id": plan_id, "created_at": _utcnow(),
                "expected_revision": before, "result_revision": after, "payload": _copy_json(payload),
                "details": details, "before": {"runtime": runtime, "user": user},
                "after": {"runtime": next_runtime, "user": next_user},
            }
            if allocated is not None:
                plan["allocated_item_id"] = allocated
            if allocated_many is not None:
                plan["allocated_item_ids"] = allocated_many
            self._write_transaction(plan_id, {"state": "PLANNED", "plan": plan})
            return {key: plan[key] for key in ("schema_version", "plan_id", "expected_revision", "result_revision", "details")}

    def apply(self, plan_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        _safe_part(plan_id, "plan id")
        with self._lock():
            self._recover_locked()
            journal_path = self.runtime / "transactions" / plan_id / "journal.json"
            journal = _json_read(journal_path)
            if not isinstance(journal, dict):
                raise ValidationError("plan is unknown")
            if journal.get("state") in {"COMMITTED", "RECOVERED_COMMITTED"} and journal.get("kind") != "install":
                return self._applied_result(journal)
            if journal.get("state") != "PLANNED" or journal.get("kind") == "install":
                raise ValidationError("plan is not ready for apply")
            plan = journal.get("plan")
            if not isinstance(plan, dict):
                raise CorpusStoreError("invalid plan journal")
            runtime, user = self._runtime_state(), self._user_state()
            current = self._authoring_revision(runtime, user)
            expected = expected_revision if expected_revision is not None else plan.get("expected_revision")
            if expected != current or plan.get("expected_revision") != current:
                raise StaleRevision(f"plan {plan_id} is stale; current revision is {current}")
            # Recalculate from payload under the lock; journal after-state is a preview, not authority.
            allocated = plan.get("allocated_item_id")
            if allocated is None and plan["payload"].get("operation", plan["payload"].get("op")) == "create":
                # Persisted pre-allocation plans already resolved their identity in after-state.
                ref = plan.get("details", {}).get("ref")
                allocated = ref.split(":", 1)[1] if isinstance(ref, str) and ref.startswith(LOCAL_PACKAGE + ":") else None
            next_runtime, next_user, details = self._prepare_operation(plan["payload"], runtime, user, allocated_item_id=allocated,
                                                                      allocated_item_ids=plan.get("allocated_item_ids"))
            self._validate_candidate_projection(next_runtime, next_user)
            result = self._authoring_revision(next_runtime, next_user)
            if result != plan.get("result_revision"):
                raise CorpusStoreError("plan result changed during apply")
            if details.get("operation") == "import":
                import importlib
                name = "compose.corpus_import" if __package__ else "corpus_import"
                importlib.import_module(name).verify_import_sources(self, details)
            prepared = {"state": "PREPARED", "plan": plan, "prior_revision": current, "prepared_at": _utcnow()}
            history_id = f"{prepared['prepared_at'].replace(':', '').replace('+00:00', 'Z')}-{plan_id[:12]}"
            prepared["history_id"] = history_id
            self._write_transaction(plan_id, prepared)
            _atomic_write(self.user_root / "history" / history_id / "state.json",
                          {"runtime": runtime, "user": user, "revision": current, "details": details})
            if details.get("operation") == "reset":
                _atomic_write(self.user_root / "trash" / history_id / "state.json", {"runtime": runtime, "user": user, "revision": current})
            _atomic_write(self._user_state_path, next_user)
            _atomic_write(self._runtime_state_path, next_runtime)
            committed = {"state": "COMMITTED", "plan": plan, "history_id": history_id, "revision": result, "committed_at": _utcnow()}
            self._write_transaction(plan_id, committed)
            return {"plan_id": plan_id, "history_id": history_id, "revision": result, "details": details}

    @staticmethod
    def _applied_result(journal: dict[str, Any]) -> dict[str, Any]:
        plan = journal["plan"]
        return {"plan_id": plan["plan_id"], "history_id": journal["history_id"],
                "revision": plan["result_revision"], "details": plan["details"]}

    # ---- immutable snapshots and history -----------------------------------

    def _selected_items(self, items: list[dict[str, Any]], selection: list[str] | None,
                        overrides: dict[str, bool] | None = None, *, mode: str = "default",
                        host: str | None = None, cwd: str | Path | None = None) -> list[dict[str, Any]]:
        self._selection_mode({}, {}, mode)
        if mode == "none":
            return []
        overrides = overrides or {}
        working = Path(cwd or Path.cwd()).resolve()
        selected: list[dict[str, Any]] = []
        for item in items:
            origin = item.get("origin", {})
            if origin.get("type") == "instruction_import":
                scope = origin.get("scope", {})
                if not isinstance(scope, dict) or scope.get("kind") not in {"global", "project"}:
                    raise ValidationError("imported item has invalid source scope")
                hosts = origin.get("hosts", ["claude", "codex"])
                if not isinstance(hosts, list) or not hosts or any(value not in {"claude", "codex"} for value in hosts):
                    raise ValidationError("imported item has invalid host scope")
                if host is not None and host not in hosts:
                    continue
                if scope["kind"] == "project":
                    root = scope.get("root")
                    if not isinstance(root, str) or not Path(root).is_absolute():
                        raise ValidationError("imported project root must be absolute")
                    project_root = Path(root)
                    if project_root.resolve() != project_root:
                        raise ValidationError("imported project root is no longer canonical; review its scope")
                    if not working.is_relative_to(project_root):
                        continue
            if item["ref"] in overrides and (mode == "default" or overrides[item["ref"]] is False):
                if overrides[item["ref"]]:
                    selected.append(item)
                continue
            if selection and "all" in selection:
                selected.append(item)
                continue
            if mode == "default" and item.get("tier") in {"core", "infra"}:
                selected.append(item)
                continue
            if not selection:
                continue
            if item["ref"] in selection or item["package_id"] in selection:
                selected.append(item)
                continue
            if any(f"{item['package_id']}/{domain}" in selection for domain in item.get("domains", [])):
                selected.append(item)
        return selected

    def snapshot(self, host: str, selection: list[str] | None = None, dry_run: bool = False,
                 native: bool = False, *, selection_mode: str | None = None,
                 cwd: str | Path | None = None) -> dict[str, Any]:
        """Compose an immutable activated-session snapshot.

        A dry run has no durable write path: it compiles in an OS temporary
        directory and rewrites only the returned private paths to their future
        content-addressed destination.  The ContentRef is therefore the same
        value Apply/launch will later publish.
        """
        _host(host)
        if not isinstance(native, bool):
            raise ValidationError("native activation must be boolean")
        if dry_run and not self._runtime_state_path.is_file():
            raise CorpusStoreError("no installed baseline; run install first")
        lock = transaction_lock(self.state_root) if dry_run else self._lock()
        with lock:
            guard_pending(self.state_root)
            if dry_run and pending_operations(self.state_root):
                raise CorpusStoreError("source transaction needs recovery before snapshot preview")
            if not dry_run:
                self._recover_locked()
            runtime, user = self._runtime_state(), self._user_state()
            items, inventory, defaults, baseline_ref = self._effective_items(runtime, user, host=host)
            active = [item for item in items if item.get("active", True) is not False]
            effective_selection = self._effective_selection(user, defaults, selection)
            mode = self._selection_mode(user, defaults, selection_mode)
            if selection is not None and selection_mode is None and mode == "none":
                mode = "default"
            if mode == "none":
                effective_selection = []
            working = Path(cwd or Path.cwd()).resolve()
            self._validate_snapshot_selection(effective_selection, inventory,
                                              self._selection_subjects(runtime, user, active, effective_selection))
            selected = self._selected_items(active, effective_selection, self._enabled_overrides(user),
                                            mode=mode, host=host, cwd=working)
            self._require_resolved(selected)
            selected, promotion_warnings = self._resolve_promotions(selected, user, host, baseline_ref)
            bootstrap_path = self.repo / "compose" / "bootstrap" / "SKILL.md"
            if not bootstrap_path.is_file():
                raise CorpusStoreError("private management bootstrap is missing")
            catalog_path = self.repo / "compose" / "corpus_catalog.py"
            inputs = {
                "schema_version": SCHEMA_VERSION, "host": host, "baseline_ref": baseline_ref,
                "selection": effective_selection,
                "selection_mode": mode, "cwd": str(working),
                "selection_digest": _digest(effective_selection),
                "authoring_revision": self._authoring_revision(runtime, user),
                "item_digests": {item["ref"]: _digest(item) for item in sorted(selected, key=lambda x: x["ref"])},
                "learning_digest": _digest(self._learning_events(host)),
                "promotion_digest": _digest(self._baseline_promotions(baseline_ref)),
                "compiler_digest": _digest(catalog_path.read_bytes()) if catalog_path.is_file() else None,
                "store_schema_digest": _digest(Path(__file__).read_bytes()),
                "bootstrap_digest": _digest(bootstrap_path.read_bytes()),
            }
            if native:
                import sys
                inputs["native"] = True
                inputs["native_python"] = sys.executable
            content_ref = _digest(inputs)
            root = self.sessions / "snapshots" / content_ref
            _reject_symlink_path(self.sessions)
            _reject_symlink_path(self.sessions / "snapshots")
            catalog = self._catalog_module()
            if not hasattr(catalog, "compile_items"):
                raise CorpusStoreError("corpus catalog has no compile_items")
            if not dry_run and (root / "inventory.json").exists():
                verified = verify_snapshot(root, content_ref)
                if verified["inputs"] != inputs:
                    raise CorpusStoreError(f"immutable snapshot collision: {content_ref}")
                output = verified["output"]
            else:
                if dry_run:
                    temp = tempfile.TemporaryDirectory(prefix="agent-bios-snapshot-")
                    staging = Path(temp.name) / "snapshot"
                    staging.mkdir()
                else:
                    temp = None
                    staging = root.with_name(f".{root.name}.staging-{uuid.uuid4().hex}")
                    staging.mkdir(parents=True, exist_ok=False)
                try:
                    compiled = catalog.compile_items(_copy_json(selected), staging, host, native=True, reference_root=root) if native else catalog.compile_items(_copy_json(selected), staging, host)
                    if not isinstance(compiled, dict) or not isinstance(compiled.get("instruction_text"), str):
                        raise CorpusStoreError("catalog compiler returned invalid output")
                    files = _snapshot_relative_paths(compiled.get("files"))
                    output = {
                        "instruction_text": compiled.get("instruction_text", ""),
                        "files": sorted(set(files) | ({"bootstrap/SKILL.md"} if mode != "none" else set())), "item_refs": compiled.get("item_refs", []),
                        "unavailable": compiled.get("unavailable", []) + promotion_warnings,
                    }
                    assets = _snapshot_assets(compiled.get("assets", {}), files)
                    if assets:
                        output["assets"] = assets
                    invocation = (f"Corpus management: invoke $agent-bios using {root / 'bootstrap' / 'SKILL.md'}."
                                  if mode != "none" else "")
                    if mode == "none":
                        output["instruction_text"] = ""
                        for relative in files:
                            if relative == "launch-content/instructions.md":
                                (staging / relative).write_text("", encoding="utf-8")
                    else:
                        output["instruction_text"] = output["instruction_text"].rstrip() + "\n\n" + invocation + "\n"
                    for plugin in assets.get("claude_plugins", []):
                        for agent_path in (staging / plugin / "agents").glob("*.md"):
                            with agent_path.open("a", encoding="utf-8") as agent_file:
                                agent_file.write("\n\n" + invocation + "\n")
                    if dry_run:
                        output["instruction_text"] = output["instruction_text"].replace(str(staging), str(root))
                    else:
                        if mode != "none":
                            bootstrap_target = staging / "bootstrap" / "SKILL.md"
                            bootstrap_target.parent.mkdir(parents=True, exist_ok=True)
                            bootstrap_target.write_bytes(bootstrap_path.read_bytes())
                        _rewrite_staged_paths(staging, root)
                        output["instruction_text"] = output["instruction_text"].replace(str(staging), str(root))
                        _atomic_write(staging / "inventory.json", {"inputs": inputs, "items": selected})
                        _atomic_write(staging / "output.json", output)
                        digests = _snapshot_file_digests(staging, output["files"])
                        _atomic_write(staging / "inventory.json", {"inputs": inputs, "items": selected, "file_digests": digests})
                    # A directory rename is the publication point; no consumer sees a partial snapshot.
                    if not dry_run:
                        root.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            os.replace(staging, root)
                        except FileExistsError:
                            if verify_snapshot(root, content_ref)["inputs"] != inputs:
                                raise CorpusStoreError(f"immutable snapshot collision: {content_ref}")
                finally:
                    if temp is not None:
                        temp.cleanup()
                    elif staging.exists():
                        import shutil
                        shutil.rmtree(staging)
            return {"content_ref": content_ref, "path": str(root), "instruction_text": output["instruction_text"],
                    "revision": inputs["authoring_revision"], "unavailable": output.get("unavailable", []),
                    "item_refs": output.get("item_refs", []), "selection_mode": mode,
                    "assets": output.get("assets", {})}

    def history(self, ref: str | None = None) -> list[dict[str, Any]]:
        root = self.user_root / "history"
        if not root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(root.glob("*/state.json"), reverse=True):
            record = _json_read(path)
            if not isinstance(record, dict):
                continue
            if ref is not None:
                user = record.get("user", {})
                details = record.get("details", {})
                changed = details.get("items", {}) if details.get("operation") == "enable" else {}
                if (ref not in user.get("items", {}) and ref not in user.get("overrides", {})
                        and ref not in user.get("tombstones", {}) and ref not in user.get("enabled_overrides", {})
                        and ref not in changed):
                    continue
            rows.append({"history_id": path.parent.name, "revision": record.get("revision"), "path": str(path.parent)})
        return rows

    def snapshot_inventory(self, content_ref: str) -> dict[str, Any]:
        """Read a pinned snapshot by ContentRef without resolving current state."""
        _safe_part(content_ref, "content ref")
        with self._lock():
            self._recover_locked()
            root = self.sessions / "snapshots" / content_ref
            verified = verify_snapshot(root, content_ref)
            output = verified["output"]
            return {"content_ref": content_ref, "path": str(root), "inputs": verified["inputs"],
                    "items": verified["items"], "files": output.get("files"),
                    "item_refs": output.get("item_refs"), "instruction_text": output.get("instruction_text"),
                    "unavailable": output.get("unavailable"), "assets": output.get("assets", {})}

    def capture_learning(self, host: str, record: dict[str, Any]) -> dict[str, Any]:
        """Append exact captured bytes to a host-private immutable source journal."""
        _host(host)
        if not isinstance(record, dict):
            raise ValidationError("learning capture must be an object")
        event = _copy_json(record)
        unknown = set(event) - LEARNING_FIELDS
        required = {"schema_version", "learning_id", "lesson", "domain", "created", "supporting_sessions"}
        if unknown or not required <= set(event):
            raise ValidationError("learning record must use the collector v1 schema exactly")
        if event["schema_version"] != 1 or not isinstance(event["learning_id"], str) or not LEARNING_ID_RE.fullmatch(event["learning_id"]):
            raise ValidationError("invalid collector learning identity")
        if not isinstance(event["lesson"], str) or not isinstance(event["domain"], str) or not isinstance(event["created"], str):
            raise ValidationError("invalid collector learning content")
        sessions = event["supporting_sessions"]
        if not isinstance(sessions, list) or not sessions or not all(isinstance(value, str) for value in sessions):
            raise ValidationError("invalid collector learning provenance")
        path = self.user_root / "learnings" / host / "events.jsonl"
        with self._lock():
            self._recover_locked()
            prior = self._learning_events(host)
            if any(x.get("learning_id") == event["learning_id"] for x in prior):
                raise ValidationError("learning_id already captured")
            _reject_symlink_path(path, leaf=False)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Append is atomic under the store lock and fsync makes the capture durable before return.
            with path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical(event).decode("utf-8") + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return {"host": host, "learning_id": event["learning_id"], "digest": _digest(event), "revision": self._authoring_revision(self._runtime_state(), self._user_state())}
