"""Qualify signed Windows script assets on an ephemeral GitHub Actions runner.

This exercises the delivered bootstrap and command wrappers in Windows PowerShell
5.1 and PowerShell 7. It never changes execution policy or starts a model login.
The runner-only guard protects a developer's persistent PATH from test fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile


SOURCE = Path(__file__).resolve().parents[2]
MARKER = "AGENT_BIOS_SCRIPT_SMOKE_JSON="


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest(path)
            for path in root.rglob("*") if path.is_file()}


class Driver:
    def __init__(self, assets: Path, scratch: Path, existing_python: Path):
        self.assets = assets
        self.scratch = scratch
        self.existing_python = existing_python.resolve(strict=True)
        self.checks: list[dict[str, object]] = []
        self.bootstrap = assets / "install.ps1"
        self.manifest = assets / "release.json"
        self.release = json.loads(self.manifest.read_text(encoding="utf-8-sig"))
        self.shells = [Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe",
                       Path(shutil.which("pwsh") or "")]
        if any(not shell.is_file() for shell in self.shells):
            raise AssertionError("Windows PowerShell 5.1 and PowerShell 7 must both be present")

    def checked(self, name: str, **detail: object) -> None:
        self.checks.append({"name": name, **detail})
        print(f"PASS: {name}", flush=True)

    def env(self, root: Path) -> dict[str, str]:
        home = root / "사용자 홈"
        home.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        for name in list(env):
            # PSModulePath: a pwsh 7 parent's value leaves Windows PowerShell 5.1 unable to
            # auto-load its Security module (Cert: drive, Get-AuthenticodeSignature).
            if name.startswith(("AGENT_BIOS_", "AGENT_LAUNCH_")) or name.upper() in {
                    "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "ZDOTDIR", "PSMODULEPATH"}:
                env.pop(name, None)
        env.update(HOME=str(home), USERPROFILE=str(home),
                   APPDATA=str(home / "AppData/Roaming"), LOCALAPPDATA=str(home / "AppData/Local"),
                   AGENT_BIOS_STATE_DIR=str(home / "state"),
                   AGENT_BIOS_INSTRUCTIONS_DIR=str(home / "personal"),
                   CODEX_HOME=str(home / ".codex"), CLAUDE_CONFIG_DIR=str(home / ".claude"),
                   CODEX_THREAD_ID="windows-script-smoke", PYTHONUTF8="1",
                   PYTHONDONTWRITEBYTECODE="1")
        # Use absolute executable paths in the harness. Application discovery sees
        # neither the build Python nor Node/npm/GitHub CLI from the hosted image.
        process_only = home / "process-only toolchain"
        process_only.mkdir()
        env["PATH"] = str(process_only) + ";" + str(Path(os.environ["WINDIR"]) / "System32")
        for name in ("APPDATA", "LOCALAPPDATA", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
            Path(env[name]).mkdir(parents=True, exist_ok=True)
        return env

    def ps(self, shell: Path, source: str, env: dict[str, str], *,
           expect_failure: bool = False, timeout: int = 240) -> subprocess.CompletedProcess[str]:
        prelude = ("$ErrorActionPreference = 'Stop'; "
                   "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); "
                   "$OutputEncoding = [Console]::OutputEncoding; ")
        result = subprocess.run([str(shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                                 prelude + source], env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        if expect_failure == (result.returncode == 0):
            raise AssertionError({"shell": str(shell), "expected_failure": expect_failure,
                                  "returncode": result.returncode,
                                  "stdout": result.stdout[-6000:], "stderr": result.stderr[-6000:]})
        return result

    def ps_json(self, shell: Path, source: str, env: dict[str, str]) -> object:
        result = self.ps(shell, source, env)
        rows = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
        if len(rows) != 1:
            raise AssertionError(f"Expected one structured result: {result.stdout[-6000:]} {result.stderr[-1500:]}")
        return json.loads(rows[0])

    def emit(self, expression: str) -> str:
        return f"[Console]::WriteLine({quote(MARKER)} + (ConvertTo-Json -Depth 30 -Compress ({expression})))"

    def install_command(self, root: Path, *, python: Path | None = None,
                        manifest: Path | None = None, bootstrap: Path | None = None) -> str:
        selected = manifest or self.manifest
        command = (f"& {quote(bootstrap or self.bootstrap)} -ManifestPath {quote(selected)} "
                   f"-ManifestSha256 {quote(digest(selected))} -InstallRoot {quote(root)} -NoLaunch")
        return command + (f" -PythonPath {quote(python)} -NoRuntimeDownload" if python else " -PrivateRuntime")

    def install(self, shell: Path, root: Path, env: dict[str, str], *, python: Path | None = None,
                shadow: bool = False) -> dict[str, object]:
        setup = ""
        if shadow:
            setup = ("function global:Invoke-UserAgentBios { 'user-alias-preserved' }; "
                     "Set-Alias -Name agent-bios -Value Invoke-UserAgentBios -Scope Global; ")
        source = setup + "$beforePath = $env:PATH; $beforePreference = $ErrorActionPreference; "
        source += self.install_command(root, python=python) + "; "
        source += ("if ($ErrorActionPreference -cne $beforePreference) { throw 'bootstrap changed caller preferences' }; "
                   "foreach ($entry in $beforePath.Split(';')) { "
                   "if ($entry -and $env:PATH.Split(';') -notcontains $entry) { throw 'lost process PATH entry' } }; ")
        if shadow:
            source += ("if ((agent-bios) -cne 'user-alias-preserved' -or "
                       "(Get-Command agent-bios).CommandType -ne 'Alias') { throw 'user alias replaced' }; ")
        else:
            source += ("$resolved = Get-Command agent-bios -ErrorAction Stop; "
                       f"if ($resolved.Source -ine {quote(root / 'bin/agent-bios.ps1')}) {{ throw 'bare command did not resolve installed wrapper' }}; ")
        source += self.emit("@{ path=$env:PATH; shell=$PSVersionTable.PSVersion.ToString() }")
        report = self.ps_json(shell, source, env)
        binding = json.loads((root / "deployment.json").read_text(encoding="utf-8"))
        assert binding["owner"] == "agent-bios-windows-script", binding
        assert binding["version"] == self.release["version"], binding
        integration = json.loads((root / "platform.json").read_text(encoding="utf-8"))
        assert integration["shortcuts"]
        for path, sha256 in integration["shortcuts"].items():
            shortcut = Path(path)
            assert shortcut.is_relative_to(Path(env["APPDATA"]))
            assert digest(shortcut) == sha256
        self.checked("bootstrap installs and returns to the same shell", shell=report["shell"],
                     runtime="external" if python else "private", shadow_preserved=shadow)
        return binding

    def cli(self, shell: Path, root: Path, env: dict[str, str], *args: str,
            as_json: bool = True, input_text: str | None = None) -> object:
        prefix = ""
        pipeline = ""
        if input_text is not None:
            # PowerShell's native pipeline uses OutputEncoding, set explicitly in ps().
            prefix = f"$payload = {quote(input_text)}; "
            pipeline = "$payload | "
        command = f"{pipeline}& {quote(root / 'bin/agent-bios.ps1')} " + " ".join(quote(arg) for arg in args)
        source = prefix + f"$lines = @({command}); if ($LASTEXITCODE -ne 0) {{ throw ('agent-bios exit ' + $LASTEXITCODE) }}; "
        source += "$result = $lines -join [Environment]::NewLine; "
        if as_json:
            source += "$result = $result | ConvertFrom-Json; "
        return self.ps_json(shell, source + self.emit("$result"), env)

    def raw_python(self, binding: dict[str, object], env: dict[str, str], script: Path,
                   *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        package = Path(binding["application_root"])
        argv = [binding["python"]["path"], "-I", "-X", "utf8", str(package / "compose/runtime_entry.py"),
                "--dependencies", binding["dependencies_root"], "--script", str(script), *args]
        child_env = {**env, "AGENT_BIOS_WINDOWS_BINDING": str(Path(binding["commands_root"]).parent / "deployment.json")}
        result = subprocess.run(argv, env=child_env, input=input_text, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=180)
        if result.returncode:
            raise AssertionError({"argv": argv, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
        return result

    def bridge(self, binding: dict[str, object], env: dict[str, str], *args: str,
               input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        helper = Path(env["HOME"]) / ".agents/skills/agent-bios/scripts/bridge.py"
        # A real app helper does not inherit the wrapper's process-only exports.
        # Prove that its retained configuration supplies child dependency bindings.
        child_env = {key: value for key, value in env.items() if key not in {
            "AGENT_BIOS_WINDOWS_BINDING", "AGENT_BIOS_PYTHON_ENTRY", "AGENT_BIOS_PYTHON_DEPS"}}
        argv = [binding["python"]["path"], "-I", str(helper), *args]
        result = subprocess.run(argv, env=child_env, input=input_text, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=180)
        if result.returncode:
            raise AssertionError({"argv": argv, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
        return result

    def product(self, shell: Path, root: Path, env: dict[str, str], binding: dict[str, object]) -> dict[str, object]:
        home = Path(env["HOME"])
        project = home / "프로젝트 공백"
        project.mkdir()
        protected = {}
        for path in (home / ".codex/AGENTS.md", home / ".claude/CLAUDE.md", project / "AGENTS.md"):
            path.write_text("# Local instructions\nPreserve the user's selected environment.\n", encoding="utf-8")
            protected[str(path)] = digest(path)
        assert self.cli(shell, root, env, "install", "--non-interactive")["stored"]
        assert self.cli(shell, root, env, "verify")["stored"]
        assert self.cli(shell, root, env, "--version", as_json=False).strip() == self.release["version"]
        start = self.cli(shell, root, env, "setup", "start", "--language", "ko")
        assert start["cli_argv"][0].casefold() == str(binding["python"]["path"]).casefold()
        dependencies = self.cli(shell, root, env, "setup", "inspect", "--language", "ko")["dependencies"]
        learning = next(row for row in dependencies if row["id"] == "jsonschema")
        assert learning["status"] == "available", learning
        assert not any(row["id"] == "bash" for row in dependencies)
        self.checked("real private install, version, verify and setup use the bound Python", shell=shell.name)

        capture = self.cli(shell, root, env, "import", "capture", "--project", str(project),
                           "--path", str(project / "AGENTS.md"), "--json")
        evidence = capture["sources"][0]
        payload = {"operation": "import", "capture_id": capture["capture_id"], "candidates": [{
            "source_id": evidence["source_id"], "title": "Worker environment continuity",
            "body": "Preserve the user's selected environment.", "surface": "relevant", "kind": "guide",
            "reason": "Applies when adapting this project's environment.",
            "evidence": [{"start": 1, "end": evidence["line_count"]}]}]}
        plan = self.cli(shell, root, env, "import", "plan", "--json", input_text=json.dumps(payload))
        self.cli(shell, root, env, "import", "apply", plan["plan_id"],
                 "--expected-revision", plan["expected_revision"], "--json")
        self.checked("source capture and revision-checked import run against isolated private roots", shell=shell.name)

        snapshots = []
        for host in ("claude", "codex"):
            snapshot = self.cli(shell, root, env, "instructions", "snapshot", "--host", host, "--json")
            saved = Path(snapshot["path"])
            assert "korean-writing" in (saved / "router/relevant.md").read_text(encoding="utf-8")
            snapshots.append({"path": str(saved), "inventory": inventory(saved)})
        assert self.cli(shell, root, env, "app", "register", "--json")["registered"]
        status = json.loads(self.bridge(binding, env, "session", "status", "--json").stdout)
        assert status["enabled"] is False
        preview = json.loads(self.bridge(binding, env, "session", "preview", "--json").stdout)
        used = json.loads(self.bridge(binding, env, "session", "use", "--expected-content-ref",
                                     preview["content_ref"], "--json").stdout)
        assert used["enabled"] and used["instruction_text"]
        assert used["delivery"] == "returned-as-context"
        self.bridge(binding, env, "learn", "--host", "codex", "--no-upload",
                    input_text=json.dumps({"lesson": "Preserve a worker's selected environment during updates.",
                                           "domain": "unclassified", "supporting_sessions": ["codex:abcd1234"]}))
        events = Path(env["AGENT_BIOS_INSTRUCTIONS_DIR"]) / "learnings/codex/events.jsonl"
        assert len(events.read_text(encoding="utf-8").splitlines()) == 1
        self.checked("both host snapshots, app bridge children and learning capture use runtime binding", shell=shell.name)

        probe = home / "studio_probe.py"
        probe.write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\n"
                         "from instructions_ui_runtime import activate_ui_runtime\n"
                         "activate_ui_runtime(Path(sys.argv[2]))\n"
                         "from instructions_ui import InstructionsStudio\n"
                         "from jsonschema import Draft202012Validator\n"
                         "Draft202012Validator.check_schema({'type': 'object'})\n"
                         "print('studio-and-validator-ok')\n", encoding="utf-8")
        package = Path(binding["application_root"])
        assert "studio-and-validator-ok" in self.raw_python(binding, env, probe, str(package / "compose"), str(package)).stdout
        for name, expected in protected.items():
            assert digest(Path(name)) == expected
        self.checked("Studio and ABI-specific validation dependencies import under isolated runtime", shell=shell.name)
        return {"protected": protected, "snapshots": snapshots, "events": str(events), "events_sha256": digest(events)}

    def preserve(self, evidence: dict[str, object]) -> None:
        for name, expected in evidence["protected"].items():
            assert digest(Path(name)) == expected
        for snapshot in evidence["snapshots"]:
            assert inventory(Path(snapshot["path"])) == snapshot["inventory"]
        assert digest(Path(evidence["events"])) == evidence["events_sha256"]

    def fixture(self, name: str) -> tuple[Path, dict[str, object]]:
        folder = self.scratch / "negative-assets" / name
        folder.mkdir(parents=True)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8-sig"))
        for key, filename in (("archive", "application.zip"), ("runtime", "runtime.zip")):
            shutil.copy2(self.assets / filename, folder / filename)
            manifest[key]["url"] = filename
        return folder, manifest

    def write_manifest(self, folder: Path, manifest: dict[str, object]) -> Path:
        path = folder / "release.json"
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return path

    def rejected(self, shell: Path, command: str, env: dict[str, str], reason: str) -> None:
        result = self.ps(shell, command, env, expect_failure=True)
        assert reason.casefold() in (result.stdout + result.stderr).casefold(), {
            "expected_reason": reason, "stdout": result.stdout[-3000:], "stderr": result.stderr[-3000:]}

    def negatives(self, shell: Path) -> None:
        root = self.scratch / "negative installs"
        root.mkdir()
        env = self.env(root)

        bad_hash = self.install_command(root / "wrong manifest hash").replace(digest(self.manifest), "0" * 64)
        self.rejected(shell, bad_hash, env, "SHA256")
        assert not (root / "wrong manifest hash/deployment.json").exists()
        self.checked("incorrect caller-pinned manifest hash refuses installation")

        for key in ("archive", "runtime"):
            folder, manifest = self.fixture("wrong-" + key + "-hash")
            manifest[key]["sha256"] = "0" * 64
            path = self.write_manifest(folder, manifest)
            target = root / ("wrong " + key)
            self.rejected(shell, self.install_command(target, manifest=path), env, "SHA256")
            assert not (target / "deployment.json").exists()
            self.checked("incorrect " + key + " hash refuses execution and active binding")

        folder, manifest = self.fixture("wrong-signer")
        manifest["script_signer_thumbprints"] = ["0" * 40]
        path = self.write_manifest(folder, manifest)
        self.rejected(shell, self.install_command(root / "wrong signer", manifest=path), env, "unapproved script signer")
        assert not (root / "wrong signer/deployment.json").exists()
        self.checked("unknown script signer cannot expand bootstrap trust")

        folder, manifest = self.fixture("zip-traversal")
        archive = folder / "application.zip"
        with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("../escaped-by-zip.txt", "must not extract")
        manifest["archive"].update(sha256=digest(archive), size=archive.stat().st_size)
        path = self.write_manifest(folder, manifest)
        self.rejected(shell, self.install_command(root / "unsafe zip", manifest=path), env, "unsafe")
        assert not list(root.rglob("escaped-by-zip.txt"))
        assert not (root / "unsafe zip/deployment.json").exists()
        self.checked("correctly hashed ZIP with a traversal member is rejected")

        folder = self.scratch / "tampered-bootstrap"
        folder.mkdir()
        tampered = folder / "install.ps1"
        tampered.write_bytes(self.bootstrap.read_bytes() + b"\n# tampered signed bytes\n")
        self.rejected(shell, self.install_command(root / "tampered script", bootstrap=tampered), env, "signature")
        assert not (root / "tampered script/deployment.json").exists()
        self.checked("modified bootstrap fails its required Authenticode verification")

        occupied = root / "foreign destination"
        occupied.mkdir()
        foreign = occupied / "keep.txt"
        foreign.write_text("not owned by agent-bios", encoding="utf-8")
        before = inventory(occupied)
        self.rejected(shell, self.install_command(occupied), env, "unowned")
        assert inventory(occupied) == before
        self.checked("occupied unowned destination remains unchanged")

        invalid_python = root / "not-approved-python.exe"
        invalid_python.write_text("This is a non-executable signature rejection fixture.", encoding="utf-8")
        self.rejected(shell, self.install_command(root / "unapproved runtime", python=invalid_python), env, "signature")
        assert not (root / "unapproved runtime/deployment.json").exists()
        self.checked("explicit unapproved Python is rejected without automatic fallback")

        folder, manifest = self.fixture("tampered-wrapper")
        archive = folder / "application.zip"
        rewritten = folder / "rewritten.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(rewritten, "w", zipfile.ZIP_DEFLATED) as target:
            for member in source.infolist():
                data = source.read(member)
                if member.filename == "commands/agent-bios.ps1":
                    data += b"\n# changed after release signing\n"
                target.writestr(member, data)
        rewritten.replace(archive)
        manifest["archive"].update(sha256=digest(archive), size=archive.stat().st_size)
        path = self.write_manifest(folder, manifest)
        self.rejected(shell, self.install_command(root / "tampered wrapper", manifest=path), env, "signature")
        assert not (root / "tampered wrapper/deployment.json").exists()
        self.checked("valid archive digest does not excuse a command's invalid signature")

        inno = root / "existing Inno installation"
        inno.mkdir()
        (inno / "unins000.exe").write_text("Unexecuted owned-installation fixture.", encoding="utf-8")
        before = inventory(inno)
        self.rejected(shell, self.install_command(inno), env, "Inno")
        assert inventory(inno) == before
        self.checked("existing Inno ownership is refused without overwriting files")

    def lifecycle(self, shell: Path, index: int) -> None:
        scope = self.scratch / f"shell-{index} 한글 공백"
        scope.mkdir()
        env = self.env(scope)
        root = scope / "managed install"
        binding = self.install(shell, root, env, shadow=index == 1)
        runtime = Path(binding["python"]["path"])
        assert binding["python"]["managed_root"]
        assert runtime.is_file()
        pth_files = list(runtime.parent.glob("python*._pth"))
        assert pth_files, "This branch must use the real embeddable isolated distribution"
        with zipfile.ZipFile(self.assets / "runtime.zip") as archive:
            for pth in pth_files:
                assert pth.read_bytes() == archive.read(pth.name), "Do not weaken upstream _pth isolation"
        evidence = self.product(shell, root, env, binding)
        fresh = {key: value for key, value in env.items() if key not in {
            "AGENT_BIOS_STATE_DIR", "AGENT_BIOS_INSTRUCTIONS_DIR", "AGENT_BIOS_CORPUS_DIR",
            "CODEX_HOME", "CLAUDE_CONFIG_DIR"}}
        assert self.cli(shell, root, fresh, "verify")["stored"]
        observed = self.cli(shell, root, fresh, "status")
        assert Path(observed["package_root"]).is_relative_to(Path(env["AGENT_BIOS_STATE_DIR"]))
        source = (f"& {quote(root / 'bin/agent-bios.ps1')} status | Out-Null; "
                  "if ($LASTEXITCODE -ne 0) { throw 'fresh-shell status failed' }; "
                  "if (Test-Path Env:AGENT_BIOS_STATE_DIR) { throw 'saved roots leaked into caller environment' }; "
                  "if (Test-Path Env:AGENT_BIOS_INSTRUCTIONS_DIR) { throw 'saved user root leaked into caller environment' }; ")
        self.ps(shell, source, fresh)
        self.checked("fresh shell restores saved custom roots for execution without changing caller environment", shell=shell.name)
        binding = self.install(shell, root, env)
        assert self.cli(shell, root, env, "verify")["stored"]
        self.preserve(evidence)
        self.checked("same-version repair retains source edits, native files and prior snapshots", shell=shell.name)

        # Move to an independently located approved interpreter with identical
        # upstream bytes. This detects launch receipts bound to sys.executable.
        external = scope / "approved external Python B"
        shutil.copytree(Path(binding["python"]["managed_root"]), external)
        python_b = external / runtime.name
        external_before = inventory(external)
        before_identity = binding["python"]["path"]
        binding = self.install(shell, root, env, python=python_b)
        assert str(binding["python"]["path"]).casefold() != str(before_identity).casefold()
        assert binding["python"]["managed_root"] is None
        assert self.cli(shell, root, env, "verify")["stored"]
        assert self.cli(shell, root, env, "app", "status", "--json")["registered"]
        bridge_status = json.loads(self.bridge(binding, env, "session", "status", "--json").stdout)
        assert bridge_status["enabled"]
        assert inventory(external) == external_before
        self.preserve(evidence)
        self.checked("interpreter A to B update preserves ownership, bridge and private state", shell=shell.name)

        platform_receipt = json.loads((root / "platform.json").read_text(encoding="utf-8"))
        removed = self.cli(shell, root, env, "uninstall")
        assert not (root / "bin/agent-bios.ps1").exists()
        assert not (root / "bin/agent-launch.ps1").exists()
        assert runtime.exists(), "Historical runtime was removed despite retained bridge/snapshot references"
        assert removed["retained_release_paths"]
        assert removed["retained_runtime_paths"]
        assert inventory(external) == external_before
        user_path = self.ps_json(shell, self.emit("[Environment]::GetEnvironmentVariable('Path', 'User')"), env)
        assert str(root / "bin") not in (user_path or "").split(";")
        assert all(not Path(path).exists() for path in platform_receipt["shortcuts"])
        self.preserve(evidence)
        self.checked("uninstall retains authoring, session pins, external Python and referenced old runtimes", shell=shell.name)

    def existing(self, shell: Path) -> None:
        scope = self.scratch / "preinstalled Python case"
        scope.mkdir()
        env = self.env(scope)
        root = scope / "install"
        python_before = digest(self.existing_python)
        site = self.existing_python.parent / "Lib/site-packages"
        site_before = inventory(site) if site.is_dir() else {}
        binding = self.install(shell, root, env, python=self.existing_python)
        assert Path(binding["python"]["path"]).resolve() == self.existing_python
        assert binding["python"]["managed_root"] is None
        assert self.cli(shell, root, env, "install", "--non-interactive")["stored"]
        assert self.cli(shell, root, env, "verify")["stored"]
        self.cli(shell, root, env, "uninstall")
        assert digest(self.existing_python) == python_before
        assert (inventory(site) if site.is_dir() else {}) == site_before
        self.checked("preinstalled approved Python is reused without runtime download or global package mutation")

    def https_runtime(self, shell: Path) -> None:
        folder, manifest = self.fixture("https-runtime")
        url = manifest["runtime"]["source_url"]
        assert url.startswith("https://www.python.org/ftp/python/")
        manifest["runtime"]["url"] = url
        path = self.write_manifest(folder, manifest)
        # Remove the local runtime: success must come through the normal HTTPS
        # acquisition code, using the same approved digest and publisher policy.
        (folder / "runtime.zip").unlink()
        scope = self.scratch / "https runtime install"
        scope.mkdir()
        env = self.env(scope)
        root = scope / "application"
        self.ps(shell, self.install_command(root, manifest=path), env)
        binding = json.loads((root / "deployment.json").read_text(encoding="utf-8"))
        assert binding["python"]["managed_root"]
        assert self.cli(shell, root, env, "install", "--non-interactive")["stored"]
        assert self.cli(shell, root, env, "verify")["stored"]
        self.cli(shell, root, env, "uninstall")
        self.checked("real HTTPS official runtime acquisition verifies hashes and publishers before deployment")

    def run(self) -> None:
        with zipfile.ZipFile(self.assets / "application.zip") as bundle:
            assert not any(name.lower().endswith(".exe") for name in bundle.namelist())
            assert "package/compose/runtime_entry.py" in bundle.namelist()
            assert "commands/agent-bios.ps1" in bundle.namelist()
        self.checked("application ZIP contains scripts and dependencies without custom EXEs")
        for index, shell in enumerate(self.shells):
            actual = self.ps_json(shell, self.emit("$PSVersionTable.PSVersion.Major"),
                                  {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"})
            assert actual == (5 if index == 0 else 7), actual
            self.lifecycle(shell, index)
        self.existing(self.shells[1])
        self.negatives(self.shells[0])
        self.https_runtime(self.shells[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=SOURCE / "dist/windows-script")
    parser.add_argument("--python-existing", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run on an ephemeral Windows GitHub Actions runner; this suite owns persistent test PATH entries.")
    import winreg
    assets = args.assets.resolve(strict=True)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
        try:
            original_path, original_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            original_path, original_type = None, winreg.REG_EXPAND_SZ
    report: dict[str, object] = {"platform": sys.platform, "passed": False, "checks": []}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="agent-bios 스크립트 검증 ") as temporary:
            # Resolve the scratch root once: the runner's TEMP may be an 8.3 short
            # path, and the deployment owner records resolved long paths.
            driver = Driver(assets, Path(temporary).resolve(), args.python_existing)
            report["checks"] = driver.checks
            driver.run()
            report["passed"] = True
    except BaseException:
        report["failure"] = traceback.format_exc()
        raise
    finally:
        # This is an ephemeral CI account. Restore its exact prior registry value,
        # even when a negative control interrupts a test before normal removal.
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
            if original_path is None:
                try:
                    winreg.DeleteValue(key, "Path")
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, "Path", 0, original_type, original_path)
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (assets / "script-smoke-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
