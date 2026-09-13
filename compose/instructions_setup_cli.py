"""JSON setup adapter with read-only reviews and durable, non-replaying receipts."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

if __name__ == "__main__":
    sys.dont_write_bytecode = True

try:
    from instructions_install import InstructionsInstaller
    from instructions_setup import SetupController, SetupError, format_setup_result, review_summary
    from instructions_setup_i18n import LANGUAGES, choice_label, dependency_display, detect_language, translate
    from instructions_transaction import environment_value, confirmed_release, reject_symlink_ancestors, transaction_lock, try_transaction_lock
except ImportError:
    from .instructions_install import InstructionsInstaller
    from .instructions_setup import SetupController, SetupError, format_setup_result, review_summary
    from .instructions_setup_i18n import LANGUAGES, choice_label, dependency_display, detect_language, translate
    from .instructions_transaction import environment_value, confirmed_release, reject_symlink_ancestors, transaction_lock, try_transaction_lock


SCHEMA_VERSION = 1
IDENTIFIER = re.compile(r"[0-9a-f]{64}\Z")
LANGUAGE_IDS = {identifier for _label, identifier in LANGUAGES}
INCIDENTAL_ENV = {
    **dict.fromkeys(("_", "SHLVL"), "shell command bookkeeping does not select setup effects"),
    **dict.fromkeys(("PWD", "OLDPWD"), "the actual working directory is bound separately in the review context"),
    **dict.fromkeys(("TERM", "COLORTERM", "TERM_PROGRAM", "TERM_PROGRAM_VERSION", "TERM_SESSION_ID", "SHELL_SESSION_ID",
                     "COLUMNS", "LINES", "NO_COLOR", "FORCE_COLOR"),
                    "terminal presentation and terminal-session identity are not installation authority"),
    **dict.fromkeys(("LC_ALL", "LC_MESSAGES", "LC_CTYPE", "LC_NUMERIC", "LC_TIME", "LC_COLLATE", "LC_MONETARY", "LANG", "LANGUAGE"),
                    "display locale may change between calls; the chosen review language is bound explicitly"),
    **dict.fromkeys(("TMPDIR", "TMP", "TEMP"),
                    "scratch allocation may change between calls; package and private destinations are bound separately"),
    **dict.fromkeys(("PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"),
                    "Python cache and output policy do not select installation targets or recipes"),
    **dict.fromkeys(("CODEX_THREAD_ID", "CODEX_TASK_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"),
                    "setup does not activate a task and may continue from another task on the same machine and private roots"),
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identity() -> dict[str, Any]:
    hardware = ""
    method = "host-filesystem"
    if sys.platform.startswith("linux"):
        for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
            try:
                candidate = path.read_text(encoding="ascii").strip()
            except (OSError, UnicodeError):
                continue
            if re.fullmatch(r"[a-fA-F0-9]{32}", candidate):
                hardware, method = candidate, "machine-id"
                break
    elif sys.platform == "darwin":
        try:
            result = subprocess.run(["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([A-Fa-f0-9-]+)"', result.stdout)
            if result.returncode == 0 and match:
                hardware, method = match[1], "platform-uuid"
        except (OSError, subprocess.SubprocessError):
            pass
    host = socket.gethostname()
    if not hardware:
        root = Path("/").stat()
        hardware = f"{host}:{root.st_dev}:{root.st_ino}"
    return {"machine_id": hashlib.sha256(hardware.encode()).hexdigest(), "identity_method": method,
            "hostname": host, "platform": platform.system(), "architecture": platform.machine(),
            "uid": os.getuid() if hasattr(os, "getuid") else None}


def _process_identity(pid: int) -> str | None:
    if sys.platform.startswith("linux"):
        try:
            fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
            return fields[19]
        except (OSError, IndexError):
            return None
    try:
        result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart="], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=3,
                                env={**os.environ, "LC_ALL": "C", "TZ": "UTC"})
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    reject_symlink_ancestors(path)
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise SetupError(f"missing, unsafe, or oversized setup JSON: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"cannot read setup JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SetupError("setup JSON must be an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    reject_symlink_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, raw = tempfile.mkstemp(prefix=".setup-receipt-", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(_canonical(value) + b"\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _review_identity(review: dict[str, Any]) -> str:
    return _digest({key: value for key, value in review.items() if key != "review_id"})


def _file_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SetupError(f"reviewed dependency executable is unavailable: {path}")
    digest = hashlib.sha256()
    with resolved.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(resolved), "sha256": digest.hexdigest(), "size_bytes": resolved.stat().st_size}


class SetupService:
    """Bind shared-engine reviews to a machine, then record every effect boundary."""

    def __init__(self, installer: Any, *, controller_factory: Callable | None = None,
                 identity: Callable[[], dict[str, Any]] = _identity,
                 progress_hook: Callable[[dict[str, Any]], None] | None = None):
        self.installer = installer
        self.controller_factory = controller_factory or (lambda: SetupController(installer))
        self.identity = identity
        self.progress_hook = progress_hook

    def context(self) -> dict[str, Any]:
        env = self.installer.env
        home = Path(env.get("HOME", str(Path.home()))).expanduser().resolve()
        state = Path(getattr(self.installer, "state_root", env.get("AGENT_BIOS_STATE_DIR", home / ".local/share/agent-bios"))).expanduser().resolve()
        user = Path(getattr(self.installer, "user_root", environment_value(env, "AGENT_BIOS_INSTRUCTIONS_DIR", "AGENT_BIOS_CORPUS_DIR", home / ".config/agent-bios/corpus"))).expanduser().resolve()
        return {**self.identity(), "home": str(home), "state_dir": str(state), "user_dir": str(user),
                "codex_dir": str(Path(env.get("CODEX_HOME", home / ".codex")).expanduser().resolve()),
                "claude_dir": str(Path(env.get("CLAUDE_CONFIG_DIR", home / ".claude")).expanduser().resolve()),
                "package_root": str(Path(self.installer.repo).resolve()), "cwd": str(Path.cwd().resolve()),
                "python": {"executable": str(Path(sys.executable).resolve()), "version": platform.python_version()},
                "environment_digest": _digest({key: value for key, value in env.items() if key not in INCIDENTAL_ENV})}

    def _language(self, language: str | None) -> str:
        value = language or detect_language(self.installer.env)
        if value not in LANGUAGE_IDS:
            raise SetupError("language must be en, ko, or ja")
        return value

    def _assert_owner(self, review: dict[str, Any]) -> None:
        current = self.context()
        if any(review["context"].get(key) != current.get(key) for key in ("machine_id", "uid", "home", "state_dir", "user_dir")):
            raise SetupError("review receipt belongs to another machine or private root context")

    def start(self, language: str | None = None) -> dict[str, Any]:
        package = Path(self.installer.repo).resolve()
        cli = ["/bin/bash", str(package / "install.sh")]
        return {"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-start",
                "languages": [{"label": label, "id": identifier} for label, identifier in LANGUAGES],
                "suggested_language": detect_language(self.installer.env), "language": self._language(language),
                "context": self.context(), "guide_path": str(package / "compose/setup/START.md"),
                "cli_argv": cli, "setup_argv": [*cli, "setup"]}

    def inspect(self, language: str | None = None) -> dict[str, Any]:
        language = self._language(language)
        controller = self.controller_factory()
        retained = getattr(controller, "retained_instructions", [])
        return {"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-inspection", "context": self.context(),
                "language": language, "dependencies": controller.dependencies, "choices": controller.choices,
                "retained_corpus": retained,
                "default_plan": controller.default_plan(),
                "display": {"dependencies": [dependency_display(language, row) for row in controller.dependencies],
                            "retained_corpus": [{**row, "label": translate(language, row["label"])} for row in retained],
                            "choices": [{**row, "label": choice_label(language, row)} for row in controller.choices]}}

    def discover(self, roots: list[str]) -> dict[str, Any]:
        if not isinstance(roots, list) or not all(isinstance(root, str) and Path(root).is_absolute() and Path(root).is_dir() for root in roots):
            raise SetupError("project roots must be existing absolute directories")
        found = self.installer.setup_discover(roots)
        return {"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-discovery", "context": self.context(),
                "sources": found["sources"], "omitted": found.get("omitted", [])}

    def _actions(self, preview: dict[str, Any]) -> list[dict[str, Any]]:
        identities = []
        for action in preview["plan"]["dependency_actions"]:
            command = action["argv"][0]
            path = shutil.which(command, path=self.installer.env.get("PATH", os.defpath))
            if not path:
                raise SetupError(f"reviewed dependency executable is unavailable: {command}")
            identities.append({"id": action["id"], **_file_identity(Path(path))})
        return identities

    def plan(self, value: dict[str, Any], language: str | None = None, *, continuation: dict[str, Any] | None = None) -> dict[str, Any]:
        language = self._language(language)
        controller = self.controller_factory()
        if not isinstance(value, dict) or set(value) != controller.FIELDS:
            raise SetupError("plan input must contain exactly the six setup choice fields; derived commands are not input")
        preview = controller.preview(value)
        review = {"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-review", "context": self.context(),
                  "language": language, "preview": preview, "action_inputs": self._actions(preview),
                  "summary": review_summary(preview["plan"], controller.dependencies, controller.choices, language)}
        if continuation is not None:
            review["continuation"] = continuation
        review["review_id"] = _review_identity(review)
        return review

    def _receipt_path(self, identifier: str) -> Path:
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise SetupError("review id must be an engine-issued 64-character identifier")
        return Path(self.context()["state_dir"]) / "setup/receipts" / f"{identifier}.json"

    def _receipt(self, identifier: str) -> dict[str, Any] | None:
        path = self._receipt_path(identifier)
        reject_symlink_ancestors(path)
        if not path.exists():
            return None
        receipt = _read_json(path)
        fingerprint = _digest({key: value for key, value in receipt.items() if key != "receipt_revision"})
        if receipt.get("schema_version") != SCHEMA_VERSION or receipt.get("review_id") != identifier \
                or receipt.get("receipt_revision") != fingerprint or not isinstance(receipt.get("operations"), dict) \
                or receipt.get("state") not in {"running", "complete", "partial", "unknown"}:
            raise SetupError("setup receipt integrity check failed")
        self._validate_envelope(receipt.get("review"), identifier)
        return receipt

    def _save(self, receipt: dict[str, Any]) -> None:
        receipt["updated_at"] = time.time()
        receipt["receipt_revision"] = _digest({key: value for key, value in receipt.items() if key != "receipt_revision"})
        _write_json(self._receipt_path(receipt["review_id"]), receipt)

    @staticmethod
    def _validate_envelope(review: Any, expected: str) -> None:
        fields = {"schema_version", "kind", "context", "language", "preview", "action_inputs", "summary", "review_id"}
        if not isinstance(review, dict) or set(review) not in (fields, fields | {"continuation"}) \
                or review.get("schema_version") != SCHEMA_VERSION or review.get("kind") != "agent-bios-setup-review":
            raise SetupError("apply requires the entire engine-issued review envelope")
        if not isinstance(review["context"], dict) or not isinstance(review["preview"], dict) \
                or not isinstance(review["language"], str) or review["language"] not in LANGUAGE_IDS \
                or not isinstance(review["summary"], str) or not isinstance(review["action_inputs"], list):
            raise SetupError("review envelope fields have invalid types")
        if not isinstance(expected, str) or not IDENTIFIER.fullmatch(expected) or review.get("review_id") != expected \
                or _review_identity(review) != expected:
            raise SetupError("review identity does not match the exact reviewed envelope")

    def _current_review(self, review: dict[str, Any]) -> dict[str, Any]:
        if "continuation" in review:
            continuation = review["continuation"]
            if not isinstance(continuation, dict) or set(continuation) != {"review_id", "receipt_revision", "reuse_installation"}:
                raise SetupError("invalid setup continuation")
            resumed = self.resume(continuation["review_id"], review["language"])
            if resumed.get("review") is None:
                raise SetupError("setup continuation requires inspection of prior effects")
            return resumed["review"]
        value = review.get("preview", {}).get("plan", {})
        plan = {key: value[key] for key in SetupController.FIELDS if key in value}
        return self.plan(plan, review["language"])

    def handoff(self) -> dict[str, Any]:
        context = self.context()
        result = {"verification": "deferred", "runtime_verified": None, "package_verified": None, "package_root": None, "release_digest": None, "cli_argv": None, "setup_argv": None,
                  "guide_path": None, "helper_registered": None, "helper_verified": None, "helper_argv": None,
                  "helper_usable": None,
                  "native_discovery": "unverified", "task_activation": {"performed": False, "existing_tasks": "unchanged", "default": "not_requested"},
                  "environment": {"HOME": context["home"], "AGENT_BIOS_STATE_DIR": context["state_dir"],
                                  "AGENT_BIOS_INSTRUCTIONS_DIR": context["user_dir"], "CODEX_HOME": context["codex_dir"],
                                  "AGENT_BIOS_CORPUS_DIR": context["user_dir"],
                                  "CLAUDE_CONFIG_DIR": context["claude_dir"]}, "needs_action": []}
        try:
            with try_transaction_lock(Path(context["state_dir"])) as acquired:
                if not acquired:
                    result["needs_action"].append("private state verification is deferred: another operation holds the lock or synchronization is unavailable; retry setup status")
                    return result
                result.update(verification="checked", runtime_verified=False, package_verified=False,
                              helper_registered=False, helper_verified=False, helper_usable=False)
                return self._verified_handoff(context, result)
        except (OSError, RuntimeError, ValueError) as exc:
            result["needs_action"].append(str(exc))
            return result

    def _verified_handoff(self, context: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        record = Path(context["state_dir"]) / "runtime/private-install.json"
        pending = False
        if record.is_file():
            try:
                reject_symlink_ancestors(record)
                release = confirmed_release(Path(context["state_dir"]))
                result.update(package_verified=True, package_root=str(release), release_digest=release.name,
                              cli_argv=["/bin/bash", str(release / "install.sh")],
                              setup_argv=["/bin/bash", str(release / "install.sh"), "setup"], guide_path=str(release / "compose/setup/START.md"))
                result["environment"].update(AGENT_BIOS_PACKAGE_ROOT=str(release), AGENT_BIOS_PRIVATE_INSTRUCTIONS="1", AGENT_BIOS_PRIVATE_CORPUS="1", AGENT_BIOS_LEGACY_INSTALL="0")
            except (OSError, RuntimeError, ValueError) as exc:
                result["needs_action"].append(str(exc))
            try:
                verification = self.installer.verify()
                result["runtime_verified"] = verification.get("stored") is True
                if not result["runtime_verified"]:
                    result["needs_action"].append("private runtime verification did not confirm installation")
            except (OSError, RuntimeError, ValueError) as exc:
                result["needs_action"].append(str(exc))
            try:
                pending = bool(self.installer.status().get("transactions"))
                if pending:
                    result["needs_action"].append("private installation has a pending transaction")
            except (OSError, RuntimeError, ValueError) as exc:
                pending = True
                result["needs_action"].append(str(exc))
        try:
            manager = self.installer._app_manager()
            bridge = manager.managed_status()
            result["helper_registered"] = bool(bridge.get("registered"))
            result["needs_action"].extend(bridge.get("needs_action", []))
            if bridge.get("registered") and not bridge.get("needs_action"):
                helper = manager.target / "scripts/bridge.py"
                result.update(helper_verified=True, helper_argv=[sys.executable, str(helper)])
            if "AGENT_LAUNCH_VENV" in self.installer.env:
                result["environment"]["AGENT_LAUNCH_VENV"] = self.installer.env["AGENT_LAUNCH_VENV"]
        except (OSError, RuntimeError, ValueError) as exc:
            result["needs_action"].append(str(exc))
        result["helper_usable"] = result["helper_verified"] and result["package_verified"] and not pending
        return result

    def status(self, identifier: str, language: str | None = None, *, replayed: bool = False) -> dict[str, Any]:
        receipt = self._receipt(identifier)
        result = receipt.get("result") or {} if receipt else {}
        language = self._language(language or (receipt or {}).get("review", {}).get("language"))
        state = receipt["state"] if receipt else "missing"
        if state == "running":
            owner = receipt.get("owner", {})
            token = _process_identity(owner.get("pid", -1)) if isinstance(owner.get("pid"), int) else None
            same_machine = receipt["review"]["context"].get("machine_id") == self.context()["machine_id"]
            if not same_machine or token is None or token != owner.get("process_identity"):
                state = "unknown"
        return {"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-status", "review_id": identifier,
                "state": state, "receipt_path": str(self._receipt_path(identifier)), "receipt": receipt,
                "result": result, "summary": format_setup_result(result, language, interface="conversation"), "handoff": self.handoff(),
                "replayed": replayed, "context": self.context(), "language": language}

    def resume(self, identifier: str, language: str | None = None) -> dict[str, Any]:
        response = self.status(identifier, language)
        response.update(remaining_plan=None, review=None, needs_action=[])
        receipt = response["receipt"]
        if receipt is None:
            response["needs_action"] = ["setup receipt was not found"]
            return response
        self._assert_owner(receipt["review"])
        chain = []
        while receipt.get("continued_by"):
            if receipt["review_id"] in chain or len(chain) >= 32:
                raise SetupError("setup continuation chain is invalid")
            chain.append(receipt["review_id"])
            child = self._receipt(receipt["continued_by"])
            if child is None or child["review"].get("continuation", {}).get("review_id") != receipt["review_id"]:
                raise SetupError("setup continuation receipt is missing or inconsistent")
            self._assert_owner(child["review"])
            receipt = child
            response = self.status(receipt["review_id"], language)
            response.update(remaining_plan=None, review=None, needs_action=[], resumed_from=identifier)
        if receipt["state"] == "complete":
            return response
        if receipt["state"] == "running":
            response["needs_action"] = ["setup is running or its interruption is unconfirmed; inspect its recorded progress before retrying"]
            return response
        unsafe = [name for name, operation in receipt.get("operations", {}).items()
                  if operation.get("state") in {"running", "failed", "unknown"}]
        if unsafe or receipt["state"] == "unknown":
            response["needs_action"] = ["inspect effects before retrying: " + ", ".join(unsafe or ["unknown operation"])]
            response["inspection"] = self.inspect(response["language"])
            return response
        original = receipt["review"]["preview"]["plan"]
        plan = {key: original[key] for key in SetupController.FIELDS}
        completed = {name for name, operation in receipt.get("operations", {}).items() if operation.get("state") == "completed"}
        controller = self.controller_factory()
        inventory = {row["id"]: row for row in controller.dependencies}
        remaining = []
        for name in plan["dependencies"]:
            row = inventory.get(name)
            if row is None:
                response["needs_action"].append(f"requested dependency is absent from the current inventory: {name}")
            elif "dependency:" + name in completed:
                if row.get("status") != "available":
                    response["needs_action"].append(f"completed dependency is not currently available: {name}")
            elif row.get("status") == "available":
                continue
            elif not row.get("install_argv"):
                response["needs_action"].append(f"requested dependency is still missing and has no current installation recipe: {name}")
            else:
                remaining.append(name)
        response["inspection"] = {"dependencies": controller.dependencies, "choices": controller.choices}
        if response["needs_action"]:
            return response
        plan["dependencies"] = remaining
        reuse = "install" in completed
        if reuse:
            if not response["handoff"]["runtime_verified"] or response["handoff"]["needs_action"]:
                response["needs_action"] = ["verify the completed private installation before continuing"]
                return response
            plan["selection_mode"], plan["targets"] = None, None
        if "extras" in completed:
            plan["app_bridge"], plan["import_paths"], plan["project_roots"] = False, [], []
        continuation = {"review_id": receipt["review_id"], "receipt_revision": receipt["receipt_revision"], "reuse_installation": reuse}
        response["remaining_plan"] = plan
        candidate = self.plan(plan, response["language"], continuation=continuation)
        if reuse:
            completed_install = receipt["operations"]["install"]["event"].get("installation", {})
            completed_digest = completed_install.get("record", {}).get("release_digest") or completed_install.get("release_digest")
            source_digest = candidate["preview"]["installation"].get("release_digest")
            if source_digest != response["handoff"].get("release_digest") or completed_digest != source_digest:
                response["needs_action"] = ["source or installed package changed after partial setup; create a fresh installation plan"]
                return response
        response["review"] = candidate
        return response

    def apply(self, review: dict[str, Any], expected_review_id: str, *, yes: bool = False) -> dict[str, Any]:
        if yes is not True:
            raise SetupError("apply requires explicit --yes acknowledgment of the exact reviewed plan")
        review = json.loads(json.dumps(review, ensure_ascii=False))
        self._validate_envelope(review, expected_review_id)
        existing = self._receipt(expected_review_id)
        if existing is not None:
            if existing["review"] != review:
                raise SetupError("review differs from the owned receipt")
            self._assert_owner(review)
            return self.status(expected_review_id, replayed=True)
        if self._current_review(review) != review:
            raise SetupError("review is stale or belongs to another execution context; create a fresh plan")
        state_root = Path(self.context()["state_dir"])
        with transaction_lock(state_root):
            if self._receipt(expected_review_id) is not None:
                return self.status(expected_review_id, replayed=True)
            if self._current_review(review) != review:
                raise SetupError("review changed while waiting for the setup lock; create a fresh plan")
            receipt = {"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-receipt", "review_id": expected_review_id,
                       "review": review, "state": "running", "created_at": time.time(), "operations": {}, "progress": [], "result": None,
                       "owner": {"pid": os.getpid(), "process_identity": _process_identity(os.getpid())}}
            self._save(receipt)
            if review.get("continuation"):
                parent = self._receipt(review["continuation"]["review_id"])
                if parent is None or parent["receipt_revision"] != review["continuation"]["receipt_revision"] or parent.get("continued_by"):
                    raise SetupError("setup continuation was consumed or changed before execution")
                parent["continued_by"] = expected_review_id
                self._save(parent)
            def progress(event: dict[str, Any]) -> None:
                stage, phase = event.get("stage"), event.get("phase")
                key = "dependency:" + str(event.get("dependency", event.get("id", ""))) if stage == "dependency" else stage
                if phase == "started" and stage == "dependency":
                    actual = self._actions({"plan": {"dependency_actions": [action for action in review["preview"]["plan"]["dependency_actions"] if action["id"] == event["dependency"]]}})
                    expected = [row for row in review["action_inputs"] if row["id"] == event["dependency"]]
                    if actual != expected:
                        raise SetupError("dependency executable changed after review")
                if stage in {"dependency", "install", "extras"}:
                    receipt["operations"][key] = {"state": {"started": "running", "completed": "completed", "failed": "failed", "not_started": "not_started"}.get(phase, "not_started"),
                                                  "event": event, "at": time.time()}
                receipt["progress"].append(event)
                self._save(receipt)
                if self.progress_hook:
                    self.progress_hook(event)
            try:
                controller = self.controller_factory()
                plan = {key: review["preview"]["plan"][key] for key in SetupController.FIELDS}
                result = controller.apply(plan, preview=review["preview"], progress=progress,
                                          reuse_installation=bool(review.get("continuation", {}).get("reuse_installation")))
                receipt["result"] = result
                active = any(operation["state"] == "running" for operation in receipt["operations"].values())
                receipt["state"] = "complete" if result.get("applied") else "unknown" if active else "partial"
            except BaseException as exc:
                active = any(operation["state"] == "running" for operation in receipt["operations"].values())
                receipt["state"] = "unknown" if active else "partial"
                receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
                receipt["result"] = {"applied": False, "installation_error": str(exc) or type(exc).__name__,
                                     "dependency_results": [operation["event"] for key, operation in receipt["operations"].items() if key.startswith("dependency:") and "returncode" in operation["event"]]}
            self._save(receipt)
            return self.status(expected_review_id)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SetupError(message)


def _input(source: str) -> dict[str, Any]:
    if source != "-":
        return _read_json(Path(source).expanduser())
    if sys.stdin.isatty():
        raise SetupError("--input - requires piped JSON; use a review file in a terminal")
    body = sys.stdin.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise SetupError("setup input is too large")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise SetupError("setup input must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    args = None
    presentation_language = None
    try:
        parser = _Parser(prog="agent-bios setup", add_help=False)
        parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
        parser.add_argument("--help", action="store_true")
        sub = parser.add_subparsers(dest="command")
        for name in ("start", "inspect"):
            command = sub.add_parser(name, add_help=False)
            command.add_argument("--language", choices=sorted(LANGUAGE_IDS))
        discover = sub.add_parser("discover", add_help=False)
        discover.add_argument("--project-root", action="append", default=[])
        plan = sub.add_parser("plan", add_help=False)
        plan.add_argument("--input", required=True)
        plan.add_argument("--language", choices=sorted(LANGUAGE_IDS))
        apply = sub.add_parser("apply", add_help=False)
        apply.add_argument("--input", required=True)
        apply.add_argument("--review-id", required=True)
        apply.add_argument("--yes", action="store_true")
        for name in ("status", "resume"):
            command = sub.add_parser(name, add_help=False)
            command.add_argument("--review-id", required=True)
            command.add_argument("--language", choices=sorted(LANGUAGE_IDS))
        raw = list(sys.argv[1:] if argv is None else argv)
        args = parser.parse_args([value for value in raw if value != "--json"])
        if args.help:
            result = {"schema_version": SCHEMA_VERSION, "commands": ["start", "inspect", "discover", "plan", "apply", "status", "resume"], "format": "JSON"}
        else:
            service = SetupService(InstructionsInstaller(args.repo))
            command = args.command or "start"
            with contextlib.redirect_stdout(sys.stderr):
                if command == "start": result = service.start(getattr(args, "language", None))
                elif command == "inspect": result = service.inspect(args.language)
                elif command == "discover": result = service.discover(args.project_root)
                elif command == "plan": result = service.plan(_input(args.input), args.language)
                elif command == "apply":
                    envelope = _input(args.input)
                    selected_language = envelope.get("language")
                    if isinstance(selected_language, str) and selected_language in LANGUAGE_IDS:
                        presentation_language = selected_language
                    result = service.apply(envelope, args.review_id, yes=args.yes)
                elif command == "status": result = service.status(args.review_id, args.language)
                else: result = service.resume(args.review_id, args.language)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if (args.command == "apply" and result.get("state") != "complete") else 0
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        language = presentation_language or getattr(args, "language", None) or detect_language(os.environ)
        print(json.dumps({"schema_version": SCHEMA_VERSION, "kind": "agent-bios-setup-error", "ok": False,
                          "error": {"type": type(exc).__name__, "message": str(exc)},
                          "summary": translate(language, "Setup could not finish. Details: {detail}", detail=str(exc))}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
