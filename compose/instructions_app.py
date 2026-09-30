#!/usr/bin/env python3
"""Explicit app discovery and per-task instructions context delivery.

The Codex app pulls through a registered skill; Claude Desktop pulls through a
generated `.mcpb` bundle whose server calls the session operations here.
"""
from __future__ import annotations
try:
    from host_platform import cli_argv, create_junction, python_argv, runtime_environment
except ImportError:
    from .host_platform import cli_argv, create_junction, python_argv, runtime_environment

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import tempfile
from typing import Any
import zipfile

try:
    from instructions_store import InstructionsStore, InstructionsStoreError
    from instructions_transaction import (environment_value, TransactionError, confirmed_release, guard_pending,
                                    reject_symlink_ancestors, transaction_lock)
except ImportError:
    from .instructions_store import InstructionsStore, InstructionsStoreError
    from .instructions_transaction import (environment_value, TransactionError, confirmed_release, guard_pending,
                                     reject_symlink_ancestors, transaction_lock)


SCHEMA_VERSION = 1
BRIDGE_MEMBERS = ("SKILL.md", "agents/openai.yaml", "scripts/bridge.py",
                  "scripts/instructions_transaction.py", "scripts/host_platform.py", "bridge.json")
PREVIOUS_BRIDGE_MEMBERS = tuple(x for x in BRIDGE_MEMBERS if x != "scripts/host_platform.py")
LEGACY_BRIDGE_MEMBERS = ("SKILL.md", "agents/openai.yaml", "scripts/bridge.py",
                         "scripts/corpus_transaction.py", "bridge.json")
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
# Desktop sends no conversation identity with a tool call (2.9939.4 and 2.16120.0,
# design/app-session-reach/2026-09-30T0645--20084c8--desktop-mcpb-qualification.md),
# so AppSessions mints one; the prefix keeps it apart from Codex task ids.
DESKTOP_SESSION_ID = re.compile(r"desktop-[a-f0-9]{32}\Z")
END_MARKER = re.compile(r"agent-bios end [a-f0-9]{12}\Z")
# Receipt host -> the snapshot host whose items it receives.
APP_HOSTS = {"codex": "codex", "claude-desktop": "claude"}
# The smallest inline boundary Desktop has shown (2.9939.4). 2.16120.0 inlined
# more, so crossing it is disclosed, never refused.
DESKTOP_INLINE_FLOOR = 49_152
DESKTOP_BUNDLE_MEMBERS = ("manifest.json", "server/desktop.json", "server/host_platform.py",
                          "server/instructions_transaction.py", "server/server.py")


class AppError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    reject_symlink_ancestors(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AppError(f"unreadable app state: {path}") from exc
    if not isinstance(value, dict):
        raise AppError(f"invalid app state: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    reject_symlink_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _tree_digest(members: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(members.items()):
        digest.update(relative.encode("utf-8") + b"\0" + data + b"\0")
    return digest.hexdigest()


def _roots(environ: dict[str, str] | None) -> tuple[dict[str, str], Path, Path, Path]:
    env = dict(os.environ if environ is None else environ)
    home = Path(env.get("HOME", str(Path.home()))).expanduser().absolute()
    state = Path(env.get("AGENT_BIOS_STATE_DIR", str(home / ".local/share/agent-bios"))).expanduser().absolute()
    user = Path(environment_value(env, "AGENT_BIOS_INSTRUCTIONS_DIR", "AGENT_BIOS_CORPUS_DIR", str(home / ".config/agent-bios/corpus"))).expanduser().absolute()
    return env, home, state, user


class AppBridge:
    """Own one explicit-only skill symlink; retain immutable private generations."""

    def __init__(self, repo: Path, environ: dict[str, str] | None = None):
        self.repo = Path(repo).absolute()
        self.env, self.home, self.state_root, self.user_root = _roots(environ)
        self.target = self.home / ".agents/skills/agent-bios"
        self.generations = self.state_root / "runtime/app-bridges"

    def _base_config(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "home": str(self.home),
                "state_root": str(self.state_root), "user_root": str(self.user_root),
                "discovery_path": str(self.target)}

    def _config(self) -> dict[str, Any]:
        config = self._base_config()
        if "AGENT_LAUNCH_VENV" in self.env:
            value = self.env["AGENT_LAUNCH_VENV"]
            config["launch_venv"] = str(Path(value).expanduser().absolute()) if value else ""
        else:
            current = self._owned_target()
            if current is not None:
                saved = _read_json(current / "bridge.json")
                if "launch_venv" in saved:
                    config["launch_venv"] = saved["launch_venv"]
                if "python_binding" in saved:
                    config["python_binding"] = saved["python_binding"]
        binding = runtime_environment(self.env)
        if binding:
            config["python_binding"] = binding
        return config

    def _source_members(self) -> dict[str, bytes]:
        reject_symlink_ancestors(self.state_root)
        guard_pending(self.state_root)
        release = confirmed_release(self.state_root)
        source = release / "compose/app_bridge"
        members = {}
        canonical = (release / "compose/instructions_transaction.py").is_file()
        inventory = BRIDGE_MEMBERS if canonical else LEGACY_BRIDGE_MEMBERS
        for name in inventory:
            if name == "bridge.json":
                members[name] = _json_bytes(self._config())
                continue
            path = release / "compose" / Path(name).name if name in {
                "scripts/instructions_transaction.py", "scripts/corpus_transaction.py", "scripts/host_platform.py"
            } else source / name
            reject_symlink_ancestors(path)
            if not path.is_file():
                raise AppError(f"installed release has no app bridge member: {path}")
            members[name] = path.read_bytes()
            if os.name == "nt" and name == "SKILL.md":
                interpreter = sys.executable.replace("'", "''")
                command = python_argv(Path('$BRIDGE'))
                prefix = '& ' + ' '.join(('"$BRIDGE"' if word == '$BRIDGE' else "'" + word.replace("'", "''") + "'") for word in command)
                text = members[name].decode("utf-8").replace('python3 "$BRIDGE"', prefix)
                text += "\nOn Windows use PowerShell and the bundled interpreter shown above. Set $BRIDGE to the absolute scripts/bridge.py path beside this skill. Follow returned command argument arrays for setup; do not translate them into Bash commands.\n"
                members[name] = text.encode("utf-8")
        return members

    def _owned_target(self) -> Path | None:
        reject_symlink_ancestors(self.target.parent)
        if not os.path.lexists(self.target):
            return None
        if not (self.target.is_symlink() or (os.name == "nt" and self.target.is_junction())):
            raise AppError(f"preserving unowned app skill: {self.target}")
        raw = self.target.resolve() if os.name == "nt" else Path(os.readlink(self.target))
        reject_symlink_ancestors(self.generations)
        same_parent = raw.parent.resolve() == self.generations.resolve() if os.name == "nt" else raw.parent == self.generations
        if not raw.is_absolute() or not same_parent or not re.fullmatch(r"[a-f0-9]{64}", raw.name):
            raise AppError(f"preserving unowned app skill link: {self.target}")
        if os.name == "nt":
            # Keep the saved root spelling: canonicalizing the record itself would
            # invalidate its exact ownership/context checks. Only compare locations.
            raw = self.generations / raw.name
        reject_symlink_ancestors(raw)
        if not raw.is_dir():
            raise AppError(f"owned app skill generation is unavailable: {raw}")
        paths = list(raw.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise AppError(f"preserving redirected app skill generation: {raw}")
        files = {path.relative_to(raw).as_posix(): path.read_bytes() for path in paths if path.is_file()}
        if set(files) not in (set(BRIDGE_MEMBERS), set(PREVIOUS_BRIDGE_MEMBERS), set(LEGACY_BRIDGE_MEMBERS)) or _tree_digest(files) != raw.name:
            raise AppError(f"preserving changed app skill generation: {raw}")
        config = _read_json(raw / "bridge.json")
        base = self._base_config()
        if (any(config.get(key) != value for key, value in base.items())
                or set(config) - set(base) - {"launch_venv", "python_binding"}
                or ("launch_venv" in config and (not isinstance(config["launch_venv"], str)
                    or (config["launch_venv"] and not Path(config["launch_venv"]).is_absolute())))):
            raise AppError(f"app skill belongs to different private root settings: {self.target}")
        return raw

    def status(self) -> dict[str, Any]:
        try:
            target = self._owned_target()
            return {"registered": target is not None, "discovery_path": str(self.target),
                    "generation": str(target) if target else None, "implicit_invocation": False,
                    "native_discovery": "unverified", "session_activation": "explicit-use-only"}
        except (AppError, OSError, TransactionError) as exc:
            return {"registered": False, "discovery_path": str(self.target), "needs_action": [str(exc)],
                    "native_discovery": "unverified", "session_activation": "explicit-use-only"}

    def has_owned_registration(self) -> bool:
        """Identify our link namespace without opening unrelated skill contents."""
        try:
            reject_symlink_ancestors(self.target.parent)
            if not (self.target.is_symlink() or (os.name == "nt" and self.target.is_junction())):
                return False
            target = self.target.resolve() if os.name == "nt" else Path(os.readlink(self.target))
            reject_symlink_ancestors(self.generations)
            same_parent = target.parent.resolve() == self.generations.resolve() if os.name == "nt" else target.parent == self.generations
            return target.is_absolute() and same_parent
        except (OSError, TransactionError):
            return False

    def managed_status(self) -> dict[str, Any]:
        """Lifecycle view: foreign native paths are outside this installer."""
        if not self.has_owned_registration():
            return {"registered": False, "managed": False, "discovery_path": str(self.target)}
        return {**self.status(), "managed": True}

    def register(self, dry_run: bool = False) -> dict[str, Any]:
        reject_symlink_ancestors(self.state_root)
        if dry_run:
            before = self._owned_target()
            members = self._source_members()
            generation = self.generations / _tree_digest(members)
            return {"registered": before is not None, "dry_run": True, "changed": before != generation,
                    "discovery_path": str(self.target), "generation": str(generation),
                    "implicit_invocation": False, "native_discovery": "unverified",
                    "session_activation": "explicit-use-only"}
        with transaction_lock(self.state_root):
            before = self._owned_target()
            members = self._source_members()
            generation = self.generations / _tree_digest(members)
            result = {"registered": True, "dry_run": False, "changed": before != generation,
                      "discovery_path": str(self.target), "generation": str(generation),
                      "implicit_invocation": False, "native_discovery": "unverified",
                      "session_activation": "explicit-use-only"}
            reject_symlink_ancestors(generation)
            if generation.exists():
                paths = list(generation.rglob("*"))
                actual = {path.relative_to(generation).as_posix(): path.read_bytes()
                          for path in paths if path.is_file() and not path.is_symlink()}
                if any(path.is_symlink() for path in paths) or actual != members:
                    raise AppError(f"app bridge generation collision: {generation}")
            else:
                self.generations.mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = Path(tempfile.mkdtemp(prefix=".bridge-", dir=self.generations))
                try:
                    for relative, data in members.items():
                        path = temporary / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                        path.chmod(0o600)
                    os.replace(temporary, generation)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            self.target.parent.mkdir(parents=True, exist_ok=True)
            if self._owned_target() != before:
                raise AppError("app skill changed while preparing registration")
            descriptor, temporary = tempfile.mkstemp(prefix=".agent-bios-link-", dir=self.target.parent)
            os.close(descriptor)
            os.unlink(temporary)
            try:
                if os.name == "nt":
                    create_junction(Path(temporary), generation)
                    if before is not None:
                        self.target.rmdir()
                else:
                    os.symlink(str(generation), temporary)
                os.replace(temporary, self.target)
            finally:
                if os.path.lexists(temporary):
                    os.rmdir(temporary) if os.name == "nt" and Path(temporary).is_junction() else os.unlink(temporary)
            return result

    def unregister(self, dry_run: bool = False) -> dict[str, Any]:
        reject_symlink_ancestors(self.state_root)
        if dry_run or not os.path.lexists(self.target):
            before = self._owned_target()
            return {"registered": before is not None, "dry_run": dry_run, "changed": before is not None,
                    "discovery_path": str(self.target), "retained_private_generations": True}
        with transaction_lock(self.state_root):
            before = self._owned_target()
            if before is not None:
                self.target.rmdir() if os.name == "nt" else self.target.unlink()
            return {"registered": False, "dry_run": False, "changed": before is not None,
                    "discovery_path": str(self.target), "retained_private_generations": True}

    def refresh_registration(self) -> dict[str, Any]:
        """Refresh an existing owned registration; installation never opts in."""
        status = self.managed_status()
        if not status["registered"]:
            return status
        try:
            return {**self.register(), "managed": True}
        except (AppError, OSError, TransactionError) as exc:
            return {**self.managed_status(), "needs_action": [str(exc)]}


class AppSessions:
    """Record returned context, separately from native launch pins and host proof."""

    def __init__(self, repo: Path, environ: dict[str, str] | None = None, host: str = "codex"):
        if host not in APP_HOSTS:
            raise AppError(f"unsupported app host: {host}")
        self.repo = Path(repo).absolute()
        self.host = host
        self.env, self.home, self.state_root, self.user_root = _roots(environ)

    @property
    def desktop(self) -> bool:
        return self.host == "claude-desktop"

    def _session(self, session: str | None, *, mint: bool = False) -> str:
        if self.desktop:
            if session is None and mint:
                return "desktop-" + secrets.token_hex(16)
            if not isinstance(session, str) or not DESKTOP_SESSION_ID.fullmatch(session):
                raise AppError("Desktop session requires the session_id that preview or use returned in this conversation")
            return session
        value = session if session is not None else self.env.get("CODEX_THREAD_ID")
        if not isinstance(value, str) or not SESSION_ID.fullmatch(value):
            raise AppError("app session requires CODEX_THREAD_ID or --session with a valid task id")
        return value

    def _cwd(self, cwd: Path | None) -> Path:
        if not self.desktop:
            return Path(cwd or Path.cwd()).absolute()
        if cwd is not None:
            raise AppError("Desktop delivery has no project scope; it does not take a working directory")
        # Desktop names no project: the filesystem root lies inside no imported project scope.
        return Path(os.path.abspath(os.sep))

    def _path(self, session: str) -> Path:
        return self.state_root / "sessions/app-context" / f"{session}.json"

    def _read(self, session: str) -> dict[str, Any]:
        path = self._path(session)
        reject_symlink_ancestors(path)
        if not path.exists():
            return {"schema_version": SCHEMA_VERSION, "host": self.host, "session_id": session,
                    "enabled": False, "deliveries": []}
        record = _read_json(path)
        if (record.get("schema_version") != SCHEMA_VERSION or record.get("host") != self.host
                or record.get("session_id") != session or not isinstance(record.get("enabled"), bool)
                or not isinstance(record.get("deliveries"), list)):
            raise AppError(f"invalid app session receipt: {path}")
        for delivery in record["deliveries"]:
            if (not isinstance(delivery, dict) or delivery.get("delivery") != "returned-as-context"
                    or not isinstance(delivery.get("content_ref"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", delivery["content_ref"])
                    or ("end_marker" in delivery and not (isinstance(delivery["end_marker"], str)
                                                          and END_MARKER.fullmatch(delivery["end_marker"])))
                    or ("confirmed_at" in delivery and not isinstance(delivery["confirmed_at"], str))):
                raise AppError(f"invalid app session delivery: {path}")
        return record

    @staticmethod
    def _view(record: dict[str, Any]) -> dict[str, Any]:
        delivered = bool(record["deliveries"])
        view = {**record, "ever_delivered": delivered,
                "active_content_ref": record["deliveries"][-1]["content_ref"] if delivered and record["enabled"] else None,
                "native_activation": False, "host_loading": "unverified",
                "context_retracted": False,
                "clean_exclusion_requires_new_session": delivered and not record["enabled"]}
        if record["host"] == "claude-desktop":
            # A marker reported back proves the end was read, never inline delivery.
            view["latest_end_confirmed"] = bool(delivered and record["deliveries"][-1].get("confirmed_at"))
            view["project_scope"] = "none"
        return view

    def status(self, session: str | None = None, *, end_marker_seen: str | None = None) -> dict[str, Any]:
        session = self._session(session)
        if end_marker_seen is None:
            return self._view(self._read(session))
        reject_symlink_ancestors(self.state_root)
        with transaction_lock(self.state_root):
            record = self._read(session)
            latest = record["deliveries"][-1] if record["deliveries"] else None
            if latest is None or latest.get("end_marker") != end_marker_seen.strip():
                raise AppError("that end marker is not the latest delivery's in this session; read the delivered text to its last line")
            latest.setdefault("confirmed_at", datetime.now(timezone.utc).isoformat())
            _write_json(self._path(session), record)
            return {**self._view(record), "message": "The end of the latest delivery was read. This does not show whether the host kept it inline or saved it to a file."}

    def off(self, session: str | None = None) -> dict[str, Any]:
        session = self._session(session)
        reject_symlink_ancestors(self.state_root)
        with transaction_lock(self.state_root):
            record = self._read(session)
            record["enabled"] = False
            _write_json(self._path(session), record)
            result = self._view(record)
            result["message"] = (
                "Instructions delivery is off. Previously returned text remains in conversation context; "
                "start a new session for clean exclusion."
                if record["deliveries"] else "Instructions delivery is off; this bridge has returned no instructions text to this session."
            )
            return result

    def _snapshot(self, *, selection: list[str] | None, selection_mode: str | None,
                  cwd: Path | None, dry_run: bool) -> dict[str, Any]:
        reject_symlink_ancestors(self.state_root)
        guard_pending(self.state_root)
        release = confirmed_release(self.state_root)
        store = InstructionsStore(release, self.state_root, self.user_root)
        if selection is not None and selection_mode is None:
            selection_mode = "selected"
        return store.snapshot(host=APP_HOSTS[self.host], selection=selection, selection_mode=selection_mode,
                              cwd=self._cwd(cwd), dry_run=dry_run, native=False)

    def _runtime_commands(self) -> dict[str, Any]:
        release = confirmed_release(self.state_root)
        bridge = AppBridge(self.repo, self.env)
        result = {"package_root": str(release),
                  "learn_argv": cli_argv(release, "learn"),
                  "environment": {"AGENT_BIOS_PACKAGE_ROOT": str(release),
                                  "AGENT_BIOS_STATE_DIR": str(self.state_root),
                                  "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.user_root),
                                  "AGENT_BIOS_CORPUS_DIR": str(self.user_root),
                                  "AGENT_BIOS_PRIVATE_CORPUS": "1",
                                  "AGENT_BIOS_PRIVATE_INSTRUCTIONS": "1", "AGENT_BIOS_LEGACY_INSTALL": "0"}}
        result["environment"].update(runtime_environment())
        registered = bridge.managed_status().get("registered")
        if "AGENT_LAUNCH_VENV" in self.env or registered:
            config = bridge._config()
            if "launch_venv" in config:
                result["environment"]["AGENT_LAUNCH_VENV"] = config["launch_venv"]
        if registered:
            result["bridge_learn_argv"] = python_argv(bridge.target / "scripts/bridge.py", "learn")
        return result

    def _desktop_size(self, text: str) -> dict[str, Any]:
        size = len(text.encode("utf-8"))
        return {"instruction_bytes": size, "project_scope": "none",
                "host_may_save_to_file": size > DESKTOP_INLINE_FLOOR}

    def preview(self, session: str | None = None, *, selection: list[str] | None = None,
                selection_mode: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
        session = self._session(session, mint=True)
        if selection_mode == "none":
            return {"session_id": session, "selection_mode": "none", "content_ref": None,
                    "instruction_characters": 0, "delivery": "preview-only", "native_activation": False}
        snapshot = self._snapshot(selection=selection, selection_mode=selection_mode, cwd=cwd, dry_run=True)
        result = {"session_id": session, "content_ref": snapshot["content_ref"], "revision": snapshot["revision"],
                  "instruction_characters": len(snapshot["instruction_text"]),
                  "unavailable": snapshot.get("unavailable", []), "selection": selection,
                  "selection_mode": snapshot.get("selection_mode", selection_mode),
                  "delivery": "preview-only", "native_activation": False}
        if self.desktop:
            result.update(self._desktop_size(snapshot["instruction_text"]))
        return result

    def use(self, session: str | None = None, *, selection: list[str] | None = None,
            selection_mode: str | None = None, cwd: Path | None = None,
            expected_content_ref: str | None = None) -> dict[str, Any]:
        session = self._session(session, mint=True)
        if selection_mode == "none":
            return self.off(session)
        reject_symlink_ancestors(self.state_root)
        with transaction_lock(self.state_root):
            record = self._read(session)
            snapshot = self._snapshot(selection=selection, selection_mode=selection_mode, cwd=cwd, dry_run=False)
            if expected_content_ref is not None and snapshot["content_ref"] != expected_content_ref:
                raise AppError("instructions preview changed; preview again before using this session selection")
            if not snapshot["instruction_text"].strip():
                return self.off(session)
            latest = record["deliveries"][-1] if record["deliveries"] else None
            # Desktop retries a failing call without telling the model, and a retry exists
            # exactly when the first result may not have arrived: return the same text and
            # receipt again rather than recording a second delivery.
            repeat = (self.desktop and record["enabled"] and latest is not None
                      and latest["content_ref"] == snapshot["content_ref"])
            runtime = None if self.desktop else self._runtime_commands()
            if not repeat:
                delivery = {"at": datetime.now(timezone.utc).isoformat(), "content_ref": snapshot["content_ref"],
                            "snapshot_path": snapshot["path"], "revision": snapshot["revision"],
                            "cwd": str(self._cwd(cwd)), "delivery": "returned-as-context",
                            "instruction_sha256": hashlib.sha256(snapshot["instruction_text"].encode("utf-8")).hexdigest()}
                if self.desktop:
                    delivery["end_marker"] = "agent-bios end " + secrets.token_hex(6)
                record["deliveries"].append(delivery)
                record["enabled"] = True
                _write_json(self._path(session), record)
                latest = delivery
            result = {**self._view(record), "delivery": "returned-as-context",
                      "content_ref": snapshot["content_ref"], "instruction_text": snapshot["instruction_text"],
                      "unavailable": snapshot.get("unavailable", []),
                      "message": "Returned the selected immutable instructions as task context. This receipt is not proof of model reading or native startup activation."}
            if self.desktop:
                result.update(self._desktop_size(snapshot["instruction_text"]))
                result.update({"repeat": repeat, "end_marker": latest["end_marker"]})
            else:
                result["runtime"] = runtime
            return result


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    """Byte-stable archive: fixed order, times and modes, so equal members give equal files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, members[name])
    return buffer.getvalue()


class DesktopBundle:
    """Write one content-addressed Claude Desktop bundle; installing it is the user's step.

    Desktop resolves a bare `python3` through the user's login-shell PATH, which on
    stock macOS reaches 3.9, so the manifest names the interpreter running agent-bios.
    Nothing here writes into Desktop's own directories.
    """

    def __init__(self, repo: Path, environ: dict[str, str] | None = None):
        self.repo = Path(repo).absolute()
        self.env, self.home, self.state_root, self.user_root = _roots(environ)
        self.bundles = self.state_root / "runtime/desktop-bundles"

    def _interpreter(self, binding: dict[str, str]) -> str:
        if binding:
            return binding["AGENT_BIOS_PYTHON_EXECUTABLE"]
        if sys.version_info < (3, 11):
            raise AppError(f"the Desktop bundle needs Python 3.11 or newer; this is {sys.version.split()[0]} at {sys.executable}")
        if not sys.executable or not Path(sys.executable).is_absolute():
            raise AppError("cannot name an absolute Python interpreter for the Desktop bundle")
        return sys.executable

    @staticmethod
    def _tools(server: Path) -> list[dict[str, str]]:
        spec = importlib.util.spec_from_file_location("agent_bios_desktop_server", server)
        if spec is None or spec.loader is None:
            raise AppError(f"cannot read the Desktop server tools: {server}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return [{"name": tool["name"], "description": tool["description"]} for tool in module.TOOLS]

    def _members(self) -> tuple[dict[str, bytes], str]:
        reject_symlink_ancestors(self.state_root)
        guard_pending(self.state_root)
        release = confirmed_release(self.state_root)
        binding = runtime_environment(self.env)
        interpreter = self._interpreter(binding)
        sources = {"server/server.py": release / "compose/app_desktop/server.py",
                   "server/instructions_transaction.py": release / "compose/instructions_transaction.py",
                   "server/host_platform.py": release / "compose/host_platform.py"}
        members: dict[str, bytes] = {}
        for name, source in sources.items():
            reject_symlink_ancestors(source)
            if not source.is_file():
                raise AppError(f"installed release has no Desktop bundle member: {source}")
            members[name] = source.read_bytes()
        config: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "home": str(self.home),
                                  "state_root": str(self.state_root), "user_root": str(self.user_root)}
        if binding:
            config["python_binding"] = binding
        members["server/desktop.json"] = _json_bytes(config)
        version = _read_json(release / "package.json").get("version")
        if not isinstance(version, str):
            raise AppError("installed release has no package version")
        manifest = {
            "manifest_version": "0.3", "name": "agent-bios", "display_name": "agent-bios", "version": version,
            "description": "Pull your selected agent-bios work environment into a conversation when you ask for it.",
            "author": {"name": "agent-bios"},
            "server": {"type": "python", "entry_point": "server/server.py",
                       "mcp_config": {"command": interpreter, "args": ["-I", "${__dirname}/server/server.py"]}},
            "tools": self._tools(release / "compose/app_desktop/server.py"),
            "compatibility": {"platforms": ["darwin"]},
        }
        members["manifest.json"] = _json_bytes(manifest)
        if set(members) != set(DESKTOP_BUNDLE_MEMBERS):
            raise AppError("Desktop bundle member inventory changed")
        return members, interpreter

    def build(self, dry_run: bool = False) -> dict[str, Any]:
        members, interpreter = self._members()
        path = self.bundles / _tree_digest(members) / "agent-bios.mcpb"
        result = {"path": str(path), "dry_run": dry_run, "interpreter": interpreter,
                  "desktop_installation": "unverified",
                  "next_step": "Open this file with Claude Desktop and confirm its installation dialog; "
                               "agent-bios does not write into Desktop."}
        reject_symlink_ancestors(path)
        if dry_run:
            return {**result, "changed": not path.exists()}
        with transaction_lock(self.state_root):
            if path.exists():
                with zipfile.ZipFile(path) as archive:
                    if {name: archive.read(name) for name in archive.namelist()} != members:
                        raise AppError(f"Desktop bundle collision: {path}")
                return {**result, "changed": False}
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix=".agent-bios-", suffix=".mcpb", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(_zip_bytes(members))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.lexists(temporary):
                    os.unlink(temporary)
            return {**result, "changed": True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-bios app", description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--user-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("register", "unregister", "status"):
        command = commands.add_parser(name)
        if name != "status":
            command.add_argument("--dry-run", action="store_true")
    desktop = commands.add_parser("desktop", help="write the Claude Desktop bundle; installing it stays a Desktop step")
    desktop.add_argument("--dry-run", action="store_true")
    session = commands.add_parser("session", help="explicitly preview, use or stop instructions delivery in one app task")
    operations = session.add_subparsers(dest="operation", required=True)
    for name in ("preview", "use", "off", "status"):
        command = operations.add_parser(name)
        command.add_argument("--session", help="defaults to CODEX_THREAD_ID; Desktop preview and use mint one")
        command.add_argument("--host", choices=sorted(APP_HOSTS), default="codex")
        if name == "status":
            command.add_argument("--end-marker-seen", help="Desktop: the delivery's last line, as the model read it")
        if name in {"preview", "use"}:
            selection = command.add_mutually_exclusive_group()
            selection.add_argument("--domains", help="comma-separated qualified instructions selection")
            selection.add_argument("--no-instructions", "--no-corpus", action="store_true")
            command.add_argument("--cwd", type=Path)
            if name == "use":
                command.add_argument("--expected-content-ref", help="require the exact previously previewed snapshot")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in raw
    args = build_parser().parse_args([token for token in raw if token != "--json"])
    env = dict(os.environ)
    if args.state_dir is not None:
        env["AGENT_BIOS_STATE_DIR"] = str(args.state_dir)
    if args.user_dir is not None:
        env["AGENT_BIOS_INSTRUCTIONS_DIR"] = str(args.user_dir)
    try:
        if args.command == "session":
            manager = AppSessions(args.repo, env, host=args.host)
            options = {}
            if args.operation == "status" and args.end_marker_seen is not None:
                options["end_marker_seen"] = args.end_marker_seen
            if args.operation in {"preview", "use"}:
                selected = None
                if args.domains is not None:
                    selected = [value.strip() for value in args.domains.split(",") if value.strip()]
                    if not selected:
                        raise AppError("--domains requires a nonempty instructions selection; use --no-instructions to keep instructions off")
                options = {"selection": selected,
                           "selection_mode": "none" if args.no_instructions else "selected" if selected is not None else None,
                           "cwd": args.cwd}
                if args.operation == "use":
                    options["expected_content_ref"] = args.expected_content_ref
            result = getattr(manager, args.operation)(session=args.session, **options)
        elif args.command == "desktop":
            result = DesktopBundle(args.repo, env).build(dry_run=args.dry_run)
        else:
            manager = AppBridge(args.repo, env)
            options = {} if args.command == "status" else {"dry_run": args.dry_run}
            result = getattr(manager, args.command)(**options)
        if not as_json and isinstance(result.get("instruction_text"), str):
            metadata = {key: value for key, value in result.items() if key != "instruction_text"}
            print(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
            print(result["instruction_text"], end="")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (AppError, InstructionsStoreError, TransactionError, OSError) as exc:
        print(f"agent-bios app: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
