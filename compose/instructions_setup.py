"""Shared setup controller, read-only dependency inventory, and numbered client."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Callable, TextIO

try:
    from instructions_setup_i18n import choice_label, dependency_display, translate
except ImportError:
    from .instructions_setup_i18n import choice_label, dependency_display, translate


class SetupError(RuntimeError):
    pass


class _Back(Exception):
    pass


class _Cancel(Exception):
    pass


def _display(value: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)[:240].strip()


def dependency_inventory(repo: Path, environ: dict[str, str] | None = None, *,
                         runner: Callable = subprocess.run,
                         which: Callable = shutil.which,
                         system: str | None = None) -> list[dict[str, Any]]:
    """Probe local commands without installing, authenticating, or fetching data."""
    env = dict(os.environ if environ is None else environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    home = Path(env.get("HOME", str(Path.home())))
    system = system or platform.system()
    supported = system in {"Darwin", "Linux", "Windows"}
    paths = {name: which(name, path=env.get("PATH", os.defpath))
             for name in ("bash", "python3", "node", "npm", "brew", "git", "zsh", "claude", "codex", "cp", "mktemp")}

    def probe(argv: list[str]) -> tuple[bool, str]:
        try:
            result = runner(argv, shell=False, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=5, env=env)
            text = (result.stdout or result.stderr or "").splitlines()
            return result.returncode == 0, _display(text[0] if text else "")
        except (OSError, subprocess.SubprocessError) as exc:
            return False, _display(str(exc))

    rows: list[dict[str, Any]] = []

    def add(identifier: str, title: str, role: str, purpose: str, *,
            path: str | None = None, argv: list[str] | None = None,
            action: list[str] | None = None, reason: str = "", scope: str = "",
            present: bool | None = None, version: str = "") -> dict[str, Any]:
        okay, detail = probe(argv) if argv else (bool(path) if present is None else present, version)
        row = {"id": identifier, "title": title, "role": role, "purpose": purpose,
               "status": "available" if okay else "missing", "path": path, "version": detail,
               "install_argv": action if not okay and supported else None,
               "install_scope": scope, "manual_reason": reason if not okay else ""}
        if not supported:
            row["manual_reason"] = "This installer supports macOS and Linux."
        rows.append(row)
        return row

    brew_row = add("homebrew", "Homebrew", "optional package manager", "Offers local package installation recipes when available.",
        path=paths["brew"], argv=[paths["brew"], "--version"] if paths["brew"] else None,
        reason="Optional: use an existing operating-system package manager or the official host installer.")
    brew = paths["brew"] if brew_row["status"] == "available" and system != "Windows" else None

    def formula(name: str) -> list[str] | None:
        return [brew, "install", name] if brew else None

    add("bash", "Bash", "runtime", "Runs the package entry point and bundled shell tools.",
        path=paths["bash"], argv=[paths["bash"], "--version"] if paths["bash"] else None,
        action=formula("bash"), scope="Homebrew prefix", reason="Install Bash using your operating system package manager.")
    py = sys.executable if system == "Windows" else paths["python3"]
    add("python3", "Python 3.11+", "runtime", "Runs installation, instructions storage, and terminal interfaces.", path=py,
        argv=[py, "-c", "import sys; print(sys.version.split()[0]); raise SystemExit(sys.version_info < (3,11))"] if py else None,
        action=formula("python"), scope="Homebrew prefix", reason="Install Python 3.11+ and ensure python3 resolves to it.")
    node = paths["node"]
    node_row = add("node", "Node.js 22+", "delivery / optional host install", "Supports npm host installation and optional slide rendering.", path=node,
        argv=[node, "--version"] if node else None, action=formula("node"), scope="Homebrew prefix",
        reason="Install a current Node.js distribution with npm; the instructions runtime itself does not need Node.")
    node_major = re.match(r"v?(\d+)", node_row["version"])
    major = int(node_major[1]) if node_major and node_row["status"] == "available" else 0
    if node_row["status"] == "available" and major < 22:
        node_row["status"] = "missing"
        if supported:
            node_row.update(install_argv=formula("node"), manual_reason="Node.js 22+ is required by the Claude npm installer.")
    npm = paths["npm"]
    npm_row = add("npm", "npm", "delivery / optional host install", "Installs the package and selected host CLIs.", path=npm,
        argv=[npm, "--version"] if npm else None,
        reason="npm comes with Node.js; install Node.js first and rerun setup.")
    npm = npm if npm_row["status"] == "available" else None
    for identifier, title, package, minimum in (("codex", "Codex CLI", "@openai/codex", 18),
                                                  ("claude", "Claude Code", "@anthropic-ai/claude-code", 22)):
        action = [brew, "install", "--cask", "codex" if identifier == "codex" else "claude-code"] if brew else (
            [npm, "install", "-g", package] if npm and major >= minimum else None)
        path = paths[identifier]
        add(identifier, title, "selected host", "Required to launch this host; sign-in is a separate step.", path=path,
            argv=[path, "--version"] if path else None, action=action,
            scope="Homebrew prefix and required dependencies" if brew else "npm global prefix",
            reason=f"Use the official installer, or install npm with Node.js {minimum}+ and rerun setup.")
    for identifier, title, role, purpose in (
        ("git", "Git", "workflow", "Clone updates, worktrees, and version-control workflows."),
        ("zsh", "zsh", "optional shell connection", "Optional interception of bare host commands."),
    ):
        path = paths[identifier]
        add(identifier, title, role, purpose, path=path, argv=[path, "--version"] if path else None,
            action=formula(identifier), scope="Homebrew prefix", reason="Install with your operating system package manager.")
    for identifier in ("cp", "mktemp"):
        add(identifier, identifier, "shell adapters", "Required by optional shell worker adapters.", path=paths[identifier],
            reason="Install the standard BSD or GNU command-line utilities for your system.")
    venv = Path(env.get("AGENT_LAUNCH_VENV") or str(home / ".local/share/agent-launch/venv"))
    vpy = venv / "bin/python"
    configured_python = env.get("AGENT_LAUNCH_PYTHON")
    bootstrap_python = which(configured_python, path=env.get("PATH", os.defpath)) if configured_python else py
    provisioner = Path(repo) / "launch/provision-venv.sh"
    pins = {}
    if provisioner.is_file():
        pins = dict(re.findall(r'\b(?:TEXTUAL|JSONSCHEMA)_PIN="([a-z]+)==([0-9][a-zA-Z0-9_.-]*)"', provisioner.read_text(encoding="utf-8")))
        if set(pins) != {"textual", "jsonschema"}:
            raise SetupError("Bundled managed dependency pins are incomplete; verify or reinstall the agent-bios package.")

    def module_probe(interpreter: str, name: str, *, managed: bool = False) -> list[str]:
        code = f"import {name}; import importlib.metadata; actual = importlib.metadata.version({name!r}); print(actual)"
        if name == "jsonschema":
            code += "; from jsonschema import Draft202012Validator"
        if managed and name in pins:
            code += f"; import sys; raise SystemExit(sys.version_info < (3, 11) or actual != {pins[name]!r})"
        return [interpreter, "-c", code]

    bootstrap = add("python-venv", "Python venv / pip bootstrap", "managed dependency prerequisite", "Creates the managed environment using AGENT_LAUNCH_PYTHON when set, otherwise python3.", path=bootstrap_python,
        argv=[bootstrap_python, "-c", "import sys, venv, ensurepip; print('venv; bundled pip ' + ensurepip.version()); raise SystemExit(sys.version_info < (3, 11))"] if bootstrap_python else None,
        reason="Install venv/ensurepip for Python 3.11+; check AGENT_LAUNCH_PYTHON if configured. An existing managed environment does not need this bootstrap.")
    can_provision = system != "Windows" and bool(paths["bash"] and provisioner.is_file() and (vpy.is_file() or bootstrap["status"] == "available"))
    try:
        from .instructions_ui_runtime import runtime_inventory
    except ImportError:
        from instructions_ui_runtime import runtime_inventory
    ui = runtime_inventory(Path(repo))
    bundle = str(Path(repo) / "compose/ui_runtime")
    textual_version = next((row["version"] for row in ui.get("packages", []) if row["name"] == "textual"), "")
    add("textual", "Textual (included)", "bundled UI runtime", "The terminal UI uses verified bundled packages without a system or managed Textual installation.",
        path=bundle, present=ui["status"] == "available", version=textual_version,
        scope="process-owned temporary directory",
        reason="The shipped UI bundle is unavailable; verify or reinstall this agent-bios package. " + "; ".join(ui.get("issues", [])))
    for package in ui.get("packages", []):
        if package["name"] == "textual":
            continue
        add("ui-" + package["name"], package["name"] + " (included)", "bundled UI dependency",
            "Included in the Textual runtime; no separate installation is needed.",
            path=bundle, present=True, version=package["version"], scope="process-owned temporary directory")
    learning_ready, learning_version = probe(module_probe(py, "jsonschema")) if py else (False, "")
    learning_python = py
    if not learning_ready and vpy.is_file():
        learning_ready, learning_version = probe(module_probe(str(vpy), "jsonschema", managed=True))
        learning_python = str(vpy)
    add("jsonschema", "jsonschema", "learning capture", "Validates end-user learn submissions against JSON Schema Draft 2020-12, and also serves the author gate.",
        path=learning_python, present=learning_ready, version=learning_version,
        action=[paths["bash"], str(provisioner), "--learning-only"] if can_provision else None,
        scope=str(venv), reason="Select the managed learning validator installation; learn uses it when system Python lacks jsonschema.")
    for identifier, title, purpose in (
        ("slide-playwright", "Playwright module", "Static slide jobs bind an explicit Playwright module file."),
        ("slide-pdf-lib", "pdf-lib", "Static slide jobs resolve pdf-lib beside the selected Playwright module."),
        ("slide-browser", "Chromium-family browser", "Static slide jobs bind an explicit browser executable."),
        ("spreadsheet-processing", "Spreadsheet-processing skill", "Selected spreadsheet guidance can use this optional personal skill."),
        ("mcp-servers", "User-specific MCP servers", "Only user-selected workflows require their configured external services."),
    ):
        row = add(identifier, title, "optional job / personal integration", purpose, present=False,
                  reason="Configure this only for a workflow that requires it; setup cannot choose your job environment or account.")
        row["status"] = "not assessed"
    if system == "Windows":
        rows = [row for row in rows if row["id"] not in {"homebrew", "bash", "zsh", "cp", "mktemp", "python-bootstrap"}]
    return rows


def catalog_choices(installer: Any) -> list[dict[str, str]]:
    if hasattr(installer, "setup_catalog"):
        catalog = installer.setup_catalog()
    else:
        try:
            from instructions_catalog import load_catalog
        except ImportError:
            from .instructions_catalog import load_catalog
        catalog = load_catalog(installer.repo)
    choices: list[dict[str, str]] = []
    for package in catalog["packages"]:
        package_id = package["package_id"]
        choices.append({"target": package_id, "label": "All content in " + package_id})
        for name, description in sorted(package.get("domains", {}).items()):
            choices.append({"target": package_id + "/" + name, "label": f"{description} ({package_id}/{name})"})
    if not choices:
        raise SetupError("No instructions packages are available for selection.")
    return choices


def _indexes(value: str, count: int) -> list[int]:
    if value.lower() in {"", "none"}:
        return []
    try:
        indexes = sorted({int(part.strip()) - 1 for part in value.split(",")})
    except ValueError as exc:
        raise SetupError("Enter comma-separated numbers, or none.") from exc
    if any(index < 0 or index >= count for index in indexes):
        raise SetupError("A selected number is outside the displayed list.")
    return indexes


def format_setup_result(result: dict[str, Any], language: str = "en", *, interface: str = "terminal") -> str:
    """Summarize completion without exposing the runtime file inventory."""
    if interface not in {"terminal", "conversation"}:
        raise ValueError("unknown setup presentation")
    def t(message: str, **values: Any) -> str:
        return translate(language, message, **values)

    def recovery_hint() -> str:
        return t("Use the returned review_id with agent-bios setup status or agent-bios setup resume before continuing.")

    if result.get("cancelled"):
        if result.get("cancelled_after_start"):
            lines = [t("Setup stopped after the current operation finished.")]
            completed = [row["id"] for row in result.get("dependency_results", []) if row.get("returncode") == 0]
            if completed:
                lines.append(t("Dependencies retained: {dependencies}.", dependencies=", ".join(completed)))
            if result.get("installation_applied"):
                lines.append(t("The private runtime installation is retained; remaining setup was not applied."))
            else:
                lines.append(t("The private runtime installation was not applied."))
            if interface == "conversation":
                lines.append(recovery_hint())
            return "\n".join(lines)
        return t("Setup cancelled. No installation changes were applied.")
    if result.get("dry_run"):
        return t("Setup preview complete. No installation changes were applied.")
    completed = [row["id"] for row in result.get("dependency_results", []) if row.get("returncode") == 0]
    if result.get("installation_error"):
        lines = [t("Private runtime installation needs attention: {error}", error=str(result["installation_error"]))]
        if completed:
            lines.append(t("Dependencies retained: {dependencies}.", dependencies=", ".join(completed)))
        lines.append(recovery_hint() if interface == "conversation" else t("Inspect the reported state and rerun agent-bios install."))
        return "\n".join(lines)
    if result.get("dependency_failed"):
        lines = [t("Dependency installation failed: {dependency}. The private runtime was not installed by this setup.", dependency=result["dependency_failed"])]
        if completed:
            lines.append(t("Dependencies already installed: {dependencies}.", dependencies=", ".join(completed)))
        lines.append(recovery_hint() if interface == "conversation" else t("Resolve the dependency error and run agent-bios install --interactive again."))
        return "\n".join(lines)
    if result.get("extras_error"):
        lines = [t("Private runtime installed; app registration or instruction capture needs attention."),
                 str(result["extras_error"])]
        if (result.get("extras") or {}).get("app_bridge", {}).get("registered"):
            lines.append(t("The app command registration is retained; instruction capture did not complete."))
        if completed:
            lines.append(t("Dependencies installed: {dependencies}.", dependencies=", ".join(completed)))
        lines.append(recovery_hint() if interface == "conversation" else t("Open Instructions Studio: agent-bios instructions (terminal or Codex app terminal panel)."))
        return "\n".join(lines)
    if not result.get("applied"):
        return t("Setup did not complete.")
    plan = result.get("plan", {})
    lines = [t("Setup complete. Private runtime installed.")]
    if completed:
        lines.append(t("Dependencies installed: {dependencies}.", dependencies=", ".join(completed)))
    mode, targets = plan.get("selection_mode"), plan.get("targets") or []
    if mode == "none":
        lines.append(t("Instructions for future activated sessions: none."))
    elif mode == "selected":
        instructions = t("all available instructions") if targets == ["all"] else ", ".join(targets)
        lines.append(t("Instructions for future activated sessions: {instructions}.", instructions=instructions))
    elif mode == "default":
        lines.append(t("Instructions policy: core, infrastructure and personal instructions; selected domains: {domains}.", domains=", ".join(targets))
                     if targets else t("Instructions policy: core, infrastructure and personal instructions."))
    else:
        lines.append(t("Saved instructions policy and item choices preserved."))
    extras = result.get("extras") or {}
    bridge = extras.get("app_bridge") or (result.get("installation") or {}).get("app_bridge") or {}
    if bridge.get("needs_action"):
        lines.append(t("Codex app bridge needs attention; existing files were preserved:"))
        lines.extend("- " + str(message) for message in bridge["needs_action"])
    if bridge.get("registered"):
        lines.append(t("Codex app bridge registered: use $agent-bios for per-task preview/use/off and instructions management."))
    captured = extras.get("import") or {}
    if captured.get("capture_id"):
        count = captured.get("source_count")
        lines.append(t("Instruction capture: {capture_id} ({count} source files). Model review is required before activation.",
                       capture_id=captured["capture_id"], count=count) if count is not None else
                     t("Instruction capture: {capture_id}. Model review is required before activation.", capture_id=captured["capture_id"]))
        if captured.get("next_command"):
            lines.append(t("Next: {command}", command=str(captured["next_command"])))
        if bridge.get("registered") and captured.get("app_request"):
            request = str(captured["app_request"])
            if request == f"Use $agent-bios to import capture {captured['capture_id']}":
                request = t("Use $agent-bios to import capture {capture_id}", capture_id=captured["capture_id"])
            lines.append(t("In Codex: {request}", request=request))
    lines.append(t("Continue in the conversation using the returned verified entrypoint.") if interface == "conversation"
                 else t("Open Instructions Studio: agent-bios instructions (terminal or Codex app terminal panel)."))
    return "\n".join(lines)


def review_summary(plan: dict[str, Any], dependencies: list[dict[str, Any]],
                   choices: list[dict[str, Any]], language: str = "en") -> str:
    """Render the shared human review without importing a UI framework."""
    def t(message: str, **values: Any) -> str:
        return translate(language, message, **values)
    labels = {row["target"]: choice_label(language, row) for row in choices}
    labels["all"] = t("All available instructions")
    mode, targets = plan.get("selection_mode"), plan.get("targets") or []
    if mode is None:
        instructions = t("Keep the saved instructions policy and item choices")
    elif mode == "none":
        instructions = t("No active instructions")
    elif targets == ["all"]:
        instructions = t("All available instructions")
    else:
        instructions = ", ".join(labels.get(value, value) for value in targets) or t("No selected items")
    selected = set(plan.get("dependencies") or [])
    installs = [dependency_display(language, row) for row in dependencies if row["id"] in selected]
    lines = [t("Ready to apply"), "", t("Instructions: {selection}", selection=instructions),
             t("App connection: {connection}", connection=t("Register $agent-bios for explicit task use") if plan.get("app_bridge") else t("No new app registration"))]
    if installs:
        lines.append(t("Install:"))
        lines.extend("  " + row["title"] + (" — " + row["install_scope"] if row.get("install_scope") else "") for row in installs)
    else:
        lines.append(t("Install dependencies: none"))
    sources = plan.get("import_paths") or []
    lines.append(t("Prepare for model review: {count} instruction file(s)", count=len(sources)))
    lines.extend("  " + path for path in sources)
    lines.extend(["", t("Native global and project instruction files are preserved."),
                  t("This setup does not add instructions to the current app task."),
                  t("Library files remain stored privately when active instructions are off.")])
    if sources:
        lines.append(t("Captured instructions need a separate semantic review before import."))
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", "\n".join(lines))


class SetupController:
    """One read-only plan and selected execution path for installation clients."""

    FIELDS = {"selection_mode", "targets", "dependencies", "app_bridge", "import_paths", "project_roots"}

    def __init__(self, installer: Any, *, runner: Callable = subprocess.run,
                 inventory: list[dict[str, Any]] | None = None, extras_handler: Callable | None = None):
        self.installer = installer
        self.runner = runner
        self.dependencies = inventory if inventory is not None else dependency_inventory(installer.repo, installer.env, runner=runner)
        self.choices = catalog_choices(installer)
        retained = getattr(installer, "setup_local_instructions", None)
        self.retained_instructions = retained() if callable(retained) else []
        self.handler = extras_handler or getattr(installer, "setup_extras", None)
        identifiers = [row["id"] for row in self.dependencies]
        if len(identifiers) != len(set(identifiers)):
            raise SetupError("Dependency inventory has duplicate identifiers.")

    def default_plan(self, selection_mode: str | None = None, targets: list[str] | None = None) -> dict[str, Any]:
        if selection_mode is None and targets is None:
            status = getattr(self.installer, "status", None)
            selection_mode = None if callable(status) and status().get("installed") else "none"
        return {"selection_mode": selection_mode,
                "targets": list(targets) if targets is not None else (None if selection_mode is None else []),
                "dependencies": [], "app_bridge": False, "import_paths": [], "project_roots": []}

    def discover(self, project_roots: list[str]) -> dict[str, Any]:
        if not isinstance(project_roots, list) or not all(isinstance(value, str) and Path(value).is_absolute()
                                                         and Path(value).is_dir() for value in project_roots):
            raise SetupError("Project roots must be existing absolute directories.")
        discovery = getattr(self.installer, "setup_discover", None)
        if not callable(discovery):
            raise SetupError("Instruction discovery is unavailable in this installer.")
        found = discovery(project_roots)
        return found if isinstance(found, dict) else {"sources": found, "omitted": []}

    def _plan(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) - self.FIELDS - {"dependency_actions"}:
            raise SetupError("Installation plan contains unsupported fields.")
        if not self.FIELDS <= set(value):
            raise SetupError("Installation plan is incomplete.")
        plan = {key: value[key] for key in self.FIELDS}
        mode, targets = plan["selection_mode"], plan["targets"]
        if (mode is not None and not isinstance(mode, str)) or mode not in {None, "default", "selected", "none"}:
            raise SetupError("Unsupported instructions selection mode.")
        if targets is not None and (not isinstance(targets, list) or not all(isinstance(x, str) and x for x in targets)):
            raise SetupError("Instructions targets must be a list of qualified names.")
        if mode == "selected" and not targets:
            raise SetupError("Select at least one instructions, or choose no active instructions.")
        if mode == "none" and targets:
            raise SetupError("No active instructions cannot include selected targets.")
        if mode is None and targets:
            raise SetupError("Keeping saved selection cannot specify new targets.")
        if type(plan["app_bridge"]) is not bool:
            raise SetupError("App registration must be an explicit boolean choice.")
        for key in ("dependencies", "import_paths", "project_roots"):
            items = plan[key]
            if not isinstance(items, list) or not all(isinstance(x, str) and x for x in items) or len(set(items)) != len(items):
                raise SetupError(f"{key} must be a list of distinct values.")
        available = {row["id"]: row for row in self.dependencies}
        for name in plan["dependencies"]:
            if name not in available or not available[name].get("install_argv"):
                raise SetupError(f"Dependency has no reviewed installation recipe: {name}")
        if (plan["app_bridge"] or plan["import_paths"]) and not callable(self.handler):
            raise SetupError("The requested app/import integration is unavailable.")
        return json.loads(json.dumps(plan))

    def _sources(self, plan: dict[str, Any]) -> list[dict[str, str]]:
        if not plan["import_paths"]:
            return []
        found = self.discover(plan["project_roots"])
        allowed = {row["path"]: row for row in found["sources"]}
        if not set(plan["import_paths"]) <= set(allowed):
            raise SetupError("Instruction selection is outside the current discovery set.")
        try:
            from .instructions_import import _read_source
        except ImportError:
            from instructions_import import _read_source
        return [{"path": path, "sha256": hashlib.sha256(_read_source(allowed[path])[0]).hexdigest()}
                for path in plan["import_paths"]]

    def _install(self, plan: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        if plan["selection_mode"] is None:
            return self.installer.install(dry_run=dry_run)
        return self.installer.install(dry_run=dry_run, selection_mode=plan["selection_mode"], targets=plan["targets"])

    def preview(self, value: dict[str, Any]) -> dict[str, Any]:
        plan = self._plan(value)
        actions = [row for row in self.dependencies if row["id"] in plan["dependencies"]]
        concrete = dict(plan, dependency_actions=[{"id": row["id"], "argv": list(row["install_argv"]),
                                                  "scope": row["install_scope"]} for row in actions])
        sources = self._sources(plan)
        result = {"plan": concrete, "installation": self._install(plan, True),
                  "extras": self.handler(plan, dry_run=True) if plan["app_bridge"] or plan["import_paths"] else None,
                  "source_versions": sources}
        revision = getattr(self.installer, "setup_revision", None)
        if callable(revision):
            result["state_revision"] = revision()
        result["review_id"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return result

    def apply(self, value: dict[str, Any], preview: dict[str, Any] | None = None, *,
              progress: Callable[[dict[str, Any]], None] | None = None,
              should_cancel: Callable[[], bool] | None = None,
              reuse_installation: bool = False) -> dict[str, Any]:
        if type(reuse_installation) is not bool:
            raise SetupError("reuse_installation must be boolean")
        checked = self.preview(value)
        if preview is not None and checked != preview:
            raise SetupError("Installation inputs changed after review; inspect a fresh plan before Apply.")
        plan = self._plan(checked["plan"])
        result: dict[str, Any] = {"applied": False, "plan": checked["plan"], "dependency_results": []}

        def emit(stage: str, message: str, **extra) -> None:
            if progress:
                progress({"stage": stage, "message": message, **extra})

        def cancelled() -> bool:
            if should_cancel and should_cancel():
                result.update(cancelled=True, cancelled_after_start=bool(result["dependency_results"] or result.get("installation_applied")))
                return True
            return False

        for action in checked["plan"]["dependency_actions"]:
            if cancelled():
                return result
            emit("dependency", "Installing " + action["id"], dependency=action["id"], phase="started")
            try:
                process = self.runner(action["argv"], shell=False, stdin=subprocess.DEVNULL,
                                      env=dict(self.installer.env), check=False, capture_output=True,
                                      text=True, errors="replace")
            except OSError as exc:
                outcome = {"id": action["id"], "returncode": None, "stdout": "", "stderr": str(exc)}
                result["dependency_results"].append(outcome)
                result["dependency_failed"] = action["id"]
                emit("dependency", "Could not start " + action["id"], phase="not_started", **outcome)
                return result
            outcome = {"id": action["id"], "returncode": process.returncode,
                       "stdout": (getattr(process, "stdout", "") or "")[-16000:],
                       "stderr": (getattr(process, "stderr", "") or "")[-16000:]}
            result["dependency_results"].append(outcome)
            emit("dependency", "Finished " + action["id"], phase="completed" if process.returncode == 0 else "failed", **outcome)
            if process.returncode:
                result["dependency_failed"] = action["id"]
                return result
        if cancelled():
            return result
        emit("install", "Installing the private runtime", phase="checking")
        try:
            revision = getattr(self.installer, "setup_revision", None)
            if callable(revision) and revision() != checked.get("state_revision"):
                raise SetupError("Private state changed after review; review the remaining installation again.")
            if self._sources(plan) != checked["source_versions"]:
                raise SetupError("Instruction sources changed after review; select and review them again.")
            if self._install(plan, True) != checked["installation"]:
                raise SetupError("Package or instructions selection changed after review; inspect a fresh plan.")
            if reuse_installation:
                verified = self.installer.verify()
                status = self.installer.status()
                installed_root = status.get("package_root")
                digest = Path(installed_root).name if isinstance(installed_root, str) else None
                if verified.get("stored") is not True or digest != checked["installation"].get("release_digest"):
                    raise SetupError("the reviewed package does not match the retained installation")
                result["installation"] = {**status, "verified": verified, "release_digest": digest}
                result["installation_reused"] = True
            else:
                emit("install", "Installing the private runtime", phase="started")
                result["installation"] = self._install(plan, False)
                result["installation_applied"] = True
            emit("install", "Installing the private runtime", phase="completed", installation=result["installation"],
                 reused=reuse_installation)
        except (OSError, RuntimeError, ValueError) as exc:
            result["installation_error"] = str(exc)
            return result
        if cancelled():
            return result
        try:
            if plan["app_bridge"] or plan["import_paths"]:
                emit("extras", "Preparing app registration and selected instruction capture", phase="checking")
                if self._sources(plan) != checked["source_versions"]:
                    raise SetupError("Instruction sources changed after review; review a new capture before continuing.")
                source_digests = {row["path"]: row["sha256"] for row in checked["source_versions"]}
                emit("extras", "Preparing app registration and selected instruction capture", phase="started")
                result["extras"] = self.handler(dict(plan, _expected_source_digests=source_digests), dry_run=False)
                emit("extras", "Preparing app registration and selected instruction capture", phase="completed", extras=result["extras"])
            else:
                result["extras"] = None
        except (OSError, RuntimeError, ValueError) as exc:
            result["extras_error"] = str(exc)
            if getattr(exc, "completed_extras", None):
                result["extras"] = exc.completed_extras
            return result
        result["applied"] = True
        emit("complete", "Setup complete")
        return result


def run_setup(installer: Any, *, input_fn: Callable[[str], str] | None = None,
              input_stream: TextIO | None = None, output_stream: TextIO | None = None,
              runner: Callable = subprocess.run, dry_run: bool = False,
              inventory: list[dict[str, Any]] | None = None,
              extras_handler: Callable | None = None) -> dict[str, Any]:
    """Collect a complete plan, then apply only the user's explicit selection."""
    out = output_stream or sys.stdout
    source = input_stream or sys.stdin
    controller = SetupController(installer, runner=runner, inventory=inventory, extras_handler=extras_handler)
    dependencies = controller.dependencies
    choices = controller.choices
    plan: dict[str, Any] = {"selection_mode": "none", "targets": [], "dependencies": [],
                            "app_bridge": False, "import_paths": [], "project_roots": []}

    def write(text: str = "") -> None:
        print(text, file=out, flush=True)

    def ask(prompt: str) -> str:
        try:
            if input_fn is not None:
                answer = input_fn(prompt)
            else:
                print(prompt, end="", file=out, flush=True)
                answer = source.readline()
                if not answer:
                    raise _Cancel()
            value = answer.strip()
            if value.lower() in {"cancel", "q", "quit"}:
                raise _Cancel()
            if value.lower() in {"back", "b"}:
                raise _Back()
            return value
        except (EOFError, KeyboardInterrupt, StopIteration):
            raise _Cancel() from None

    write("agent-bios setup — back returns to the previous step; cancel exits without applying.")
    write("Native AGENTS.md and CLAUDE.md remain user-owned. Instructions choices govern future activated sessions.")
    step = 0
    applying = False
    while True:
        try:
            if step == 0:
                write("\nDependencies (probes do not install or sign in):")
                available_actions = []
                for row in dependencies:
                    write(f"  {row['title']} — {row['status']} [{row['role']}] {row.get('version', '')}")
                    write("    " + row["purpose"])
                    if row.get("install_argv"):
                        available_actions.append(row)
                        write(f"    Install {len(available_actions)}: {shlex.join(row['install_argv'])} ({row['install_scope']})")
                    elif row.get("manual_reason"):
                        write("    " + row["manual_reason"])
                selected = _indexes(ask("Install numbers, or none [none]: "), len(available_actions))
                plan["dependencies"] = [available_actions[index]["id"] for index in selected]
                step = 1
            elif step == 1:
                write("\nInstructions: 1 no active instructions; 2 all available instructions; 3 selected packages/domains; 4 keep saved/default selection")
                value = ask("Instructions choice [1]: ") or "1"
                if value not in {"1", "2", "3", "4"}:
                    raise SetupError("Choose 1, 2, 3, or 4.")
                plan["selection_mode"] = {"1": "none", "2": "selected", "3": "selected", "4": None}[value]
                plan["targets"] = ["all"] if value == "2" else (None if value == "4" else [])
                step = 2 if value == "3" else 3
            elif step == 2:
                for index, choice in enumerate(choices, 1):
                    write(f"  {index}. {choice['label']}")
                selected = _indexes(ask("Instructions numbers: "), len(choices))
                if not selected:
                    raise SetupError("Select at least one instructions, or go back to choose no active instructions.")
                plan["targets"] = [choices[index]["target"] for index in selected]
                step = 3
            elif step == 3:
                write("\nCodex app bridge supports per-task instructions preview/use/off and instructions management through $agent-bios.")
                write("The TUI runs in a terminal or the Codex app terminal panel.")
                value = ask("Register the Codex app bridge? [y/N]: ").lower()
                if value not in {"", "n", "no", "y", "yes"}:
                    raise SetupError("Enter yes or no.")
                plan["app_bridge"] = value in {"y", "yes"}
                step = 4
            elif step == 4:
                write("\nPrepare existing instructions for personal instructions review. Source files are preserved.")
                write("Enter explicit project directories as JSON, for example [\"/path/to/project\"].")
                raw = ask("Project directories [skip; globals = global sources only]: ")
                if raw.lower() in {"", "skip", "none"}:
                    plan["project_roots"], plan["import_paths"] = [], []
                    step = 6
                    continue
                try:
                    roots = [] if raw.lower() == "globals" else json.loads(raw)
                except ValueError as exc:
                    raise SetupError("Enter a JSON list of absolute project directories, globals, or skip.") from exc
                if not isinstance(roots, list) or not all(isinstance(root, str) and Path(root).is_absolute() and Path(root).is_dir() for root in roots):
                    raise SetupError("Project roots must be existing absolute directories.")
                plan["project_roots"] = list(dict.fromkeys(roots))
                discovery = getattr(installer, "setup_discover", None)
                if not callable(discovery):
                    raise SetupError("Instruction discovery is unavailable in this installer.")
                found = discovery(plan["project_roots"])
                candidates = found.get("sources", []) if isinstance(found, dict) else found
                candidates = [dict(row) if isinstance(row, dict) else {"path": str(row)} for row in candidates]
                if not candidates:
                    write("No eligible instruction files were found in those locations.")
                    plan["import_paths"] = []
                    step = 6
                    continue
                step = 5
            elif step == 5:
                for index, row in enumerate(candidates, 1):
                    write(f"  {index}. {row['path']}")
                selected = _indexes(ask("Instruction file numbers to capture, or none [none]: "), len(candidates))
                plan["import_paths"] = [str(candidates[index]["path"]) for index in selected]
                step = 6
            else:
                preview = controller.preview(plan)
                write("\nReview installation plan:")
                write(json.dumps(preview, ensure_ascii=False, indent=2))
                if plan["import_paths"]:
                    write("Captured instructions require model review before choosing consumption surfaces. Capture alone does not activate them.")
                if dry_run:
                    return {"applied": False, "dry_run": True, **preview}
                value = ask("Type apply to execute this plan, back to revise, or cancel: ").lower()
                if value != "apply":
                    raise SetupError("Nothing was applied. Type apply, back, or cancel.")
                applying = True
                return controller.apply(plan, preview=preview, progress=lambda event: write(event["message"]))
        except _Back:
            step = {0: 0, 1: 0, 2: 1, 3: 2 if plan["selection_mode"] == "selected" and plan["targets"] != ["all"] else 1,
                    4: 3, 5: 4, 6: 4}.get(step, 4)
        except _Cancel:
            write("Setup cancelled; no installation plan was applied.")
            return {"cancelled": True, "applied": False}
        except SetupError as exc:
            if applying:
                raise
            write(str(exc))
