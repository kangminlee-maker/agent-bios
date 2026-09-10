#!/usr/bin/env python3
"""Private corpus installation and explicit legacy migration.

This command owns package-at-rest installation.  It deliberately has no host
activation path: an installed corpus is stored and verifiable, while a launcher
activation creates the per-session snapshot and pin.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import sys
import tempfile
import time
import tomllib
import uuid
from typing import Any

from corpus_transaction import (
    _valid_release,
    TransactionError,
    guard_pending,
    operation_scope,
    operation_scope_active,
    pending_status,
    reject_symlink_ancestors,
    transaction_lock,
)


SCHEMA_VERSION = 1
PRIVATE_RECORD = "private-install.json"
CENTRAL_START = "<!-- agent-bios:central:start -->"
CENTRAL_END = "<!-- agent-bios:central:end -->"
PERSONAL_START = "<!-- agent-bios:personal-learnings:start -->"
PERSONAL_END = "<!-- agent-bios:personal-learnings:end -->"
CLAUDE_IMPORTS = frozenset(("@central/bundle.md", "@personal/learnings.md"))
ZSH_HOOK = '[ -r "$HOME/.config/agent-launch/shell.zsh" ] && source "$HOME/.config/agent-launch/shell.zsh"'
LEARNING_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class InstallError(RuntimeError):
    pass


def _serialized(method):
    """Keep installer metadata and its owned paths one transaction at a time."""
    def wrapped(self, *args, **kwargs):
        name = method.__name__
        dry = bool(kwargs.get("dry_run", False))
        if name == "install" and len(args) >= 2:
            dry = dry or bool(args[1])
        elif name in {"uninstall"} and args:
            dry = dry or bool(args[0])
        apply = bool(args[0]) if args and name in {"migrate", "reset"} else bool(kwargs.get("apply", False))
        if name == "status" or dry or (name in {"migrate", "reset"} and not apply):
            return method(self, *args, **kwargs)
        with self._installer_lock():
            if name in {"install", "uninstall", "reset"} and not operation_scope_active(self.state_root):
                if any(row["kind"] == "migrate" for row in pending_status(self.state_root)["transactions"]):
                    raise InstallError("pending migration requires agent-bios migrate --apply --yes before other writes")
            return method(self, *args, **kwargs)
    return wrapped


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise InstallError(f"refusing symlink output: {path}")
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        if mode is not None:
            temporary.chmod(mode)
        elif path.exists():
            temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_bytes(path, _canonical(value) + b"\n", 0o600)


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"missing or unsafe JSON record: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError(f"cannot read JSON record {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError(f"JSON record must be an object: {path}")
    return data


def _relative(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise InstallError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value.rstrip("/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise InstallError(f"unsafe {label}: {value!r}")
    return path.as_posix()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.absolute().relative_to(root.absolute())
        return True
    except ValueError:
        return False


def _active_import_lines(body: str) -> list[int]:
    """Line numbers of real import directives, excluding fenced examples."""
    result: list[int] = []
    fenced = False
    for index, line in enumerate(body.splitlines(keepends=True)):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if not fenced and stripped in CLAUDE_IMPORTS:
            result.append(index)
    return result


def _remove_claude_imports(body: str) -> tuple[str, list[str]]:
    lines = body.splitlines(keepends=True)
    indexes = set(_active_import_lines(body))
    removed = [lines[index].strip() for index in sorted(indexes)]
    return "".join(line for index, line in enumerate(lines) if index not in indexes), removed


def _remove_spans(body: str) -> tuple[str | None, list[str]]:
    """Strip exact, non-overlapping managed marker spans or report ambiguity."""
    spans = ((CENTRAL_START, CENTRAL_END, "central"), (PERSONAL_START, PERSONAL_END, "personal-learnings"))
    found: list[tuple[int, int, str]] = []
    for start, end, label in spans:
        starts = [index for index in range(len(body)) if body.startswith(start, index)]
        ends = [index for index in range(len(body)) if body.startswith(end, index)]
        if not starts and not ends:
            continue
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            return None, [f"malformed {label} marker span"]
        found.append((starts[0], ends[0] + len(end), label))
    if len(found) == 2 and not (found[0][1] <= found[1][0] or found[1][1] <= found[0][0]):
        return None, ["overlapping managed marker spans"]
    text = body
    removed: list[str] = []
    for start, end, label in sorted(found, reverse=True):
        text = text[:start] + text[end:]
        removed.append(label)
    return text.lstrip("\n"), list(reversed(removed))


def _strip_codex_config_additions(body: str) -> tuple[str | None, bool]:
    """Remove only the exact legacy config block and tagged feature line."""
    begin, end, tag = "# >>> agent-bios additions >>>", "# <<< agent-bios additions <<<", "# agent-bios"
    starts = body.count(begin)
    ends = body.count(end)
    if starts != ends or starts > 1:
        return None, False
    skipping = False
    changed = False
    lines: list[str] = []
    for line in body.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == begin:
            skipping, changed = True, True
            continue
        if stripped == end:
            skipping = False
            continue
        if skipping:
            continue
        if stripped.endswith(tag) and "multi_agent" in stripped:
            changed = True
            continue
        lines.append(line)
    result = "".join(lines)
    if changed:
        try:
            tomllib.loads(result)
        except tomllib.TOMLDecodeError:
            return None, False
    return result, changed


class CorpusInstaller:
    """Private install state plus carefully scoped legacy cleanup."""

    def __init__(self, repo: Path, environ: dict[str, str] | None = None):
        self.repo = Path(repo).resolve()
        self.env = dict(os.environ if environ is None else environ)
        home = Path(self.env.get("HOME", str(Path.home()))).expanduser()
        self.state_root = Path(self.env.get("AGENT_BIOS_STATE_DIR", str(home / ".local/share/agent-bios"))).expanduser()
        self.user_root = Path(self.env.get("AGENT_BIOS_CORPUS_DIR", str(home / ".config/agent-bios/corpus"))).expanduser()
        self.claude_root = Path(self.env.get("CLAUDE_CONFIG_DIR", str(home / ".claude"))).expanduser()
        self.codex_root = Path(self.env.get("CODEX_HOME", str(home / ".codex"))).expanduser()
        self.zdotdir = Path(self.env.get("ZDOTDIR", str(home))).expanduser()
        self.launch_root = home / ".config" / "agent-launch"
        self.bin_root = home / ".local" / "bin"
        self._installer_lock_depth = 0

    @property
    def runtime(self) -> Path:
        return self.state_root / "runtime"

    @property
    def record_path(self) -> Path:
        return self.runtime / PRIVATE_RECORD

    @contextlib.contextmanager
    def _installer_lock(self):
        """Use the store's lock; lock ordering cannot diverge by caller."""
        try:
            with transaction_lock(self.state_root):
                yield
        except TransactionError as exc:
            raise InstallError(str(exc)) from exc

    def _package_manifest(self) -> dict[str, Any]:
        return _read_json(self.repo / "package.json")

    def _package_files(self) -> list[str]:
        manifest = self._package_manifest()
        listed = manifest.get("files")
        if not isinstance(listed, list) or not listed:
            raise InstallError("package.json files must declare the private runtime payload")
        paths: set[str] = {"package.json"}  # npm includes this manifest even when files[] omits it.
        prohibited = ("gates/", "design/", "benchmarks/", "research/", "packages/", "session-distill/")
        for raw in listed:
            relative = _relative(raw, "package files entry")
            if relative.startswith(prohibited):
                raise InstallError(f"author-only path is not a private runtime payload: {relative}")
            source = self.repo / relative
            # npm's prepack stamps this author-side provenance receipt.  A
            # checkout after postpack legitimately lacks it and no private
            # runtime path consumes it, so it is not an installation blocker.
            if relative == "provenance.json" and not source.exists():
                continue
            if source.is_symlink() or not source.exists():
                raise InstallError(f"declared package file is missing or symlinked: {relative}")
            if source.is_file():
                paths.add(relative)
                continue
            if not source.is_dir():
                raise InstallError(f"declared package entry is not file or directory: {relative}")
            for child in sorted(source.rglob("*")):
                if child.is_symlink():
                    raise InstallError(f"package payload contains symlink: {child}")
                if child.is_file():
                    child_relative = child.relative_to(self.repo).as_posix()
                    if "/test_" in child_relative or child_relative.startswith("tests/"):
                        raise InstallError(f"test file is not a runtime payload: {child_relative}")
                    paths.add(child_relative)
        return sorted(paths)

    def _release_digest(self, files: list[str]) -> str:
        digest = hashlib.sha256()
        for relative in files:
            source = self.repo / relative
            digest.update(relative.encode("utf-8") + b"\0" + source.read_bytes() + b"\0")
        return digest.hexdigest()

    def _copy_release(self, files: list[str], dry_run: bool) -> tuple[Path, list[dict[str, str]], str]:
        digest = self._release_digest(files)
        release = self.runtime / "releases" / digest
        entries = [{"path": relative, "sha256": _sha256(self.repo / relative)} for relative in files]
        if dry_run:
            return release, entries, digest
        if release.exists():
            if release.is_symlink() or not release.is_dir():
                raise InstallError(f"immutable release path is unsafe: {release}")
            self._verify_release(release, entries)
            return release, entries, digest
        release.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=release.parent))
        try:
            for entry in entries:
                source = self.repo / entry["path"]
                target = staging / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            self._verify_release(staging, entries)
            os.replace(staging, release)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return release, entries, digest

    def _verify_release(self, release: Path, entries: list[dict[str, str]]) -> None:
        for entry in entries:
            target = release / _relative(entry.get("path", ""), "installed file")
            if target.is_symlink() or not target.is_file() or _sha256(target) != entry.get("sha256"):
                raise InstallError(f"private package release drifted: {target}")

    def _private_module(self, package_root: Path, stem: str):
        compose = str(package_root / "compose")
        if compose not in sys.path:
            sys.path.insert(0, compose)
        path = package_root / "compose" / f"{stem}.py"
        if not path.is_file() or path.is_symlink():
            raise InstallError(f"private package lacks compose/{stem}.py")
        name = f"agent_bios_private_{stem}_{hashlib.sha256(str(package_root).encode()).hexdigest()[:12]}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise InstallError(f"cannot load private {stem}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def _store(self, package_root: Path):
        module = self._private_module(package_root, "corpus_store")
        store = module.CorpusStore(package_root, self.state_root, self.user_root)
        # CorpusStore delegates compile/load to a module name for normal package
        # execution. Bind this instance to the release's exact catalog so a
        # long-lived manager cannot retain an older release through sys.modules.
        store._catalog_module = lambda: self._private_module(package_root, "corpus_catalog")
        return store

    def _catalog(self, package_root: Path) -> dict[str, Any]:
        """Load the catalog from the immutable release being verified."""
        module = self._private_module(package_root, "corpus_catalog")
        return module.load_catalog(package_root)

    def _normalized_domains(self, raw: str | None) -> list[str]:
        if raw is None or raw.strip() in {"", "all"}:
            return ["all"]
        catalog_path = self.repo / "compose" / "domains.json"
        manifest = _read_json(catalog_path)
        package_id = manifest.get("package_id", "@agent-bios/core")
        known = set((manifest.get("domains") or {}).keys())
        names = [value.strip() for value in raw.split(",") if value.strip()]
        if names == ["none"]:
            return []
        if "none" in names:
            raise InstallError("--domains none must be the only selection value")
        unknown = sorted(set(names) - known)
        if unknown:
            raise InstallError(f"unknown domains: {', '.join(unknown)}")
        return [f"{package_id}/{name}" for name in sorted(set(names))]

    def _write_launcher_status(self, package_root: Path, selection: list[str]) -> None:
        """Keep the legacy launcher panel readable without claiming activation."""
        manifest = _read_json(package_root / "compose" / "domains.json")
        available = sorted((manifest.get("domains") or {}).keys())
        applied = available if selection == ["all"] else sorted(value.rsplit("/", 1)[-1] for value in selection)
        _atomic_json(self.state_root / "corpus-status.json", {
            "repo": str(package_root), "current_version": None, "latest_version": None,
            "rolled_back_to": None, "versions": None, "summary": None,
            "domains": {"available": available, "applied": applied}, "last_apply": None,
            "deployed_corpus": None, "generated": int(time.time()),
            "mode": "private-session-scoped",
        })

    def _launcher_status_bytes(self, package_root: Path, selection: list[str], generated: int | None = None) -> bytes:
        """The status projection is part of the same publication as its record."""
        manifest = _read_json(package_root / "compose" / "domains.json")
        available = sorted((manifest.get("domains") or {}).keys())
        applied = available if selection == ["all"] else sorted(value.rsplit("/", 1)[-1] for value in selection)
        return _canonical({
            "repo": str(package_root), "current_version": None, "latest_version": None,
            "rolled_back_to": None, "versions": None, "summary": None,
            "domains": {"available": available, "applied": applied}, "last_apply": None,
            "deployed_corpus": None, "generated": int(time.time()) if generated is None else generated,
            "mode": "private-session-scoped",
        }) + b"\n"

    @staticmethod
    def _safe_transaction_target(path: Path) -> None:
        try:
            reject_symlink_ancestors(path)
        except TransactionError as exc:
            raise InstallError(str(exc)) from exc

    @staticmethod
    def _file_version(path: Path, *, allow_bytes: bool = True) -> dict[str, Any]:
        """A journaled exact-state predicate; secrets use hash-only predicates."""
        CorpusInstaller._safe_transaction_target(path)
        if not path.exists():
            return {"exists": False}
        if not path.is_file():
            raise InstallError(f"transaction target is not a regular file: {path}")
        data = path.read_bytes()
        result: dict[str, Any] = {"exists": True, "sha256": hashlib.sha256(data).hexdigest()}
        if allow_bytes:
            result["bytes_b64"] = base64.b64encode(data).decode("ascii")
        return result

    @staticmethod
    def _planned_version(data: bytes | None) -> dict[str, Any]:
        if data is None:
            return {"exists": False}
        return {"exists": True, "sha256": hashlib.sha256(data).hexdigest(),
                "bytes_b64": base64.b64encode(data).decode("ascii")}

    @staticmethod
    def _matches_version(path: Path, version: dict[str, Any]) -> bool:
        try:
            CorpusInstaller._safe_transaction_target(path)
        except InstallError:
            return False
        if not version.get("exists"):
            return not path.exists()
        return path.is_file() and _sha256(path) == version.get("sha256")

    def _transaction_path(self, transaction_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", transaction_id):
            raise InstallError("unsafe transaction id")
        # Store keeps its source-only candidate at ``transactions/<id>``.
        # The installer must never overwrite that source journal.
        return self.runtime / "installer-transactions" / transaction_id / "journal.json"

    def _journal_write(self, journal: Path, value: dict[str, Any]) -> None:
        _atomic_json(journal, value)

    def _write_planned(self, path: Path, version: dict[str, Any], mode: int) -> None:
        self._safe_transaction_target(path)
        encoded = version.get("bytes_b64")
        if not isinstance(encoded, str):
            if not version.get("exists"):
                path.unlink(missing_ok=True)
                return
            raise InstallError(f"journal has no replay bytes for {path}")
        _atomic_bytes(path, base64.b64decode(encoded.encode("ascii"), validate=True), mode)

    def _assert_preflight_paths(self, paths: list[dict[str, Any]]) -> None:
        for entry in paths:
            self._safe_transaction_target(Path(entry["path"]))
        conflicts = [entry["path"] for entry in paths
                     if not self._matches_version(Path(entry["path"]), entry["before"])
                     and not self._matches_version(Path(entry["path"]), entry["after"])]
        if conflicts:
            raise InstallError("owned path changed during transaction preflight: " + ", ".join(conflicts))

    def _projection_matches(self, entry: dict[str, Any]) -> bool:
        path, after = Path(entry["path"]), entry["after"]
        return self._matches_version(path, after) and (
            not after.get("exists") or path.stat().st_mode & 0o777 == int(entry["mode"]))

    def _old_record(self) -> dict[str, Any] | None:
        return _read_json(self.record_path) if self.record_path.exists() else None

    def _safe_owned_path(self, path: Path, root: Path) -> None:
        """An ownership record cannot redirect writes through a symlinked parent."""
        if not _inside(path, root):
            raise InstallError(f"owned path is outside its private destination: {path}")
        current = root.absolute()
        if current.is_symlink():
            raise InstallError(f"owned destination root is symlinked: {current}")
        relative = path.absolute().relative_to(current)
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise InstallError(f"owned destination has symlink ancestor: {current}")

    def _expected_owned(self, release: Path) -> dict[str, str]:
        expected = {str(self.bin_root / "agent-launch"): hashlib.sha256(self._launcher_body(release)).hexdigest(),
                    str(self.launch_root / "profiles.toml"): _sha256(release / "launch" / "agent-launch.toml")}
        i18n = release / "launch" / "i18n"
        for source in sorted(i18n.glob("*.toml")):
            expected[str(self.launch_root / "i18n" / source.name)] = _sha256(source)
        return expected

    def _validate_owned_record(self, record: dict[str, Any], release: Path) -> None:
        expected = self._expected_owned(release)
        launcher = record.get("launcher")
        if launcher is not None:
            if not isinstance(launcher, dict) or launcher.get("path") != str(self.bin_root / "agent-launch") \
                    or launcher.get("sha256") != expected[str(self.bin_root / "agent-launch")]:
                raise InstallError("private install record has an invalid launcher ownership claim")
            self._safe_owned_path(Path(launcher["path"]), self.bin_root)
        seen: set[str] = set()
        for entry in record.get("config_files") or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] in seen:
                raise InstallError("private install record has invalid config ownership entries")
            seen.add(entry["path"])
            if entry["path"] not in expected or entry.get("sha256") != expected[entry["path"]]:
                raise InstallError(f"private install record has an invalid config ownership claim: {entry['path']}")
            self._safe_owned_path(Path(entry["path"]), self.launch_root)

    def _owned_hash(self, record: dict[str, Any] | None, path: Path) -> str | None:
        if not record:
            return None
        for entry in [record.get("launcher"), *(record.get("config_files") or [])]:
            if isinstance(entry, dict) and entry.get("path") == str(path):
                value = entry.get("sha256")
                return value if isinstance(value, str) else None
        return None

    def _write_owned(self, path: Path, content: bytes, old: dict[str, Any] | None, mode: int) -> dict[str, str] | None:
        root = self.bin_root if path == self.bin_root / "agent-launch" else self.launch_root
        self._safe_owned_path(path, root)
        expected = self._owned_hash(old, path)
        if path.exists() and (path.is_symlink() or (expected is None and _sha256(path) != hashlib.sha256(content).hexdigest())
                            or (expected is not None and _sha256(path) != expected)):
            return None
        _atomic_bytes(path, content, mode)
        return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}

    def _launcher_body(self, package_root: Path) -> bytes:
        quoted = shlex.quote(str(package_root))
        return ("#!/bin/sh\n"
                "export AGENT_BIOS_PRIVATE_CORPUS=1\n"
                f"export AGENT_BIOS_PACKAGE_ROOT={quoted}\n"
                "exec python3 \"$AGENT_BIOS_PACKAGE_ROOT/launch/agent-launch.py\" \"$@\"\n").encode("utf-8")

    def _shell_manager(self):
        path = Path(__file__).resolve().parent.parent / "launch/shell_integration.py"
        spec = importlib.util.spec_from_file_location("agent_bios_shell_integration", path)
        if spec is None or spec.loader is None:
            raise InstallError("shell connection manager is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ShellIntegration(self.env, self.repo)

    def _shell_paths(self, action: str) -> list[dict[str, Any]]:
        try:
            manager = self._shell_manager()
            # A receipt-less managed script may survive an interrupted opt-in.
            # With neither, do not inspect or claim the user's startup file.
            if not manager.has_connection():
                return []
            # Install owns and validates the upcoming launcher projection; it
            # must also be able to repair a missing/non-executable entrypoint.
            changes = manager.plan(action, installing=action == "restore")["changes"]
        except (OSError, RuntimeError) as exc:
            raise InstallError(str(exc)) from exc
        return [{"path": str(row["path"]), "before": self._planned_version(row["before"]),
                 "after": self._planned_version(row["after"]), "mode": row["mode"], "archive": False}
                for row in changes]

    @_serialized
    def install(self, domains: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        files = self._package_files()
        requested = self._normalized_domains(domains)
        prior = self._old_record()
        # An update without an explicit selection must not broaden a saved
        # core-only or domain-limited environment back to every domain.
        if domains is None and isinstance((prior or {}).get("selection"), list):
            requested = prior["selection"]
        # A preview is strictly read-only.  A real install first refuses an
        # unrelated reset, then finishes only its own pending install before
        # creating an immutable release directory.
        if not dry_run:
            pending = pending_status(self.state_root)["transactions"]
            if any(row["owner"] == "installer" and row["kind"] == "reset" for row in pending):
                raise InstallError("pending reset requires recovery before install")
            with operation_scope(self.state_root):
                self._recover_pending_transactions()
        release, entries, digest = self._copy_release(files, dry_run)
        if dry_run:
            return {"dry_run": True, "release": str(release), "release_digest": digest,
                    "files": len(entries), "selection": requested}
        shell_paths = self._shell_paths("restore")
        # Stage the immutable baseline before publishing either source pointers
        # or launcher projections.  Store owns those source pointers; this
        # coordinator owns all cross-owner ordering.
        store = self._store(release)
        prepare = getattr(store, "prepare_install", None)
        if not callable(prepare):
            raise InstallError("private corpus store does not support staged install recovery")
        candidate = prepare(requested)
        if not isinstance(candidate, dict) or not isinstance(candidate.get("details"), dict):
            raise InstallError("private corpus store returned an invalid install candidate")
        details = candidate["details"]
        baseline_ref = details.get("baseline_ref")
        if not isinstance(baseline_ref, str):
            raise InstallError("private corpus store candidate has no baseline ref")
        owned: list[tuple[Path, bytes, int]] = [
            (self.bin_root / "agent-launch", self._launcher_body(release), 0o755),
            (self.launch_root / "profiles.toml", (release / "launch" / "agent-launch.toml").read_bytes(), 0o644),
        ]
        owned.extend((self.launch_root / "i18n" / source.name, source.read_bytes(), 0o644)
                     for source in sorted((release / "launch" / "i18n").glob("*.toml")))
        conflicts: list[str] = []
        for path, content, _mode in owned:
            current = self._file_version(path)
            expected = self._owned_hash(prior, path)
            if current["exists"] and current.get("sha256") != hashlib.sha256(content).hexdigest() and \
                    (expected is None or current.get("sha256") != expected):
                conflicts.append(str(path))
        if conflicts:
            raise InstallError("private install cannot replace user-owned paths: " + ", ".join(conflicts))
        launcher = {"path": str(owned[0][0]), "sha256": hashlib.sha256(owned[0][1]).hexdigest()}
        config = [{"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}
                  for path, content, _mode in owned[1:]]
        record = {
            "schema_version": SCHEMA_VERSION, "package_root": str(release), "release_digest": digest,
            "installed_files": entries, "selection": requested, "baseline_ref": baseline_ref,
            "launcher": launcher, "config_files": config, "created_at": int(time.time()),
            "mode": "private-session-scoped", "needs_action": [],
        }
        paths = [{"path": str(path), "before": self._file_version(path),
                  "after": self._planned_version(content), "mode": mode}
                 for path, content, mode in owned]
        paths.extend(shell_paths)
        paths.extend([
            {"path": str(self.record_path), "before": self._file_version(self.record_path),
             "after": self._planned_version(_canonical(record) + b"\n"), "mode": 0o600},
            {"path": str(self.state_root / "corpus-status.json"),
             "before": self._file_version(self.state_root / "corpus-status.json"),
             "after": self._planned_version(self._launcher_status_bytes(release, requested)), "mode": 0o600},
        ])
        transaction_id = str(candidate.get("transaction_id") or uuid.uuid4().hex)
        journal = self._transaction_path(transaction_id)
        # Source candidates are persisted by CorpusStore under the transaction
        # id.  Keep only hashes here: personal source text is free-form and
        # must never be accidentally archived by the installer journal.
        association = {"transaction_id": transaction_id, "baseline_ref": baseline_ref,
                       "selected_baseline_ref": details.get("selected_baseline_ref"),
                       "items": details.get("items"),
                       "source_before_sha256": hashlib.sha256(_canonical(candidate.get("before"))).hexdigest(),
                       "source_after_sha256": hashlib.sha256(_canonical(candidate.get("after"))).hexdigest()}
        journal_data = {"schema_version": SCHEMA_VERSION, "owner": "installer", "kind": "install", "state": "PREPARED",
                        "phase": "preflight", "candidate": association, "paths": paths,
                        "created_at": int(time.time())}
        self._journal_write(journal, journal_data)
        try:
            with operation_scope(self.state_root):
                self._finish_install_transaction(journal, journal_data, store, candidate)
            return {"dry_run": False, "stored": True, "activation": "unverified", "record": record}
        except BaseException as exc:
            journal_data["state"] = "NEEDS_RECOVERY"
            journal_data["error"] = type(exc).__name__
            self._journal_write(journal, journal_data)
            raise

    def _finish_install_transaction(self, journal: Path, data: dict[str, Any], store: Any,
                                    candidate: dict[str, Any] | None) -> None:
        self._assert_preflight_paths(data["paths"])
        data["state"], data["phase"] = "APPLYING", "projections"
        self._journal_write(journal, data)
        # Write candidate projections before source publication.  A crash here
        # is harmless to readers because the journal guard is already durable.
        for entry in data["paths"]:
            path = Path(entry["path"])
            if not self._projection_matches(entry):
                self._write_planned(path, entry["after"], int(entry["mode"]))
        data["phase"] = "source"
        self._journal_write(journal, data)
        commit = getattr(store, "commit_install", None)
        if not callable(commit):
            raise InstallError("private corpus store does not support staged install commit")
        if candidate is None:
            # The store persists the complete source candidate under this id;
            # passing only it prevents installer journals from duplicating user
            # authoring bytes (which could include sensitive free text).
            commit({"transaction_id": data["candidate"]["transaction_id"]})
        else:
            commit(candidate)
        data["phase"] = "verify"
        self._journal_write(journal, data)
        # The record/status are included in paths and now exact.  Verify the
        # installed source and every owned projection before success is visible.
        self._verify_transaction_install(data)
        data["state"], data["phase"], data["committed_at"] = "COMMITTED", "complete", int(time.time())
        self._journal_write(journal, data)

    def _verify_transaction_install(self, data: dict[str, Any]) -> None:
        for entry in data["paths"]:
            if not self._projection_matches(entry):
                raise InstallError(f"transaction projection did not verify: {entry['path']}")
        record = _read_json(self.record_path)
        release = Path(record["package_root"])
        self._verify_release(release, record["installed_files"])
        self._validate_owned_record(record, release)
        source = _read_json(self.runtime / "state.json")
        if source.get("last_successful_install_ref") != record.get("baseline_ref"):
            raise InstallError("staged corpus baseline was not published")

    def _recover_pending_transactions(self) -> None:
        root = self.runtime / "installer-transactions"
        if not root.exists():
            return
        for journal in sorted(root.glob("*/journal.json")):
            data = _read_json(journal)
            if data.get("state") not in {"PREPARED", "APPLYING", "NEEDS_RECOVERY"}:
                continue
            if data.get("kind") != "install" or not isinstance(data.get("candidate"), dict) \
                    or not isinstance(data.get("paths"), list):
                raise InstallError(f"unrecoverable transaction journal: {journal}")
            association = data["candidate"]
            release_record = next((entry for entry in data["paths"] if entry.get("path") == str(self.record_path)), None)
            if not isinstance(release_record, dict):
                raise InstallError(f"transaction journal lacks install record: {journal}")
            encoded = release_record.get("after", {}).get("bytes_b64")
            if not isinstance(encoded, str):
                raise InstallError(f"transaction journal lacks record bytes: {journal}")
            record = json.loads(base64.b64decode(encoded.encode("ascii"), validate=True))
            release = Path(record.get("package_root", ""))
            if not release.is_dir() or release.is_symlink():
                raise InstallError(f"transaction release is unavailable: {journal}")
            try:
                with operation_scope(self.state_root):
                    self._finish_install_transaction(journal, data, self._store(release), None)
            except BaseException as exc:
                data["state"], data["error"] = "NEEDS_RECOVERY", type(exc).__name__
                self._journal_write(journal, data)
                raise InstallError(f"pending install requires recovery: {journal}") from exc

    @_serialized
    def verify(self) -> dict[str, Any]:
        try:
            guard_pending(self.state_root)
        except TransactionError as exc:
            raise InstallError(str(exc)) from exc
        record = self._old_record()
        if record is None:
            raise InstallError("no private install record")
        if record.get("schema_version") != SCHEMA_VERSION:
            raise InstallError("private install record schema mismatch")
        if record.get("needs_action"):
            raise InstallError("private install is incomplete; resolve owned-path conflicts: "
                               + ", ".join(str(path) for path in record["needs_action"]))
        release = Path(record.get("package_root", ""))
        releases = self.runtime / "releases"
        if not _inside(release, releases) or release.is_symlink() or not release.is_dir():
            raise InstallError("private install record has unsafe package root")
        entries = record.get("installed_files")
        if not isinstance(entries, list) or not entries:
            raise InstallError("private install record has no installed files")
        self._verify_release(release, entries)
        self._validate_owned_record(record, release)
        catalog = self._catalog(release)
        if not catalog.get("items"):
            raise InstallError("private catalog is empty")
        source_state = _read_json(self.runtime / "state.json")
        if source_state.get("last_successful_install_ref") != record.get("baseline_ref"):
            raise InstallError("private baseline does not match install record")
        for entry in [record.get("launcher"), *(record.get("config_files") or [])]:
            if not isinstance(entry, dict):
                continue
            path = Path(entry.get("path", ""))
            if path.is_symlink() or not path.is_file() or _sha256(path) != entry.get("sha256"):
                raise InstallError(f"private owned file drifted: {path}")
        launcher_status = _read_json(self.state_root / "corpus-status.json")
        domains = launcher_status.get("domains")
        if launcher_status.get("repo") != str(release) or not isinstance(domains, dict) or \
                not isinstance(domains.get("available"), list) or not isinstance(domains.get("applied"), list):
            raise InstallError("launcher corpus-status projection is missing or malformed")
        return {"stored": True, "catalog_items": len(catalog["items"]), "baseline_ref": record["baseline_ref"],
                "activation": "unverified"}

    @_serialized
    def status(self) -> dict[str, Any]:
        try:
            pending = pending_status(self.state_root)
        except TransactionError as exc:
            raise InstallError(str(exc)) from exc
        record = self._old_record()
        if not record:
            return {"installed": False, "activation": "unverified", **pending}
        return {"installed": True, "package_root": record.get("package_root"),
                "baseline_ref": record.get("baseline_ref"), "needs_action": record.get("needs_action", []),
                "activation": "unverified", **pending}

    def _active_intents(self) -> list[Path]:
        root = self.runtime / "activations"
        if not root.is_dir():
            return []
        active = []
        for journal in root.glob("*/journal.json"):
            with contextlib.suppress(InstallError):
                data = _read_json(journal)
                if data.get("state") in {"PREPARED", "HOST_OBSERVED"}:
                    active.append(journal)
        return active

    @_serialized
    def uninstall(self, dry_run: bool = False) -> dict[str, Any]:
        record = self._old_record()
        if record is not None:
            release = Path(record.get("package_root", ""))
            if not _inside(release, self.runtime / "releases") or release.is_symlink() or not release.is_dir():
                raise InstallError("private install record has unsafe package root")
            self._validate_owned_record(record, release)
        shell_removed: list[str] = []
        try:
            manager = self._shell_manager()
            if manager.has_connection():
                shell_removed = manager.apply("remove", dry_run)["changed_paths"]
        except (OSError, RuntimeError) as exc:
            raise InstallError(str(exc)) from exc
        if record is None:
            return {"removed": shell_removed, "preserved": ["no private install record"]}
        removed: list[str] = list(shell_removed)
        preserved: list[str] = []
        for entry in [record.get("launcher"), *(record.get("config_files") or [])]:
            if not isinstance(entry, dict):
                continue
            path = Path(entry.get("path", ""))
            expected = entry.get("sha256")
            if path.is_file() and not path.is_symlink() and isinstance(expected, str) and _sha256(path) == expected:
                if not dry_run:
                    path.unlink()
                removed.append(str(path))
            elif path.exists():
                preserved.append(str(path))
        intents = self._active_intents()
        if intents:
            preserved.extend(str(path) for path in intents)
        elif _inside(release, self.runtime / "releases") and release.is_dir() and not release.is_symlink():
            if not dry_run:
                shutil.rmtree(release)
            removed.append(str(release))
        else:
            preserved.append(str(release))
        if not intents and not dry_run:
            self.record_path.unlink(missing_ok=True)
        # User package/overlays/learnings and session snapshots/pins are purposely
        # not enumerated or deleted here.  No whole state-root removal occurs.
        return {"removed": removed, "preserved": preserved,
                "retained": [str(self.user_root), str(self.state_root / "sessions")]}

    def _reset_layout(self, record: dict[str, Any], release: Path) -> tuple[list[Path], Path, Path, list[tuple[Path, bytes, int]]]:
        local = [self.launch_root / name for name in ("presets.local.toml", "review-methods.local.toml", "launcher.local.toml")]
        connections = self.launch_root.parent / "agent-bios"
        cleanup = [*local, connections / "ingest-url", self.user_root / "understand" / "state.json"]
        owned = [(self.bin_root / "agent-launch", self._launcher_body(release), 0o755),
                 (self.launch_root / "profiles.toml", (release / "launch" / "agent-launch.toml").read_bytes(), 0o644)]
        owned.extend((self.launch_root / "i18n" / p.name, p.read_bytes(), 0o644)
                     for p in sorted((release / "launch" / "i18n").glob("*.toml")))
        return cleanup, connections / "token", connections, owned

    def _learning_versions(self) -> dict[str, dict[str, Any]]:
        """Learning events are authoring input, not reset-owned cleanup."""
        return {host: self._file_version(self.user_root / "learnings" / host / "events.jsonl")
                for host in ("claude", "codex")}

    def _reset_preview(self) -> dict[str, Any]:
        record = self._old_record()
        if record is None:
            raise InstallError("cannot reset before private install")
        release = Path(record.get("package_root", ""))
        if not _inside(release, self.runtime / "releases") or release.is_symlink() or not release.is_dir():
            raise InstallError("private install record has unsafe package root")
        self._validate_owned_record(record, release)
        cleanup, secret, _connections, owned = self._reset_layout(record, release)
        targets = [{"path": str(path), "before": self._file_version(path), "after": {"exists": False}, "mode": 0o600,
                    "archive": True} for path in cleanup]
        targets.extend(self._shell_paths("remove"))
        targets.extend({"path": str(path), "before": self._file_version(path), "after": self._planned_version(body),
                        "mode": mode, "archive": False} for path, body, mode in owned)
        status_path = self.state_root / "corpus-status.json"
        targets.append({"path": str(status_path), "before": self._file_version(status_path),
                        "after": self._planned_version(self._launcher_status_bytes(
                            release, record["selection"], record.get("created_at") if isinstance(record.get("created_at"), int) else 0)),
                        "mode": 0o600, "archive": False})
        secret_before = self._file_version(secret, allow_bytes=False)
        pending = pending_status(self.state_root)
        learning = self._learning_versions()
        fingerprint = hashlib.sha256(_canonical({"record": _sha256(self.record_path), "runtime": self._file_version(self.runtime / "state.json"),
                                                 "user": self._file_version(self.user_root / "state.json"), "targets": targets,
                                                 "secret": secret_before, "learning": learning, "pending": pending["transactions"]})).hexdigest()
        return {"preview": True, "expected_revision": fingerprint, "pending": pending,
                "archive": [entry["path"] for entry in targets if entry["archive"] and entry["before"]["exists"]],
                "delete_without_archive": [str(secret)] if secret_before["exists"] else [],
                "restore_defaults": [entry["path"] for entry in targets if not entry["archive"]],
                "retained": [str(self.state_root / "sessions"), str(self.user_root / "learnings")],
                "record": record, "release": release, "targets": targets, "secret_before": secret_before,
                "learning_before": learning}

    @_serialized
    def reset(self, apply: bool = False, yes: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
        """Preview first; an apply accepts exactly that observed generation."""
        preview = self._reset_preview()
        if not apply:
            return {key: value for key, value in preview.items() if key not in {"record", "release", "targets", "secret_before", "learning_before"}}
        if not yes or not isinstance(expected_revision, str):
            raise InstallError("reset apply requires --yes and preview expected_revision")
        pending = [row for row in preview["pending"]["transactions"] if row["owner"] == "installer"]
        if any(row["kind"] == "install" for row in pending):
            raise InstallError("pending install requires recovery before reset")
        for row in pending:
            data = _read_json(Path(row["path"]))
            if data.get("owner") != "installer" or data.get("kind") != "reset":
                raise InstallError(f"pending reset requires fresh preview: {row['path']}")
            if data.get("intent", {}).get("accepted_revision") == expected_revision:
                return self._recover_reset(Path(row["path"]), data)
        if preview["expected_revision"] != expected_revision:
            raise InstallError("reset preview is stale; preview again before applying")
        record, release, targets = preview["record"], preview["release"], preview["targets"]
        with operation_scope(self.state_root):
            plan = self._store(release).plan({"operation": "reset"})
        reset_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
        journal = self.runtime / "resets" / reset_id / "journal.json"
        archive = self.user_root / "history" / reset_id / "launcher-config"
        data = {"schema_version": SCHEMA_VERSION, "owner": "installer", "kind": "reset", "state": "PREPARED", "phase": "preflight",
                "archive": str(archive), "targets": targets, "secret_before": preview["secret_before"], "learning_before": preview["learning_before"],
                "intent": {"plan_id": plan["plan_id"], "expected_revision": plan["expected_revision"],
                           "accepted_revision": expected_revision, "record_sha256": _sha256(self.record_path)},
                "retained": preview["retained"], "created_at": int(time.time())}
        _atomic_json(journal, data)
        # Keep the old publication guard until the replacement intent is durable.
        for row in pending:
            prior = _read_json(Path(row["path"]))
            prior["state"] = "SUPERSEDED"
            _atomic_json(Path(row["path"]), prior)
        return self._recover_reset(journal, data)

    def _source_pair_ok(self, data: dict[str, Any]) -> bool:
        plan_path = self.runtime / "transactions" / data["intent"]["plan_id"] / "journal.json"
        plan = _read_json(plan_path).get("plan", {})
        before, after = plan.get("before", {}), plan.get("after", {})
        runtime, user = _read_json(self.runtime / "state.json"), _read_json(self.user_root / "state.json")
        return runtime in (before.get("runtime"), after.get("runtime")) and user in (before.get("user"), after.get("user"))

    def _recover_reset(self, journal: Path, data: dict[str, Any]) -> dict[str, Any]:
        """Preflight every target and source pair before changing one byte."""
        try:
            if data["intent"].get("record_sha256") != _sha256(self.record_path) or not self._source_pair_ok(data):
                raise InstallError("reset state changed; obtain a fresh preview")
            if data.get("learning_before") != self._learning_versions():
                raise InstallError("reset learning source changed; obtain a fresh preview")
            targets = data.get("targets")
            if not isinstance(targets, list):
                raise InstallError("pending reset requires fresh preview")
            for entry in targets:
                if not (self._matches_version(Path(entry["path"]), entry["before"]) or self._matches_version(Path(entry["path"]), entry["after"])):
                    raise InstallError(f"reset target changed; obtain a fresh preview: {entry['path']}")
            secret = self.launch_root.parent / "agent-bios" / "token"; prior = data.get("secret_before", {"exists": False})
            if not (self._matches_version(secret, prior) or not secret.exists()):
                raise InstallError("reset token changed; obtain a fresh preview")
            release = Path(self._old_record()["package_root"])
            archive = Path(data["archive"])
            data.update({"state": "APPLYING", "phase": "archive"}); _atomic_json(journal, data)
            for entry in targets:
                path = Path(entry["path"])
                if entry.get("archive") and entry["before"].get("exists"):
                    target = archive / path.name
                    if not target.exists(): self._write_planned(target, entry["before"], 0o600)
                if entry.get("archive") and not self._matches_version(path, entry["after"]): self._write_planned(path, entry["after"], int(entry["mode"]))
            data["phase"] = "source"; _atomic_json(journal, data)
            with operation_scope(self.state_root):
                result = self._store(release).apply(data["intent"]["plan_id"], data["intent"]["expected_revision"])
            data["result"] = result; data["phase"] = "projections"; _atomic_json(journal, data)
            for entry in targets:
                if not entry.get("archive") and not self._projection_matches(entry): self._write_planned(Path(entry["path"]), entry["after"], int(entry["mode"]))
            if prior.get("exists"):
                if self._matches_version(secret, prior):
                    secret.unlink()
                elif secret.exists():
                    raise InstallError("reset token changed; obtain a fresh preview")
            data.update({"state": "COMMITTED", "phase": "complete", "committed_at": int(time.time())}); _atomic_json(journal, data)
            return {"preview": False, "reset": data["result"], "archive": data["archive"], "retained": data["retained"], "recovered": True}
        except BaseException as exc:
            data.update({"state": "NEEDS_RECOVERY", "error": type(exc).__name__}); _atomic_json(journal, data); raise

    def _legacy_manifest_files(self, needs_action: list[str], read=None) -> list[Path]:
        manifest = self.state_root / "manifest.txt"
        if manifest.is_symlink():
            needs_action.append(f"unsafe legacy manifest symlink: {manifest}")
            return []
        content = read(manifest) if read else manifest.read_bytes() if manifest.is_file() else None
        if content is None:
            return []
        private = self._old_record()
        protected: set[str] = set()
        if private is not None:
            self._validate_owned_record(private, Path(private.get("package_root", "")))
            protected = {str(entry["path"]) for entry in
                         [private["launcher"], *private.get("config_files", [])]}
        owned = self._legacy_manifest_destinations()
        paths: list[Path] = []
        body = content.decode("utf-8")
        for raw in body.splitlines():
            if not raw.strip():
                continue
            path = Path(raw.strip())
            if str(path) in protected:
                continue
            if not path.is_absolute() or path in {self.claude_root / "CLAUDE.md", self.codex_root / "AGENTS.md"}:
                needs_action.append(f"unowned legacy manifest target: {path}")
                continue
            if path.is_symlink():
                needs_action.append(f"unsafe legacy manifest target: {path}")
                continue
            try:
                self._migration_target_root(path)
            except InstallError as exc:
                needs_action.append(str(exc))
                continue
            if path not in owned:
                # A prior installer wrote broad directory walks into its manifest.
                # Root containment proves only where a file lives, never who wrote it.
                # A stale absent entry is harmless; an existing unknown file is not.
                if path.exists():
                    needs_action.append(f"unowned legacy manifest target: {path}")
                continue
            if path.exists() and not path.is_file():
                needs_action.append(f"legacy manifest target is not a regular file: {path}")
                continue
            paths.append(path)
        return paths

    def _legacy_manifest_destinations(self, package_root: Path | None = None) -> set[Path]:
        """Return only paths a legacy installer could derive from this source.

        The old manifest included a recursive scan of ``central``.  This map is
        deliberately source-derived instead of treating a shared native root as
        a claim of ownership, so a same-directory user file remains protected.
        """
        source_root = (package_root or self.repo).resolve()
        owned: set[Path] = {
            self.state_root / "version.json",
            self.claude_root / "central" / "bundle.md",
            self.claude_root / "personal" / "learnings.jsonl",
            self.codex_root / "personal" / "learnings.jsonl",
        }

        def source_file(relative: str) -> Path | None:
            path = source_root / relative
            return path if path.is_file() and not path.is_symlink() else None

        native = (
            ("wrappers/codex-run.sh", self.codex_root / "bin" / "codex-run"),
            ("wrappers/codex-helm.sh", self.codex_root / "bin" / "codex-helm"),
            ("wrappers/claude-run.sh", self.claude_root / "bin" / "claude-run"),
            ("launch/agent-launch.py", self.bin_root / "agent-launch"),
            ("launch/agent-launch.toml", self.launch_root / "profiles.toml"),
            ("launch/agent-launch.zsh", self.launch_root / "shell.zsh"),
        )
        owned.update(destination for source, destination in native if source_file(source) is not None)
        i18n = source_root / "launch" / "i18n"
        if i18n.is_dir() and not i18n.is_symlink():
            owned.update(self.launch_root / "i18n" / source.name
                         for source in i18n.glob("*.toml") if source.is_file() and not source.is_symlink())

        catalog = self._catalog(source_root)
        for item in catalog.get("items", []):
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            origin = item.get("origin")
            source = origin.get("source_path") if isinstance(origin, dict) else None
            members = item.get("members")
            if not isinstance(source, str) or not isinstance(members, dict):
                continue
            for member in members:
                if not isinstance(member, str):
                    continue
                relative = PurePosixPath(member)
                if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2:
                    continue
                tail = Path(*relative.parts[1:])
                if kind == "guide" and source.startswith("claude/guides/") and relative.parts[0] == "guides":
                    owned.update({self.claude_root / "guides" / tail,
                                  self.claude_root / "central" / "guides" / tail,
                                  self.codex_root / "guides" / tail})
                elif kind == "hook" and source.startswith("claude/hooks/") and relative.parts[0] == "hooks":
                    owned.add(self.claude_root / "central" / "hooks" / tail)
                elif kind == "agent" and source.startswith("claude/agents/") and relative.parts[0] == "agents":
                    owned.add(self.claude_root / "central" / "agents" / tail)
                elif kind == "skill" and source.startswith("claude/skills/") and relative.parts[0] == "skills":
                    owned.update({self.claude_root / "skills" / tail,
                                  self.codex_root / "skills" / tail})

        agents = source_root / "codex" / "agents"
        if agents.is_dir() and not agents.is_symlink():
            owned.update(self.codex_root / "agents" / source.name
                         for source in agents.glob("*.toml") if source.is_file() and not source.is_symlink())
        return owned

    def _migration_cleanup_destinations(self, release: Path) -> set[Path]:
        """The pinned release plus bounded native edits define replay authority."""
        return self._legacy_manifest_destinations(release) | {
            self.state_root / "manifest.txt",
            self.claude_root / "CLAUDE.md",
            self.claude_root / "personal" / "learnings.md",
            self.claude_root / "settings.json",
            self.codex_root / "AGENTS.md",
            self.codex_root / "config.toml",
            self.zdotdir / ".zshrc",
            self.zdotdir / ".zshenv",
            self.zdotdir / ".zprofile",
        }

    def _has_legacy_learning_projection(self, host: str, prose: Path, read=None) -> bool:
        if prose.is_symlink():
            return True
        body = read(prose) if read else prose.read_bytes() if prose.is_file() else None
        if body is None:
            return False
        if host == "codex":
            return PERSONAL_START.encode() in body or PERSONAL_END.encode() in body
        # The published legacy installer seeds this exact empty automation-owned file.
        assembler = self._private_module(self.repo, "assemble")
        return body != assembler.PERSONAL_LEARNINGS_HEADER.encode("utf-8")

    def _legacy_events(self, host: str, needs_action: list[str], read=None) -> tuple[list[dict[str, str]], Path | None]:
        home = self.claude_root if host == "claude" else self.codex_root
        source = home / "personal" / "learnings.jsonl"
        prose = home / "personal" / "learnings.md" if host == "claude" else home / "AGENTS.md"
        projection = self._has_legacy_learning_projection(host, prose, read)
        if source.is_symlink():
            needs_action.append(f"legacy {host} learning JSONL is symlinked: {source}")
            return [], None
        content = read(source) if read else source.read_bytes() if source.is_file() else None
        if projection and content is None:
            needs_action.append(f"legacy {host} learning projection has no immutable JSONL source: {prose}")
            return [], None
        if content is None:
            return [], None
        schema = _read_json(self.repo / "learn" / "learning.schema.json")
        allowed = set((schema.get("properties") or {}).keys())
        required = set(schema.get("required") or [])
        events: list[dict[str, str]] = []
        seen: dict[str, str] = {}
        body = content.decode("utf-8")
        for number, line in enumerate(body.splitlines(), 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except ValueError:
                needs_action.append(f"invalid legacy {host} learning JSONL at {source}:{number}")
                continue
            if (not isinstance(raw, dict) or set(raw) - allowed or required - set(raw)
                    or raw.get("schema_version") != 1 or not isinstance(raw.get("learning_id"), str)
                    or not LEARNING_ID.fullmatch(raw["learning_id"])
                    or not isinstance(raw.get("lesson"), str) or not isinstance(raw.get("domain"), str)
                    or not isinstance(raw.get("created"), str) or not isinstance(raw.get("supporting_sessions"), list)
                    or not all(isinstance(value, str) for value in raw["supporting_sessions"])):
                needs_action.append(f"invalid collector v1 {host} learning record at {source}:{number}")
                continue
            prior = seen.get(raw["learning_id"])
            if prior is not None:
                if prior != line:
                    needs_action.append(f"same learning_id has different legacy bytes at {source}:{number}")
                continue
            seen[raw["learning_id"]] = line
            events.append({"learning_id": raw["learning_id"], "raw": line})
        return events, source

    def _event_destination_conflicts(self, host: str, events: list[dict[str, str]], needs_action: list[str]) -> None:
        target = self.user_root / "learnings" / host / "events.jsonl"
        if not target.exists():
            return
        if target.is_symlink():
            needs_action.append(f"unsafe private {host} learning event symlink: {target}")
            return
        existing: dict[str, str] = {}
        for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                needs_action.append(f"invalid private {host} learning JSONL at {target}:{number}")
                continue
            learning_id = record.get("learning_id") if isinstance(record, dict) else None
            if not isinstance(learning_id, str):
                needs_action.append(f"invalid private {host} learning record at {target}:{number}")
                continue
            previous = existing.get(learning_id)
            if previous is not None and previous != line:
                needs_action.append(f"same learning_id has different private bytes at {target}:{number}")
            existing[learning_id] = line
        for event in events:
            current = existing.get(event["learning_id"])
            if current is not None and current != event["raw"]:
                needs_action.append(f"same learning_id has different source/private bytes: {event['learning_id']}")

    def _legacy_hook_registration_needed(self, needs_action: list[str], read=None) -> bool:
        """Use the assembler's exact command-ownership rule, after parse proof."""
        settings = self.claude_root / "settings.json"
        if settings.is_symlink():
            needs_action.append(f"unsafe Claude settings symlink: {settings}")
            return False
        content = read(settings) if read else settings.read_bytes() if settings.is_file() else None
        if content is None:
            return False
        try:
            data = json.loads(content.decode("utf-8"))
        except ValueError:
            needs_action.append(f"unreadable Claude settings for legacy hook removal: {settings}")
            return False
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            return False
        names = set((_read_json(self.repo / "compose" / "domains.json").get("hooks") or {}).keys())
        for entries in hooks.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
                    command = hook.get("command", "") if isinstance(hook, dict) else ""
                    if isinstance(command, str) and any(f"/hooks/{name}" in command for name in names):
                        return True
        return False

    def _legacy_hook_settings(self, release: Path, before: bytes) -> bytes:
        """Plan the assembler's exact ownership-sensitive edit without touching the host."""
        module = self._private_module(release, "assemble")
        manifest = _read_json(release / "compose" / "domains.json")
        with tempfile.TemporaryDirectory(prefix="corpus-hook-plan-") as raw:
            root = Path(raw)
            _atomic_bytes(root / "settings.json", before, 0o600)
            module.merge_settings(root, [], release / "claude" / "settings.template.json",
                                  owned_names=manifest.get("hooks", {}))
            return (root / "settings.json").read_bytes()

    def migration_plan(self) -> dict[str, Any]:
        return self._plan_migration()[0]

    def _plan_migration(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        # A transformation and its version predicate must describe the same read.
        inputs: dict[str, dict[str, Any]] = {}

        def read(path: Path) -> bytes | None:
            raw = str(path)
            if raw not in inputs:
                self._migration_target_root(path)
                inputs[raw] = self._file_version(path)
            if not inputs[raw]["exists"]:
                return None
            return base64.b64decode(inputs[raw]["bytes_b64"].encode("ascii"), validate=True)

        needs_action: list[str] = []

        def text(path: Path) -> str | None:
            if path.is_symlink():
                needs_action.append(f"unsafe native migration input symlink: {path}")
                return None
            content = read(path)
            return content.decode("utf-8") if content is not None else None

        writes: list[dict[str, str]] = []
        claude_entry = self.claude_root / "CLAUDE.md"
        body = text(claude_entry)
        if body is not None:
            new, removed = _remove_claude_imports(body)
            if removed:
                writes.append({"path": str(claude_entry), "content": new, "kind": "claude-imports"})
        codex_entry = self.codex_root / "AGENTS.md"
        body = text(codex_entry)
        if body is not None:
            new, outcome = _remove_spans(body)
            if new is None:
                needs_action.extend(f"{codex_entry}: {message}" for message in outcome)
            elif outcome:
                writes.append({"path": str(codex_entry), "content": new, "kind": "codex-markers"})
        codex_config = self.codex_root / "config.toml"
        body = text(codex_config)
        if body is not None:
            stripped, changed = _strip_codex_config_additions(body)
            if stripped is None:
                needs_action.append(f"cannot safely remove legacy Codex config additions: {codex_config}")
            elif changed:
                writes.append({"path": str(codex_config), "content": stripped, "kind": "codex-config-additions"})
        for startup in (self.zdotdir / ".zshrc", self.zdotdir / ".zshenv", self.zdotdir / ".zprofile"):
            body = text(startup)
            if body is not None:
                lines = body.splitlines(keepends=True)
                changed = [line for line in lines if line.strip() == ZSH_HOOK]
                if changed:
                    writes.append({"path": str(startup), "content": "".join(line for line in lines if line.strip() != ZSH_HOOK), "kind": "zsh-hook"})
        events: dict[str, list[dict[str, str]]] = {}
        learning_sources: dict[str, Path] = {}
        for host in ("claude", "codex"):
            captured, source = self._legacy_events(host, needs_action, read)
            if captured:
                events[host] = captured
                self._event_destination_conflicts(host, captured, needs_action)
                if source is not None:
                    learning_sources[host] = source
        deletes = self._legacy_manifest_files(needs_action, read)
        manifest = self.state_root / "manifest.txt"
        if not manifest.is_symlink() and read(manifest) is not None:
            deletes.append(manifest)
        seed = self.claude_root / "personal" / "learnings.md"
        if not seed.is_symlink() and read(seed) is not None and not self._has_legacy_learning_projection("claude", seed, read):
            deletes.append(seed)
        # Legacy learning projections are removed only when their immutable source
        # was successfully parsed and is scheduled for the private event store.
        for host, source in learning_sources.items():
            deletes.append(Path(source))
            if host == "claude":
                projection = self.claude_root / "personal" / "learnings.md"
                if not projection.is_symlink() and read(projection) is not None:
                    deletes.append(projection)
        remove_hooks = self._legacy_hook_registration_needed(needs_action, read)
        if not needs_action:
            for path in deletes:
                read(path)
        plan = {"schema_version": SCHEMA_VERSION, "writes": writes, "deletes": sorted({str(p) for p in deletes}),
                "events": events, "remove_hook_registrations": remove_hooks, "needs_action": needs_action}
        return plan, inputs

    def _backup(self, root: Path, path: Path) -> Path:
        target = root / "files" / str(path).lstrip("/")
        _atomic_bytes(target, path.read_bytes(), 0o600)
        return target

    def _migration_target_root(self, path: Path) -> Path:
        if not path.is_absolute() or ".." in path.parts:
            raise InstallError(f"unsafe migration target: {path}")
        roots = (self.claude_root, self.codex_root, self.launch_root, self.bin_root)
        if path in {self.state_root / name for name in ("manifest.txt", "version.json")}:
            root = self.state_root
        elif path in {self.zdotdir / name for name in (".zshrc", ".zshenv", ".zprofile")}:
            root = self.zdotdir
        else:
            root = next((r for r in roots if path != r and _inside(path, r)), None)
        if root is None:
            raise InstallError(f"migration target is outside owned roots: {path}")
        self._safe_owned_path(path, root)
        return root

    def _migration_paths(self, plan: dict[str, Any], release: Path,
                         inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        changes: dict[str, bytes | None] = {raw: None for raw in plan["deletes"]}
        for item in plan["writes"]:
            if item["path"] in changes:
                raise InstallError(f"migration both rewrites and deletes {item['path']}")
            changes[item["path"]] = item["content"].encode("utf-8")
        if plan["remove_hook_registrations"]:
            path = str(self.claude_root / "settings.json")
            if path in changes:
                raise InstallError("legacy manifest conflicts with managed hook settings")
            before = base64.b64decode(inputs[path]["bytes_b64"].encode("ascii"), validate=True)
            changes[path] = self._legacy_hook_settings(release, before)
        result = []
        for raw, content in sorted(changes.items()):
            path = Path(raw)
            self._migration_target_root(path)
            before = {key: value for key, value in inputs[raw].items() if key != "bytes_b64"}
            result.append({"path": raw, "before": before,
                           "after": self._planned_version(content),
                           "mode": (path.stat().st_mode & 0o777) if path.exists() else 0o600})
        return result

    def _validate_migration(self, journal: Path, data: dict[str, Any]) -> Path:
        self._safe_owned_path(journal, self.runtime / "migrations")
        phases = {"preflight", "cleanup", "install", "verify", "complete"}
        if data.get("kind") != "migrate" or data.get("phase") not in phases or \
                not isinstance(data.get("paths"), list) or not isinstance(data.get("plan"), dict) or \
                not isinstance(data.get("inputs"), dict):
            raise InstallError(f"legacy migration journal has no safe replay plan; recover its backup first: {journal}")
        release_record = data.get("release")
        if not isinstance(release_record, dict):
            raise InstallError(f"migration journal lacks its pinned release: {journal}")
        try:
            release = _valid_release(self.state_root, release_record)
        except TransactionError as exc:
            raise InstallError(f"invalid migration release: {journal}: {exc}") from exc
        self._safe_owned_path(release, self.runtime / "releases")
        if data.get("backup_root") != str(journal.parent / "backup"):
            raise InstallError(f"unsafe migration backup root: {journal}")
        self._safe_owned_path(Path(data["backup_root"]), journal.parent)
        cleanup_destinations = self._migration_cleanup_destinations(release)
        seen = set()
        path_names = {entry.get("path") for entry in data["paths"] if isinstance(entry, dict)}
        for raw, version in data["inputs"].items():
            self._migration_target_root(Path(raw))
            if not isinstance(version, dict) or not isinstance(version.get("exists"), bool):
                raise InstallError(f"invalid migration input version: {journal}")
            encoded = version.get("bytes_b64")
            if encoded is not None:
                if raw in path_names:
                    raise InstallError(f"migration target input retains duplicate replay bytes: {journal}")
                if not version["exists"] or not isinstance(encoded, str):
                    raise InstallError(f"invalid retained migration input bytes: {journal}")
                try:
                    body = base64.b64decode(encoded.encode("ascii"), validate=True)
                except (ValueError, AttributeError) as exc:
                    raise InstallError(f"invalid retained migration input bytes: {journal}") from exc
                if hashlib.sha256(body).hexdigest() != version.get("sha256"):
                    raise InstallError(f"retained migration input digest mismatch: {journal}")
        for entry in data["paths"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] in seen:
                raise InstallError(f"invalid migration path entries: {journal}")
            seen.add(entry["path"])
            if data["inputs"].get(entry["path"]) != entry.get("before"):
                raise InstallError(f"migration input and target versions disagree: {journal}")
            path = Path(entry["path"])
            self._migration_target_root(path)
            if path not in cleanup_destinations:
                raise InstallError(f"migration target is not a pinned legacy cleanup destination: {path}")
            if not all(isinstance(entry.get(k), dict) for k in ("before", "after")):
                raise InstallError(f"migration path lacks exact state: {journal}")
            for key in ("before", "after"):
                version = entry[key]
                if not isinstance(version.get("exists"), bool):
                    raise InstallError(f"invalid migration file state: {journal}")
                if version["exists"]:
                    if not re.fullmatch(r"[0-9a-f]{64}", str(version.get("sha256", ""))):
                        raise InstallError(f"invalid migration file digest: {journal}")
                    if key == "after":
                        try:
                            body = base64.b64decode(version["bytes_b64"].encode("ascii"), validate=True)
                        except (KeyError, TypeError, ValueError, AttributeError) as exc:
                            raise InstallError(f"invalid migration replay bytes: {journal}") from exc
                        if hashlib.sha256(body).hexdigest() != version["sha256"]:
                            raise InstallError(f"migration replay digest mismatch: {journal}")
                elif set(version) != {"exists"}:
                    raise InstallError(f"absent migration file carries replay data: {journal}")
        return release

    def _verify_transferred_events(self, plan: dict[str, Any]) -> None:
        """Keep every planned legacy event byte-for-byte present until commit."""
        for host, events in plan.get("events", {}).items():
            target = self.user_root / "learnings" / host / "events.jsonl"
            self._safe_owned_path(target, self.user_root)
            if target.is_symlink() or not target.is_file():
                raise InstallError(f"legacy learning transfer changed: {target}")
            conflicts: list[str] = []
            self._event_destination_conflicts(host, events, conflicts)
            if conflicts:
                raise InstallError("legacy learning transfer changed: " + "; ".join(conflicts))
            lines = set(target.read_text(encoding="utf-8").splitlines())
            missing = [event["learning_id"] for event in events if event["raw"] not in lines]
            if missing:
                raise InstallError(f"legacy learning transfer changed: {target}: " + ", ".join(missing))

    def _verify_migration_native_state(self, release: Path, data: dict[str, Any], *, child_required: bool) -> None:
        """Check cleanup outputs and untouched native inputs before a resume commits.

        The private child owns only its recorded launcher/config projections.
        Those exact paths may move from the migration's retired state to the
        child state; every other native path must remain at the journaled state.
        """
        child = CorpusInstaller(release, self.env)
        child_owned = set(child._expected_owned(release))
        targets = {entry["path"]: entry for entry in data["paths"]}
        changed_inputs = [raw for raw, before in data["inputs"].items()
                          if raw not in targets and not self._matches_version(Path(raw), before)]
        if changed_inputs:
            raise InstallError("migration input changed after cleanup: " + ", ".join(changed_inputs))

        child_needs_verification = False
        for raw, entry in targets.items():
            path = Path(raw)
            if raw in child_owned:
                if not self._matches_version(path, entry["after"]):
                    child_needs_verification = True
                continue
            if not self._matches_version(path, entry["after"]):
                raise InstallError(f"migration target changed after cleanup: {path}")

        if not child_required and not child_needs_verification:
            return
        child_pending = any(row["kind"] == "install" for row in pending_status(self.state_root)["transactions"])
        if child_pending:
            if child_required:
                raise InstallError("pending private install prevents migration verification")
            # ``install`` below owns replaying this child journal.  Its preflight
            # validates its exact projections before it writes any of them.
            return
        record = child._old_record()
        if record is None or record.get("package_root") != str(release):
            raise InstallError("migration private install is missing its pinned release")
        child.verify()

    def _finish_migration(self, journal: Path, data: dict[str, Any]) -> dict[str, Any]:
        release = self._validate_migration(journal, data)
        plan, paths = data["plan"], data["paths"]
        try:
            with operation_scope(self.state_root):
                if data["phase"] in {"preflight", "cleanup"}:
                    self._assert_preflight_paths(paths)
                    targets = {entry["path"] for entry in paths}
                    for raw, before in data["inputs"].items():
                        if raw not in targets and not self._matches_version(Path(raw), before):
                            raise InstallError(f"migration input changed: {raw}")
                    for entry in paths:
                        path = Path(entry["path"])
                        if not entry["before"].get("exists"):
                            continue
                        backup = Path(data["backup_root"]) / "files" / str(path).lstrip("/")
                        self._safe_owned_path(backup, journal.parent)
                        if not self._matches_version(backup, entry["before"]):
                            if not self._matches_version(path, entry["before"]):
                                raise InstallError(f"original migration backup is missing or changed: {path}")
                            self._backup(Path(data["backup_root"]), path)
                    for host, events in plan["events"].items():
                        conflicts: list[str] = []
                        self._event_destination_conflicts(host, events, conflicts)
                        if conflicts:
                            raise InstallError("; ".join(conflicts))
                        target = self.user_root / "learnings" / host / "events.jsonl"
                        self._safe_owned_path(target, self.user_root)
                        prior = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
                        known = {json.loads(line)["learning_id"] for line in prior if line.strip()}
                        additions = [event["raw"] for event in events if event["learning_id"] not in known]
                        if additions:
                            _atomic_bytes(target, ("\n".join(prior + additions) + "\n").encode("utf-8"), 0o600)
                    self._verify_transferred_events(plan)
                    data["state"], data["phase"] = "APPLYING", "cleanup"
                    self._journal_write(journal, data)
                    for entry in paths:
                        path = Path(entry["path"])
                        if not self._matches_version(path, entry["after"]):
                            if not self._matches_version(path, entry["before"]):
                                raise InstallError(f"migration target changed: {path}")
                            self._write_planned(path, entry["after"], int(entry["mode"]))
                    # This durable boundary prevents any retry from deleting a new projection.
                    data["phase"] = "install"
                    self._journal_write(journal, data)
                if data["phase"] == "install":
                    self._verify_migration_native_state(release, data, child_required=False)
                    self._verify_transferred_events(plan)
                    installer = CorpusInstaller(release, self.env)
                    current = installer._old_record()
                    child_pending = any(row["kind"] == "install" for row in
                                        pending_status(self.state_root)["transactions"])
                    if current is not None and current.get("package_root") == str(release) and not child_pending:
                        # A lost parent receipt must not publish a second installation.
                        installer.verify()
                    else:
                        installer.install()
                    data["phase"] = "verify"
                    self._journal_write(journal, data)
                self._verify_migration_native_state(release, data, child_required=True)
                self._verify_transferred_events(plan)
                self.verify()
                # The last pre-commit observation is deliberately repeated: a
                # cooperative old collector or native writer can race a resume.
                # It cannot make a noncooperating producer atomic after this check.
                self._verify_migration_native_state(release, data, child_required=True)
                self._verify_transferred_events(plan)
                data.update(state="COMMITTED", phase="complete", committed_at=int(time.time()))
                self._journal_write(journal, data)
                return {"preview": False, "migration_id": journal.parent.name,
                        "backup_root": data["backup_root"], "package_root": str(release), **plan}
        except BaseException as exc:
            data.update(state="NEEDS_RECOVERY", error=type(exc).__name__)
            self._journal_write(journal, data)
            raise

    @_serialized
    def migrate(self, apply: bool = False, yes: bool = False) -> dict[str, Any]:
        pending = pending_status(self.state_root)["transactions"]
        migrations = [item for item in pending if item["kind"] == "migrate"]
        if len(migrations) > 1:
            raise InstallError("multiple pending migration journals require explicit recovery")
        if migrations:
            journal = Path(migrations[0]["path"])
            data = _read_json(journal)
            self._validate_migration(journal, data)
            if not apply:
                return {"preview": True, **data["plan"], "recovery_journal": str(journal), "phase": data["phase"]}
            if not yes:
                raise InstallError("migration apply requires --yes")
            return self._finish_migration(journal, data)
        if apply:
            try:
                guard_pending(self.state_root)
            except TransactionError as exc:
                raise InstallError(str(exc)) from exc
        plan, inputs = self._plan_migration()
        if not apply:
            return {"preview": True, **plan}
        if not yes:
            raise InstallError("migration apply requires --yes")
        if plan["needs_action"]:
            raise InstallError("legacy migration has unresolved ownership: " + "; ".join(plan["needs_action"]))
        release, entries, digest = self._copy_release(self._package_files(), False)
        paths = self._migration_paths(plan, release, inputs)
        changed = [raw for raw, before in inputs.items() if not self._matches_version(Path(raw), before)]
        if changed:
            raise InstallError("migration input changed during planning; retry with a fresh plan: " + ", ".join(changed))
        # Refuse an unlisted/user-edited shared destination before retiring anything.
        prior = self._old_record()
        retiring = set(plan["deletes"])
        for raw, expected in self._expected_owned(release).items():
            path = Path(raw)
            self._safe_owned_path(path, self.bin_root if path.parent == self.bin_root else self.launch_root)
            if raw not in retiring and path.exists() and _sha256(path) != expected and \
                    _sha256(path) != self._owned_hash(prior, path):
                raise InstallError(f"private install cannot replace user-owned paths: {path}")
        migration_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
        journal = self.runtime / "migrations" / migration_id / "journal.json"
        backup_root = journal.parent / "backup"
        path_inputs = {entry["path"] for entry in paths}
        journal_data = {"schema_version": SCHEMA_VERSION, "owner": "installer", "kind": "migrate",
                        "state": "PREPARED", "phase": "preflight", "plan": plan, "paths": paths,
                        "inputs": {raw: ({k: v for k, v in before.items() if k != "bytes_b64"}
                                          if raw in path_inputs else before)
                                   for raw, before in inputs.items()},
                        "prior_install": self._file_version(self.record_path),
                        "release": {"package_root": str(release), "installed_files": entries, "release_digest": digest},
                        "backup_root": str(backup_root), "created_at": int(time.time())}
        self._journal_write(journal, journal_data)
        return self._finish_migration(journal, journal_data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-bios corpus")
    parser.add_argument("--repo", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--domains")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--with", dest="with_capabilities")
    onboard = subparsers.add_parser("onboard")
    onboard.add_argument("--domains")
    onboard.add_argument("--dry-run", action="store_true")
    onboard.add_argument("--with", dest="with_capabilities")
    subparsers.add_parser("verify")
    subparsers.add_parser("status")
    uninstall = subparsers.add_parser("uninstall")
    uninstall.add_argument("--dry-run", action="store_true")
    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--yes", action="store_true")
    reset = subparsers.add_parser("reset")
    reset.add_argument("--dry-run", action="store_true")
    reset.add_argument("--apply", action="store_true")
    reset.add_argument("--yes", action="store_true")
    reset.add_argument("--expected-revision", help="reset preview generation to accept")
    args = parser.parse_args(argv)
    installer = CorpusInstaller(Path(args.repo) if args.repo else Path(__file__).resolve().parent.parent)
    try:
        if args.command in {"install", "onboard"}:
            if args.with_capabilities:
                raise InstallError("optional --with dependencies are not installed by private corpus mode")
            result = installer.install(args.domains, args.dry_run)
        elif args.command == "verify":
            result = installer.verify()
        elif args.command == "status":
            result = installer.status()
        elif args.command == "uninstall":
            result = installer.uninstall(args.dry_run)
        elif args.command == "reset":
            result = installer.reset(apply=args.apply and not args.dry_run, yes=args.yes,
                                     expected_revision=args.expected_revision)
        else:
            result = installer.migrate(apply=args.apply and not args.dry_run, yes=args.yes)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except InstallError as exc:
        print(f"corpus-install: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
