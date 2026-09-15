"""Owned Windows script deployment; private instructions remain installer-owned.

The caller authenticates the downloaded bundle before invoking this module. This
owner checks its contents, interpreter binding and destinations, stages immutable
versions, and publishes a data binding consumed by the signed static wrappers.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    from .host_platform import redirected
    from .instructions_transaction import transaction_lock, reject_symlink_ancestors
except ImportError:
    from host_platform import redirected
    from instructions_transaction import transaction_lock, reject_symlink_ancestors

OWNER = "agent-bios-windows-script"
SCHEMA_VERSION = 1
COMMANDS = ("agent-bios.ps1", "agent-launch.ps1")
ENTRY = "runtime_entry.py"
PRIVATE_ENVIRONMENT = ("HOME", "AGENT_BIOS_STATE_DIR", "AGENT_BIOS_INSTRUCTIONS_DIR", "CLAUDE_CONFIG_DIR", "CODEX_HOME")


class DeploymentError(RuntimeError):
    pass


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic(path: Path, data: bytes) -> None:
    reject_symlink_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".deploy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _json(path: Path) -> dict[str, Any]:
    reject_symlink_ancestors(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeploymentError(f"invalid deployment record: {path}") from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"invalid deployment record: {path}")
    return value


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _inventory(root: Path) -> dict[str, str]:
    reject_symlink_ancestors(root)
    if not root.is_dir():
        raise DeploymentError(f"required directory is absent: {root}")
    result: dict[str, str] = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(directory) / name
            if redirected(path):
                raise DeploymentError(f"redirected bundle path: {path}")
            if name in files:
                if not path.is_file():
                    raise DeploymentError(f"non-file bundle entry: {path}")
                result[path.relative_to(root).as_posix()] = _hash(path)
    return dict(sorted(result.items()))


def _check_inventory(root: Path, inventory: dict[str, str], *, exact: bool = True) -> None:
    if not isinstance(inventory, dict) or not inventory:
        raise DeploymentError(f"empty file inventory: {root}")
    for name, digest in inventory.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise DeploymentError(f"unsafe inventory path: {name}")
        path = root / relative
        reject_symlink_ancestors(path)
        if not path.is_file() or _hash(path) != digest:
            raise DeploymentError(f"owned file drifted: {path}")
    if exact and _inventory(root) != inventory:
        raise DeploymentError(f"unexpected files in owned release: {root}")


def _version(value: str) -> tuple[int, int, int, int, tuple]:
    if not isinstance(value, str):
        raise DeploymentError("application version is missing")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", value)
    if not match:
        raise DeploymentError(f"unsupported version: {value!r}")
    parts = tuple((0, int(part)) if part.isdigit() else (1, part) for part in (match[4] or "").split("."))
    return int(match[1]), int(match[2]), int(match[3]), int(match[4] is None), parts


def _same_path(left: str, right: str) -> bool:
    left, right = os.path.expandvars(left.strip('"')), os.path.expandvars(right.strip('"'))
    try:
        return os.path.samefile(left, right)
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


class WindowsIntegration:
    """HKCU PATH and per-root Start menu entries, with exact ownership receipts."""

    def __init__(self):
        if os.name != "nt":
            raise DeploymentError("Windows deployment must run on Windows")
        import winreg
        self.registry = winreg

    def _path(self) -> tuple[str, int]:
        reg = self.registry
        with reg.CreateKey(reg.HKEY_CURRENT_USER, "Environment") as key:
            try:
                value, kind = reg.QueryValueEx(key, "Path")
                if kind not in (reg.REG_SZ, reg.REG_EXPAND_SZ):
                    raise DeploymentError("user PATH has an unsupported registry type")
                return value, kind
            except FileNotFoundError:
                return "", reg.REG_EXPAND_SZ

    def _set_path(self, value: str, kind: int) -> None:
        reg = self.registry
        with reg.CreateKey(reg.HKEY_CURRENT_USER, "Environment") as key:
            reg.SetValueEx(key, "Path", 0, kind, value)
        import ctypes
        result = ctypes.c_size_t()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 2, 2000, ctypes.byref(result))

    # Static C# source, ASCII only: it is delivered on stdin and compiled by the
    # shell, so no path or user value is ever interpolated into program text.
    SHORTCUT_SOURCE = """
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
namespace AgentBiosShortcut {
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
  public class ShellLink {}
  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
  public interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cchMaxPath, IntPtr pfd, int fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cchMaxName);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cchMaxPath);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cchMaxPath);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out short pwHotkey);
    void SetHotkey(short wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cchIconPath, out int piIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, int dwReserved);
    void Resolve(IntPtr hwnd, int fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
  }
  public static class Writer {
    public static void Save(string path, string target, string arguments, string workingDirectory) {
      IShellLinkW link = (IShellLinkW)new ShellLink();
      link.SetPath(target);
      link.SetArguments(arguments);
      link.SetWorkingDirectory(workingDirectory);
      ((IPersistFile)link).Save(path, false);
    }
  }
}
"""

    def _shortcut(self, target: Path, destination: Path, command: str) -> None:
        # The executed PowerShell program is static; paths are data environment
        # values, never interpolated into its source or encoded as a workaround.
        # IShellLinkW is used directly: the WScript.Shell shortcut object cannot
        # save to paths with characters outside the system ANSI code page.
        script = ("$ErrorActionPreference='Stop'; $source=[Console]::In.ReadToEnd(); "
                  "Add-Type -TypeDefinition $source -Language CSharp; "
                  "[AgentBiosShortcut.Writer]::Save($env:AGENT_BIOS_SHORTCUT_DESTINATION, $env:AGENT_BIOS_SHORTCUT_SHELL, "
                  "('-NoProfile -File '+[char]34+$env:AGENT_BIOS_SHORTCUT_TARGET+[char]34+' '+$env:AGENT_BIOS_SHORTCUT_COMMAND), "
                  "$env:USERPROFILE)")
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        env = dict(os.environ, AGENT_BIOS_SHORTCUT_DESTINATION=str(destination),
                   AGENT_BIOS_SHORTCUT_SHELL=str(powershell), AGENT_BIOS_SHORTCUT_TARGET=str(target),
                   AGENT_BIOS_SHORTCUT_COMMAND=command)
        result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                                input=self.SHORTCUT_SOURCE, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=180)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().replace("\r\n", " ")[:600]
            raise DeploymentError(f"Start menu shortcut creation failed (exit {result.returncode}): {detail}")

    def _group(self, root: Path) -> Path:
        token = hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()[:12]
        return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs" / ("agent-bios Script " + token)

    def _validate(self, root: Path, receipt: dict[str, Any]) -> None:
        if not receipt:
            return
        if receipt.get("owner") != OWNER or receipt.get("root") != str(root) or receipt.get("schema_version") != SCHEMA_VERSION:
            raise DeploymentError("invalid platform ownership receipt")
        if receipt.get("path_entry") not in (None, str(root / "bin")):
            raise DeploymentError("invalid owned PATH entry")
        group = self._group(root)
        if receipt.get("shortcut_group") not in (None, str(group)):
            raise DeploymentError("invalid Start menu group ownership")
        for collection in (receipt.get("shortcuts", {}), receipt.get("pending_shortcuts", {})):
            if not isinstance(collection, dict):
                raise DeploymentError("invalid Start menu ownership inventory")
            for name in collection:
                path = Path(name)
                if path.parent != group or path.name not in ("agent-bios.lnk", "Instructions Studio.lnk"):
                    raise DeploymentError("invalid Start menu ownership claim")
                reject_symlink_ancestors(path)

    def apply(self, root: Path, prior: dict[str, Any]) -> dict[str, Any]:
        self._validate(root, prior)
        receipt_path = root / "platform.json"
        receipt = dict(prior)
        receipt.update(schema_version=SCHEMA_VERSION, owner=OWNER, root=str(root))
        group = self._group(root)
        reject_symlink_ancestors(group)
        owned = dict(prior.get("shortcuts", {}))
        pending = dict(prior.get("pending_shortcuts", {}))
        if group.exists() and prior.get("shortcut_group") != str(group) and not owned:
            raise DeploymentError(f"unowned Start menu directory: {group}")
        for name in ("agent-bios.lnk", "Instructions Studio.lnk"):
            destination = group / name
            reject_symlink_ancestors(destination)
            accepted = (owned.get(str(destination)), pending.get(str(destination)))
            if destination.exists() and _hash(destination) not in accepted:
                raise DeploymentError(f"modified or unowned Start menu shortcut: {destination}")
        current, kind = self._path()
        entry = str(root / "bin")
        if not any(_same_path(part, entry) for part in current.split(";") if part):
            receipt["path_entry"] = entry
            _atomic(receipt_path, _canonical(receipt))
            self._set_path(current + (";" if current and not current.endswith(";") else "") + entry, kind)
        elif not prior.get("path_entry"):
            receipt["path_entry"] = None  # A preexisting user's PATH entry is not ours.
        receipt["shortcut_group"] = str(group)
        _atomic(receipt_path, _canonical(receipt))
        group.mkdir(parents=True, exist_ok=True)
        for name, command in (("agent-bios.lnk", "install"), ("Instructions Studio.lnk", "instructions")):
            destination = group / name
            fd, temporary_name = tempfile.mkstemp(prefix=".agent-bios-", suffix=".lnk", dir=group)
            os.close(fd)
            temporary = Path(temporary_name)
            temporary.unlink()
            try:
                self._shortcut(root / "bin/agent-bios.ps1", temporary, command)
                pending[str(destination)] = _hash(temporary)
                receipt.update(shortcuts=owned, pending_shortcuts=pending)
                _atomic(receipt_path, _canonical(receipt))
                os.replace(temporary, destination)
                owned[str(destination)] = pending.pop(str(destination))
                receipt.update(shortcuts=owned, pending_shortcuts=pending)
                _atomic(receipt_path, _canonical(receipt))
            finally:
                temporary.unlink(missing_ok=True)
        return receipt

    def remove(self, root: Path, receipt: dict[str, Any]) -> list[str]:
        self._validate(root, receipt)
        retained: list[str] = []
        entry = receipt.get("path_entry")
        if entry is not None and entry != str(root / "bin"):
            raise DeploymentError("invalid owned PATH entry")
        if entry:
            current, kind = self._path()
            # Remove only the exact representation we wrote. A later user edit
            # to an equivalent/short path is not permission to rewrite it.
            self._set_path(";".join(part for part in current.split(";") if part != entry), kind)
        group = self._group(root)
        pending = receipt.get("pending_shortcuts", {})
        shortcuts = receipt.get("shortcuts", {})
        for name in set(shortcuts) | set(pending):
            path = Path(name)
            if path.parent != group or path.name not in ("agent-bios.lnk", "Instructions Studio.lnk"):
                raise DeploymentError("invalid Start menu ownership claim")
            reject_symlink_ancestors(path)
            if path.is_file() and _hash(path) in (shortcuts.get(name), pending.get(name)):
                path.unlink()
            elif path.exists():
                retained.append(str(path))
        with contextlib.suppress(OSError):
            group.rmdir()
        return retained


class Deployment:
    def __init__(self, root: Path, *, environ: dict[str, str] | None = None,
                 integration=None, installer_factory=None, probe=None):
        self.root = Path(root).expanduser().absolute()
        reject_symlink_ancestors(self.root)
        self.root = self.root.resolve()
        self.env = dict(os.environ if environ is None else environ)
        legacy = self.env.get("AGENT_BIOS_CORPUS_DIR")
        canonical = self.env.get("AGENT_BIOS_INSTRUCTIONS_DIR")
        if legacy is not None:
            if canonical is not None and not _same_path(legacy, canonical):
                raise DeploymentError("conflicting AGENT_BIOS_INSTRUCTIONS_DIR and AGENT_BIOS_CORPUS_DIR")
            self.env.setdefault("AGENT_BIOS_INSTRUCTIONS_DIR", legacy)
        if (self.root / "owner.json").exists() or (self.root / "deployment.json").exists():
            owner = _json(self.root / "owner.json")
            saved = _json(self.root / "deployment.json") if (self.root / "deployment.json").exists() else owner
            for record in (saved, owner):
                if record.get("owner") != OWNER or record.get("schema_version") != SCHEMA_VERSION or not _same_path(record.get("root", ""), str(self.root)):
                    raise DeploymentError("invalid deployment ownership")
            values = saved.get("private_environment", owner.get("private_environment", {}))
            if not isinstance(values, dict) or set(values) - set(PRIVATE_ENVIRONMENT):
                raise DeploymentError("invalid saved private environment")
            values = dict(values)
            if "AGENT_BIOS_STATE_DIR" not in values and owner.get("state_root"):
                values["AGENT_BIOS_STATE_DIR"] = owner["state_root"]
            for name, value in values.items():
                if not isinstance(value, str) or not Path(value).is_absolute():
                    raise DeploymentError("invalid saved private environment path")
                if name in self.env and not _same_path(self.env[name], value):
                    raise DeploymentError(f"{name} differs from the saved deployment root; explicit root relocation is not supported")
                self.env.setdefault(name, value)
        home = Path(self.env.get("HOME", str(Path.home()))).expanduser()
        self.state_root = Path(self.env.get("AGENT_BIOS_STATE_DIR", str(home / ".local/share/agent-bios"))).resolve()
        if _within(self.state_root, self.root) or _within(self.root, self.state_root):
            raise DeploymentError("application root and private instructions state must be separate")
        self.integration = integration if integration is not None else WindowsIntegration()
        if installer_factory is None:
            try:
                from .instructions_install import InstructionsInstaller
            except ImportError:
                from instructions_install import InstructionsInstaller
            installer_factory = lambda package, env: InstructionsInstaller(package, environ=env)
        self.installer_factory = installer_factory
        self.probe = probe or self._probe

    @property
    def binding_path(self) -> Path:
        return self.root / "deployment.json"

    def _owned(self, *, allow_absent=False) -> dict[str, Any] | None:
        reject_symlink_ancestors(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise DeploymentError(f"deployment root is not a directory: {self.root}")
        if any(self.root.glob("unins*.exe")) or (self.root / "agent-bios.exe").exists():
            raise DeploymentError("Inno-managed installation migration is not supported; use a distinct script installation root")
        marker = self.root / "owner.json"
        if not marker.exists():
            if self.root.exists() and any(self.root.iterdir()):
                raise DeploymentError(f"unowned nonempty deployment root: {self.root}")
            if allow_absent:
                return None
            raise DeploymentError("no owned Windows script installation exists")
        owner = _json(marker)
        if owner.get("owner") != OWNER or owner.get("schema_version") != SCHEMA_VERSION or not _same_path(owner.get("root", ""), str(self.root)):
            raise DeploymentError("invalid deployment ownership marker")
        if owner.get("state_root") != str(self.state_root):
            raise DeploymentError("private instructions state differs from the saved deployment root")
        if not isinstance(owner.get("trees"), dict):
            raise DeploymentError("invalid owned tree inventory")
        for name, files in owner["trees"].items():
            path = Path(name)
            if len(path.parts) != 2 or path.parts[0] not in ("releases", "runtimes") or not re.fullmatch(r"[a-f0-9]{64}", path.name):
                raise DeploymentError("invalid owned tree claim")
            if not isinstance(files, dict) or not files:
                raise DeploymentError("invalid owned file inventory")
            reject_symlink_ancestors(self.root / path)
        return owner

    def _binding(self) -> dict[str, Any]:
        value = _json(self.binding_path)
        if value.get("owner") != OWNER or value.get("schema_version") != SCHEMA_VERSION or not _same_path(value.get("root", ""), str(self.root)):
            raise DeploymentError("invalid deployment binding ownership")
        release = Path(value.get("release_root", ""))
        if release.parent != self.root / "releases" or not re.fullmatch(r"[a-f0-9]{64}", release.name):
            raise DeploymentError("invalid deployment release root")
        for field, expected in (("application_root", release / "package"), ("dependencies_root", release / "dependencies"), ("commands_root", self.root / "bin")):
            if value.get(field) != str(expected):
                raise DeploymentError(f"invalid deployment {field}")
        if value.get("state_root") != str(self.state_root):
            raise DeploymentError("private instructions state differs from the saved deployment root")
        python = value.get("python")
        if not isinstance(python, dict) or not Path(python.get("path", "")).is_absolute():
            raise DeploymentError("invalid Python binding")
        managed = python.get("managed_root")
        if managed and (Path(managed).parent != self.root / "runtimes" or not _within(Path(python["path"]), Path(managed))):
            raise DeploymentError("invalid managed Python ownership")
        if not isinstance(value.get("command_inventory"), dict) or set(value["command_inventory"]) != set(COMMANDS):
            raise DeploymentError("invalid command ownership inventory")
        return value

    def _probe(self, binding: dict[str, Any]) -> None:
        python = Path(binding["python"]["path"])
        if not python.is_file() or _hash(python) != binding["python"]["sha256"]:
            raise DeploymentError(f"Python binding changed or is missing: {python}")
        env = dict(self.env, PYTHONDONTWRITEBYTECODE="1", AGENT_BIOS_WINDOWS_BINDING=str(self.binding_path))
        # The entry handles embeddable _pth isolation before native imports.
        result = subprocess.run([str(python), "-I", "-B", str(Path(binding["application_root"]) / "compose" / ENTRY),
                                 "--dependencies", binding["dependencies_root"], "--script",
                                 str(Path(binding["application_root"]) / "compose/native_cli.py"), "--version"],
                                env=env, capture_output=True, text=True, timeout=60)
        if result.returncode or result.stdout.strip() != binding["version"]:
            raise DeploymentError(f"staged application probe failed: {(result.stderr or result.stdout).strip()}")

    def _stage(self, source: Path, parent: str, owner: dict[str, Any]) -> tuple[Path, dict[str, str]]:
        inventory = _inventory(source)
        if not inventory:
            raise DeploymentError("cannot stage an empty bundle")
        digest = hashlib.sha256(_canonical(inventory)).hexdigest()
        target = self.root / parent / digest
        reject_symlink_ancestors(target)
        claims = owner.setdefault("trees", {})
        relative = target.relative_to(self.root).as_posix()
        if target.exists():
            if claims.get(relative) != inventory:
                raise DeploymentError(f"unowned or changed immutable destination: {target}")
            observed = _inventory(target)
            if set(observed) - set(inventory):
                raise DeploymentError(f"unexpected files in owned release: {target}")
            # Repair only previously claimed bytes. Do not delete unknown files
            # or replace a version directory that running workers may still use.
            for name, digest in inventory.items():
                if observed.get(name) != digest:
                    _atomic(target / name, (source / name).read_bytes())
            _check_inventory(target, inventory)
            return target, inventory
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=target.parent))
        try:
            shutil.copytree(source, temporary, dirs_exist_ok=True)
            _check_inventory(temporary, inventory)
            # Claim exactly these files before publication for resumable cleanup.
            claims[relative] = inventory
            _atomic(self.root / "owner.json", _canonical(owner))
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return target, inventory

    @contextlib.contextmanager
    def _private_installer(self, binding: dict[str, Any]):
        """Private projections and all children retain the selected entry/deps."""
        runtime_env = {"AGENT_BIOS_PYTHON_ENTRY": str(Path(binding["application_root"]) / "compose" / ENTRY),
                       "AGENT_BIOS_PYTHON_DEPS": binding["dependencies_root"],
                       "AGENT_BIOS_PYTHON_EXECUTABLE": binding["python"]["path"]}
        home = Path(self.env.get("HOME", str(Path.home()))).expanduser().resolve()
        defaults = {"HOME": str(home), "AGENT_BIOS_STATE_DIR": str(self.state_root),
                    "AGENT_BIOS_INSTRUCTIONS_DIR": str(home / ".config/agent-bios/corpus"),
                    "CLAUDE_CONFIG_DIR": str(home / ".claude"), "CODEX_HOME": str(home / ".codex")}
        private_env = {name: str(Path(self.env.get(name, default)).expanduser().resolve()) for name, default in defaults.items()}
        runtime_env.update(private_env)
        binding["private_environment"] = private_env
        previous = {name: os.environ.get(name) for name in runtime_env}
        try:
            os.environ.update(runtime_env)
            yield self.installer_factory(Path(binding["application_root"]), dict(self.env, **runtime_env))
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def _install_preflight(self, source: Path, version: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        owner = self._owned(allow_absent=True)
        prior = self._binding() if self.binding_path.exists() else None
        record = self.installer_factory(source / "package", self.env).record_path
        reject_symlink_ancestors(record)
        if record.exists() and (owner is None or prior is None):
            raise DeploymentError("existing private installation requires an explicit deployment handoff; "
                                  "a new or detached script root cannot adopt state owned by another installation")
        floors = [value for value in ((owner or {}).get("last_version"), (prior or {}).get("version")) if value is not None]
        for floor in floors:
            if _version(version) < _version(floor):
                raise DeploymentError(f"version downgrade refused: {floor} -> {version}")
        return owner, prior

    def install(self, source: Path, python: Path, managed_runtime: Path | None = None) -> dict[str, Any]:
        source = Path(source).resolve()
        python = Path(python).resolve()
        if _within(source, self.root) or _within(self.root, source):
            raise DeploymentError("source bundle and deployment root must be separate")
        if managed_runtime is None and _within(python, source):
            raise DeploymentError("a Python inside the temporary source bundle must be supplied as managed runtime")
        manifest = _json(source / "package/package.json")
        version = manifest.get("version")
        _version(version)
        if manifest.get("name") != "agent-bios":
            raise DeploymentError("application bundle is not agent-bios")
        for relative in ("package/compose/" + ENTRY, *("commands/" + name for name in COMMANDS)):
            if not (source / relative).is_file():
                raise DeploymentError(f"incomplete application bundle: {relative}")
        if not (source / "dependencies").is_dir():
            raise DeploymentError("incomplete application bundle: dependencies")
        if not python.is_file():
            raise DeploymentError(f"Python is absent: {python}")
        _inventory(source)  # Reject redirects before claiming or writing a root.
        self._install_preflight(source, version)  # Refuse foreign ownership before even creating a state lock.
        with transaction_lock(self.state_root):
            owner, prior = self._install_preflight(source, version)
            owner = owner or {"owner": OWNER, "schema_version": SCHEMA_VERSION, "root": str(self.root),
                              "state_root": str(self.state_root), "trees": {}}
            _atomic(self.root / "owner.json", _canonical(owner))
            release, inventory = self._stage(source, "releases", owner)
            managed_root = None
            if managed_runtime is not None:
                managed_runtime = Path(managed_runtime).resolve()
                if not _within(python, managed_runtime):
                    raise DeploymentError("selected Python is outside the supplied managed runtime")
                relative_python = python.relative_to(managed_runtime)
                managed_root, _ = self._stage(managed_runtime, "runtimes", owner)
                python = managed_root / relative_python
            elif _within(python, self.root):
                if not prior or prior["python"]["path"] != str(python) or not prior["python"].get("managed_root"):
                    raise DeploymentError("Python inside the deployment root must have recorded runtime ownership")
                managed_root = Path(prior["python"]["managed_root"])
            binding = {"owner": OWNER, "schema_version": SCHEMA_VERSION, "root": str(self.root),
                       "version": version, "content_id": release.name, "release_root": str(release),
                       "application_root": str(release / "package"), "dependencies_root": str(release / "dependencies"),
                       "commands_root": str(self.root / "bin"), "state_root": str(self.state_root),
                       "python": {"path": str(python), "sha256": _hash(python), "managed_root": str(managed_root) if managed_root else None},
                       "inventory": inventory, "command_inventory": {name: _hash(release / "commands" / name) for name in COMMANDS}}
            self.probe(binding)
            old_commands = (prior or {}).get("command_inventory", {})
            for name in COMMANDS:
                destination = self.root / "bin" / name
                reject_symlink_ancestors(destination)
                if destination.exists() and _hash(destination) not in (old_commands.get(name), binding["command_inventory"][name]):
                    raise DeploymentError(f"modified or unowned command: {destination}")
            operation = {"owner": OWNER, "schema_version": SCHEMA_VERSION, "version": version,
                         "phase": "prepared", "application_root": str(release / "package")}
            _atomic(self.root / "operation.json", _canonical(operation))
            with self._private_installer(binding) as installer:
                configured = installer.record_path.exists()
                if configured:
                    operation["phase"] = "private_update_pending"
                    _atomic(self.root / "operation.json", _canonical(operation))
                    try:
                        installer.install()
                    except Exception as exc:
                        operation.update(phase="private_update_needs_recovery", error=type(exc).__name__)
                        _atomic(self.root / "operation.json", _canonical(operation))
                        raise DeploymentError("private environment update failed; native recovery is required; active binding was not switched") from exc
                    operation["phase"] = "private_environment_updated"
                    _atomic(self.root / "operation.json", _canonical(operation))
            for name in COMMANDS:
                _atomic(self.root / "bin" / name, (release / "commands" / name).read_bytes())
            platform_path = self.root / "platform.json"
            prior_platform = _json(platform_path) if platform_path.exists() else {}
            if prior_platform and (prior_platform.get("owner") != OWNER or prior_platform.get("root") != str(self.root)):
                raise DeploymentError("invalid platform ownership receipt")
            receipt = self.integration.apply(self.root, prior_platform)
            _atomic(platform_path, _canonical(receipt))
            _atomic(self.binding_path, _canonical(binding))
            owner.update(last_version=version, private_environment=binding["private_environment"])
            _atomic(self.root / "owner.json", _canonical(owner))
            operation["phase"] = "complete"
            _atomic(self.root / "operation.json", _canonical(operation))
            return {"application_deployed": True, "version": version, "root": str(self.root),
                    "commands_root": binding["commands_root"], "binding_path": str(self.binding_path),
                    "private_environment_updated": configured, "configuration_pending": not configured,
                    "activation": "unverified"}

    def verify(self) -> dict[str, Any]:
        self._owned()
        binding = self._binding()
        _check_inventory(Path(binding["release_root"]), binding["inventory"])
        _check_inventory(self.root / "bin", binding["command_inventory"], exact=False)
        self.probe(binding)
        if (self.root / "operation.json").exists() and _json(self.root / "operation.json").get("phase") != "complete":
            raise DeploymentError("Windows deployment operation is incomplete; rerun the same verified installation to recover")
        with self._private_installer(binding) as installer:
            configured = installer.record_path.exists()
            if configured:
                installer.verify()
        return {"application_deployed": True, "version": binding["version"], "root": str(self.root),
                "configuration_pending": not configured, "activation": "unverified"}

    def uninstall(self) -> dict[str, Any]:
        self._owned()
        with transaction_lock(self.state_root):
            owner = self._owned()
            binding = self._binding()
            platform = _json(self.root / "platform.json")
            if platform.get("owner") != OWNER or platform.get("root") != str(self.root) or platform.get("schema_version") != SCHEMA_VERSION:
                raise DeploymentError("invalid platform ownership receipt")
            if hasattr(self.integration, "_validate"):
                self.integration._validate(self.root, platform)
            for name in COMMANDS:
                reject_symlink_ancestors(self.root / "bin" / name)
            with self._private_installer(binding) as installer:
                if hasattr(installer, "_active_intents") and installer._active_intents():
                    raise DeploymentError("active instructions activation requires completion before application removal")
                installer.uninstall()
            retained = self.integration.remove(self.root, platform)
            for name, digest in binding["command_inventory"].items():
                path = self.root / "bin" / name
                reject_symlink_ancestors(path)
                if path.is_file() and _hash(path) == digest:
                    path.unlink()
                elif path.exists():
                    retained.append(str(path))
            releases, runtimes = [], []
            for relative, inventory in owner.get("trees", {}).items():
                target = self.root / relative
                if Path(relative).is_absolute() or ".." in Path(relative).parts or target.parent not in (self.root / "releases", self.root / "runtimes"):
                    raise DeploymentError("invalid owned tree claim")
                reject_symlink_ancestors(target)
                if not target.exists():
                    continue
                # Historical app helpers/session resources retain absolute entry,
                # dependency and Python paths beyond the active binding. Garbage
                # collection is deferred until all those references are inventoried.
                (runtimes if target.parent == self.root / "runtimes" else releases).append(str(target))
            owner.update(last_version=binding["version"], private_environment=binding["private_environment"])
            _atomic(self.root / "owner.json", _canonical(owner))
            for name in ("deployment.json", "platform.json", "operation.json"):
                (self.root / name).unlink(missing_ok=True)
            for directory in (self.root / "bin", self.root / "releases", self.root / "runtimes", self.root):
                with contextlib.suppress(OSError):
                    directory.rmdir()
            return {"application_removed": True, "retained_paths": retained,
                    "retained_release_paths": releases, "retained_runtime_paths": runtimes,
                    "external_python_preserved": binding["python"]["managed_root"] is None,
                    "private_instructions_preserved": True, "sessions_preserved": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    install = subcommands.add_parser("install")
    install.add_argument("--source", type=Path, required=True)
    install.add_argument("--python", type=Path, required=True)
    install.add_argument("--managed-runtime", type=Path)
    for command in (install, subcommands.add_parser("verify"), subcommands.add_parser("uninstall")):
        command.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        deployment = Deployment(args.root)
        result = deployment.install(args.source, args.python, args.managed_runtime) if args.command == "install" else getattr(deployment, args.command)()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"windows-deploy: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
