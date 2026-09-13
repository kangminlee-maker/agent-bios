"""Shared lock and durable pending-operation visibility for corpus state.

The corpus store owns source bytes and the installer owns projections.  Neither
may publish independently while an install, reset or migration is incomplete: a reader
must see the completed generation or a clear recovery requirement, never a
mixture.  Journals deliberately contain no token bytes.
"""
from __future__ import annotations

import contextlib
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import threading
from typing import Any, Iterator


PENDING_STATES = frozenset({"PREPARED", "APPLYING", "NEEDS_RECOVERY"})
_local = threading.local()


class TransactionError(RuntimeError):
    pass


class TransactionPendingError(TransactionError):
    pass


def reject_symlink_ancestors(path: Path) -> None:
    """Refuse redirected user paths, allowing only macOS's fixed system aliases.

    /var, /tmp and /etc are root-owned aliases to /private on macOS. They precede
    ordinary temporary HOME/state roots and are not user-controlled redirections.
    The exception names their exact destinations and never applies to the leaf,
    a same-named link elsewhere, or a user-owned link.
    """
    for ancestor in (path, *path.parents):
        if not ancestor.is_symlink():
            continue
        system_alias = (sys.platform == "darwin" and ancestor != path
                        and ancestor in {Path("/var"), Path("/tmp"), Path("/etc")}
                        and ancestor.lstat().st_uid == 0
                        and ancestor.parent / os.readlink(ancestor) == Path("/private") / ancestor.name)
        if not system_alias:
            raise TransactionError(f"refusing symlink transaction target: {ancestor}")


def _key(state_root: Path) -> str:
    return str(Path(state_root).expanduser().resolve())


def _depths(name: str) -> dict[str, int]:
    value = getattr(_local, name, None)
    if value is None:
        value = {}
        setattr(_local, name, value)
    return value


@contextlib.contextmanager
def _transaction_lock(state_root: Path, *, readonly: bool) -> Iterator[bool]:
    root = Path(state_root).expanduser()
    if root.is_symlink():
        raise TransactionError(f"unsafe corpus state root: {root}")
    if readonly:
        reject_symlink_ancestors(root)
    key = _key(root)
    depths = _depths("lock_depths")
    if depths.get(key, 0):
        depths[key] += 1
        try:
            yield True
        finally:
            depths[key] -= 1
        return
    if not readonly:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = root / ".corpus-store.lock"
    if lock.is_symlink():
        raise TransactionError(f"unsafe corpus transaction lock: {lock}")
    flags = (os.O_RDONLY | os.O_NONBLOCK if readonly else os.O_CREAT | os.O_RDWR) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock, flags, 0o600)
    except FileNotFoundError:
        if not readonly:
            raise
        yield False
        return
    try:
        if readonly and not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise TransactionError(f"unsafe corpus transaction lock: {lock}")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | (fcntl.LOCK_NB if readonly else 0))
        except BlockingIOError:
            if not readonly:
                raise
            yield False
            return
        depths[key] = 1
        try:
            yield True
        finally:
            depths.pop(key, None)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def transaction_lock(state_root: Path) -> Iterator[None]:
    """The single re-entrant cross-process lock for store and installer work."""
    with _transaction_lock(state_root, readonly=False):
        yield


@contextlib.contextmanager
def try_transaction_lock(state_root: Path) -> Iterator[bool]:
    """Observe under the existing lock, or defer without blocking or creating state."""
    with _transaction_lock(state_root, readonly=True) as acquired:
        yield acquired


@contextlib.contextmanager
def operation_scope(state_root: Path) -> Iterator[None]:
    """Permit the coordinating writer to inspect its own pending journal."""
    key = _key(Path(state_root))
    depths = _depths("operation_depths")
    depths[key] = depths.get(key, 0) + 1
    try:
        yield
    finally:
        remaining = depths[key] - 1
        if remaining:
            depths[key] = remaining
        else:
            depths.pop(key, None)


def operation_scope_active(state_root: Path) -> bool:
    return bool(_depths("operation_depths").get(_key(Path(state_root)), 0))


def _journal_records(state_root: Path, *, coordinator_only: bool = False) -> list[dict[str, Any]]:
    root = Path(state_root).expanduser() / "runtime"
    records: list[dict[str, Any]] = []
    # ``resets`` predates the unified transaction directory and remains visible
    # so an old interrupted reset is never silently treated as complete.
    for directory in (root / "transactions", root / "installer-transactions", root / "resets", root / "migrations"):
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise TransactionError(f"unsafe transaction journal root: {directory}")
        for journal in sorted(directory.glob("*/journal.json")):
            if journal.parent.is_symlink() or journal.is_symlink() or not journal.is_file():
                raise TransactionError(f"unsafe transaction journal: {journal}")
            try:
                value = json.loads(journal.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise TransactionError(f"unreadable transaction journal: {journal}") from exc
            if not isinstance(value, dict):
                raise TransactionError(f"invalid transaction journal: {journal}")
            # Store owns its source-only install journal.  It can safely finish
            # its own PREPARED source pair under the same lock; launcher/config
            # readers must only block on the wider installer/reset coordinator.
            coordinator = directory.name in {"installer-transactions", "resets", "migrations"} or value.get("owner") == "installer"
            if value.get("state") in PENDING_STATES and (not coordinator_only or coordinator):
                fallback = "migrate" if directory.name == "migrations" else "reset" if coordinator else "source"
                records.append({"path": str(journal), "kind": value.get("kind", fallback),
                                "owner": "installer" if coordinator else "store",
                                "state": value.get("state"), "phase": value.get("phase")})
    return records


def pending_status(state_root: Path) -> dict[str, Any]:
    records = _journal_records(state_root)
    return {"pending": bool(records), "transactions": records}


def pending_operations(state_root: Path) -> list[dict[str, Any]]:
    """Return pending journals for source readers and management views."""
    return pending_status(state_root)["transactions"]


def guard_pending(state_root: Path) -> None:
    """Fail before a config/source reader consumes an incomplete publication."""
    key = _key(Path(state_root))
    if _depths("operation_depths").get(key, 0):
        return
    pending = _journal_records(state_root, coordinator_only=True)
    if pending:
        first = pending[0]
        raise TransactionPendingError(
            "corpus install/reset/migration needs recovery before reading current configuration: "
            f"{first['path']} ({first['state']})"
        )


def _valid_release(state_root: Path, record: dict[str, Any]) -> Path:
    raw = record.get("package_root")
    digest = record.get("release_digest")
    if not isinstance(raw, str) or not isinstance(digest, str):
        raise TransactionPendingError("private install record has no confirmed immutable release")
    root = (Path(state_root).expanduser() / "runtime" / "releases").absolute()
    release = Path(raw)
    try:
        release.absolute().relative_to(root)
    except ValueError as exc:
        raise TransactionPendingError("private install record points outside immutable releases") from exc
    if release.name != digest or release.is_symlink() or not release.is_dir():
        raise TransactionPendingError("private install record has an invalid immutable release")
    entries = record.get("installed_files")
    if not isinstance(entries, list) or not entries:
        raise TransactionPendingError("private install record has no release inventory")
    # The release digest is the digest of the ordered path+bytes stream.  The
    # installer computes it before any pointer publication, so this is a cheap
    # structural confirmation suitable for a config reader; full verification
    # remains CorpusInstaller.verify's responsibility.
    actual = hashlib.sha256()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise TransactionPendingError("private install record has invalid release inventory")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise TransactionPendingError("private install record has unsafe release inventory")
        member = release / relative
        if member.is_symlink() or not member.is_file():
            raise TransactionPendingError("confirmed release member is unavailable")
        data = member.read_bytes()
        actual.update(entry["path"].encode("utf-8") + b"\0" + data + b"\0")
    if actual.hexdigest() != digest:
        raise TransactionPendingError("confirmed release digest does not match inventory")
    return release


def confirmed_release(state_root: Path) -> Path:
    """Return the last fully confirmed release while a coordinator is pending.

    A pending update's ``after`` record is deliberately not trusted.  The
    journal's exact ``before`` private-install bytes identify the previous
    generation; a first installation has none and therefore fails closed.
    """
    root = Path(state_root).expanduser()
    pending = _journal_records(root, coordinator_only=True)
    migration = next((item for item in pending if item["kind"] == "migrate"), None)
    if migration is not None:
        try:
            value = json.loads(Path(migration["path"]).read_text(encoding="utf-8"))
            before = value["prior_install"]
            encoded = before.get("bytes_b64") if isinstance(before, dict) else None
            if not isinstance(encoded, str):
                raise ValueError("no prior private install")
            record = json.loads(base64.b64decode(encoded.encode("ascii"), validate=True))
        except (KeyError, OSError, ValueError, TypeError) as exc:
            raise TransactionPendingError("pending migration has no confirmed prior private install") from exc
        if not isinstance(record, dict):
            raise TransactionPendingError("prior migration install record is invalid")
        return _valid_release(root, record)
    install = next((item for item in pending if item["kind"] == "install"), None)
    if install is not None:
        journal = Path(install["path"])
        try:
            value = json.loads(journal.read_text(encoding="utf-8"))
            record_entry = next(entry for entry in value.get("paths", [])
                                if isinstance(entry, dict) and str(entry.get("path", "")).endswith(
                                    "/runtime/private-install.json"))
            before = record_entry.get("before", {})
            encoded = before.get("bytes_b64") if isinstance(before, dict) else None
            if not isinstance(encoded, str):
                raise ValueError("no prior private-install record")
            record = json.loads(base64.b64decode(encoded.encode("ascii"), validate=True))
        except (StopIteration, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise TransactionPendingError("first or incomplete install has no confirmed prior release") from exc
        if not isinstance(record, dict):
            raise TransactionPendingError("prior private-install record is invalid")
        return _valid_release(root, record)
    path = root / "runtime" / "private-install.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TransactionPendingError("pending reset has no confirmed private install") from exc
    if not isinstance(record, dict):
        raise TransactionPendingError("confirmed private install is invalid")
    return _valid_release(root, record)
