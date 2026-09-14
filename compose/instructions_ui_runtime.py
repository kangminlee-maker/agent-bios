"""Load the shipped pure-Python UI wheels offline into one process-owned directory."""
from __future__ import annotations

import atexit
from email.parser import BytesParser
import hashlib
import importlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import threading
from typing import Any
import zipfile
import zlib


SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
_LOCK = threading.RLock()
_ACTIVE: tuple[str, tempfile.TemporaryDirectory[str]] | None = None


class UiRuntimeError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _bundle_id(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical({key: value for key, value in manifest.items() if key != "bundle_id"})).hexdigest()


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    result = []
    seen = set()
    expanded = 0
    for info in archive.infolist():
        raw = info.filename.rstrip("/")
        path = PurePosixPath(raw)
        if not raw or path.is_absolute() or "\\" in raw or path.as_posix() != raw \
                or any(part in {".", ".."} for part in path.parts) \
                or any(ord(character) < 32 or ord(character) == 127 for character in raw):
            raise UiRuntimeError(f"unsafe UI wheel member: {info.filename!r}")
        if raw in seen:
            raise UiRuntimeError(f"duplicate UI wheel member: {raw}")
        seen.add(raw)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
            raise UiRuntimeError(f"non-regular UI wheel member: {raw}")
        if info.is_dir():
            continue
        if info.flag_bits & 1:
            raise UiRuntimeError(f"encrypted UI wheel member: {raw}")
        if path.suffix.lower() in {".so", ".pyd", ".dll", ".dylib", ".pth", ".pyc"} \
                or path.parts[0].endswith(".data"):
            raise UiRuntimeError(f"UI wheel requires unsupported installation behavior: {raw}")
        expanded += info.file_size
        if expanded > MAX_EXPANDED_BYTES:
            raise UiRuntimeError("UI wheel exceeds the extraction size limit")
        result.append(info)
    if not result:
        raise UiRuntimeError("UI wheel has no files")
    return result


def wheel_metadata(filename: str, data: bytes) -> dict[str, Any]:
    """Read wheel metadata and licensing without importing its Python code."""
    if Path(filename).name != filename or not re.fullmatch(r"[A-Za-z0-9_.!+-]+-py[0-9.]+-none-any\.whl", filename):
        raise UiRuntimeError(f"UI runtime requires a pure Python universal wheel: {filename}")
    if not data or len(data) > MAX_ARCHIVE_BYTES:
        raise UiRuntimeError(f"invalid UI wheel size: {filename}")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = _members(archive)
            names = {member.filename for member in members}
            metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_paths) != 1:
                raise UiRuntimeError(f"UI wheel needs exactly one distribution metadata file: {filename}")
            metadata_path = metadata_paths[0]
            info_root = metadata_path.rsplit("/", 1)[0]
            wheel_path = info_root + "/WHEEL"
            if wheel_path not in names:
                raise UiRuntimeError(f"UI wheel lacks WHEEL metadata: {filename}")
            metadata = BytesParser().parsebytes(archive.read(metadata_path))
            wheel = BytesParser().parsebytes(archive.read(wheel_path))
            tags = wheel.get_all("Tag", [])
            if wheel.get("Root-Is-Purelib", "").lower() != "true" or not tags \
                    or any(not re.fullmatch(r"py[0-9.]+-none-any", tag) for tag in tags):
                raise UiRuntimeError(f"UI wheel is not pure Python: {filename}")
            license_files = sorted(name for name in names if name.startswith(info_root + "/") and (
                "/licenses/" in name.lower() or PurePosixPath(name).name.lower().startswith(("license", "licence", "copying"))))
            if not license_files or any(not archive.read(name).strip() for name in license_files):
                raise UiRuntimeError(f"UI wheel lacks an upstream license: {filename}")
            modules = set()
            for name in names:
                parts = PurePosixPath(name).parts
                if parts[0].endswith(".dist-info"):
                    continue
                root = parts[0][:-3] if len(parts) == 1 and parts[0].endswith(".py") else parts[0]
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", root):
                    modules.add(root)
            name, version = metadata.get("Name"), metadata.get("Version")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) \
                    or not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_.!+]+", version) or not modules:
                raise UiRuntimeError(f"invalid UI distribution metadata: {filename}")
            return {"name": _normalized_name(name), "version": version, "filename": filename,
                    "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
                    "expanded_bytes": sum(member.file_size for member in members),
                    "modules": sorted(modules), "license_files": license_files,
                    "requires_python": metadata.get("Requires-Python", ""),
                    "requires_dist": metadata.get_all("Requires-Dist", [])}
    except (zipfile.BadZipFile, KeyError, OSError, UnicodeError, RuntimeError, ValueError, EOFError, zlib.error) as exc:
        if isinstance(exc, UiRuntimeError):
            raise
        raise UiRuntimeError(f"cannot read UI wheel {filename}: {exc}") from exc


def _read_bundle(repo: Path) -> tuple[dict[str, Any], list[tuple[dict[str, Any], bytes]]]:
    bundle = Path(repo) / "compose/ui_runtime"
    manifest_path = bundle / "manifest.json"
    if bundle.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise UiRuntimeError("bundled UI runtime manifest is missing or unsafe; reinstall the agent-bios package")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UiRuntimeError(f"cannot read UI runtime manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION \
            or manifest.get("python_requirement") != ">=3.11" or manifest.get("source") != "pypi":
        raise UiRuntimeError("unsupported UI runtime manifest")
    if manifest.get("bundle_id") != _bundle_id(manifest):
        raise UiRuntimeError("UI runtime manifest fingerprint mismatch")
    requirements = manifest.get("root_requirement")
    rows = manifest.get("packages")
    if not isinstance(requirements, str) or not re.fullmatch(r"textual==[0-9][A-Za-z0-9_.!+]*", requirements) \
            or not isinstance(rows, list) or not rows:
        raise UiRuntimeError("UI runtime manifest has no valid package inventory")
    supplied = set()
    filenames = set()
    modules = set()
    files = set()
    expanded = 0
    archives = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
            raise UiRuntimeError("UI runtime manifest has an invalid package row")
        filename = row["filename"]
        if Path(filename).name != filename or filename in filenames:
            raise UiRuntimeError(f"invalid or duplicate UI wheel name: {filename}")
        path = bundle / filename
        if path.is_symlink() or not path.is_file():
            raise UiRuntimeError(f"bundled UI wheel missing or unsafe: {filename}")
        if path.stat().st_size != row.get("size_bytes") or path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise UiRuntimeError(f"UI wheel size mismatch: {filename}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row.get("sha256"):
            raise UiRuntimeError(f"UI wheel SHA256 mismatch: {filename}")
        actual = wheel_metadata(filename, data)
        if actual != row:
            raise UiRuntimeError(f"UI wheel metadata differs from its manifest: {filename}")
        if row["name"] in supplied or modules.intersection(row["modules"]):
            raise UiRuntimeError(f"UI distributions overlap: {filename}")
        supplied.add(row["name"])
        filenames.add(filename)
        modules.update(row["modules"])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = {member.filename for member in _members(archive)}
        if files.intersection(names):
            raise UiRuntimeError(f"UI wheel paths overlap: {filename}")
        files.update(names)
        expanded += row["expanded_bytes"]
        if expanded > MAX_EXPANDED_BYTES:
            raise UiRuntimeError("UI runtime exceeds the extraction size limit")
        archives.append((row, data))
    if {path.name for path in bundle.iterdir() if path.name != "manifest.json"} != filenames:
        raise UiRuntimeError("UI runtime directory differs from its exact wheel inventory")
    if not any(f"{row['name']}=={row['version']}" == requirements for row in rows):
        raise UiRuntimeError("UI runtime root Textual requirement is not present")
    return manifest, archives


def runtime_inventory(repo: Path) -> dict[str, Any]:
    """Report bundled hashes, purity, and licenses without extraction or UI imports."""
    try:
        manifest, _archives = _read_bundle(repo)
    except (UiRuntimeError, OSError) as exc:
        return {"schema_version": SCHEMA_VERSION, "status": "unavailable", "issues": [str(exc)], "packages": []}
    return {**manifest, "status": "available", "issues": [],
            "package_count": len(manifest["packages"]),
            "size_bytes": sum(row["size_bytes"] for row in manifest["packages"]),
            "expanded_bytes": sum(row["expanded_bytes"] for row in manifest["packages"]),
            "license_file_count": sum(len(row["license_files"]) for row in manifest["packages"]),
            "pure_python": True}


def _preloaded_modules(modules: set[str], active: Path | None) -> list[str]:
    conflicts = []
    for name, module in tuple(sys.modules.items()):
        if name.split(".", 1)[0] not in modules:
            continue
        filename = getattr(module, "__file__", None)
        if active is not None and isinstance(filename, str):
            try:
                Path(filename).resolve().relative_to(active)
                continue
            except (ValueError, OSError):
                pass
        conflicts.append(name)
    return sorted(conflicts)


def _cleanup_runtime() -> None:
    global _ACTIVE
    if _ACTIVE is not None:
        _bundle, temporary = _ACTIVE
        sys.path[:] = [entry for entry in sys.path if entry != temporary.name]
        temporary.cleanup()
        _ACTIVE = None


def release_ui_runtime() -> None:
    """Release owned files immediately before process handoff; UI reuse needs a fresh process."""
    with _LOCK:
        _cleanup_runtime()


def activate_ui_runtime(repo: Path) -> Path:
    """Activate only verified shipped modules; imports must follow this call."""
    global _ACTIVE
    if sys.version_info < (3, 11):
        raise UiRuntimeError("the bundled UI runtime requires Python 3.11 or newer")
    with _LOCK:
        manifest, archives = _read_bundle(repo)
        if _ACTIVE is not None and _ACTIVE[0] != manifest["bundle_id"]:
            raise UiRuntimeError("another UI bundle is active; start a fresh process for this agent-bios package")
        active = Path(_ACTIVE[1].name).resolve() if _ACTIVE is not None else None
        names = {name for row, _data in archives for name in row["modules"]}
        conflicts = _preloaded_modules(names, active)
        if conflicts:
            raise UiRuntimeError("UI dependencies were imported before bundled activation: " + ", ".join(conflicts[:8])
                                 + "; start a fresh process and activate the bundle before importing UI modules")
        if active is not None:
            if not active.is_dir():
                raise UiRuntimeError("the active UI runtime directory is missing; start a fresh process")
            return active
        parent = Path(tempfile.gettempdir()).resolve()
        home = Path.home().resolve()
        if parent == home or home in parent.parents:
            parent = Path("/tmp").resolve()
        temporary = tempfile.TemporaryDirectory(prefix="agent-bios-ui-", dir=parent)
        target = Path(temporary.name)
        try:
            for _row, data in archives:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in _members(archive):
                        path = target.joinpath(*PurePosixPath(member.filename).parts)
                        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with path.open("xb") as output:
                            output.write(archive.read(member))
                        path.chmod(0o600)
            sys.path.insert(0, str(target))
            importlib.invalidate_caches()
            _ACTIVE = (manifest["bundle_id"], temporary)
            atexit.register(_cleanup_runtime)
            return target
        except BaseException:
            temporary.cleanup()
            raise
