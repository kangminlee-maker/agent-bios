#!/usr/bin/env python3
"""Build or verify the offline UI wheel bundle; only --build uses the network."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compose"))
from instructions_ui_runtime import UiRuntimeError, _bundle_id, runtime_inventory, wheel_metadata


def root_requirement(repo: Path = ROOT) -> str:
    source = (repo / "launch/provision-venv.sh").read_text(encoding="utf-8")
    pins = re.findall(r"^TEXTUAL_PIN=['\"](textual==[0-9][A-Za-z0-9_.!+]*)['\"]$", source, re.MULTILINE)
    if len(pins) != 1:
        raise UiRuntimeError("provisioner must declare exactly one literal TEXTUAL_PIN")
    return pins[0]


def smoke(repo: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="agent-bios-ui-check-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir()
        code = f"""import asyncio, importlib.resources, json, socket, sys
def forbidden(*args, **kwargs):
    raise RuntimeError('network access is forbidden in the UI smoke test')
socket.create_connection = forbidden
socket.socket.connect = forbidden
sys.path.insert(0, {str(ROOT / 'compose')!r})
from pathlib import Path
from instructions_ui_runtime import activate_ui_runtime
root = activate_ui_runtime(Path({str(repo)!r}))
from textual.app import App, ComposeResult
from textual.widgets import MarkdownViewer, TextArea, SelectionList, DirectoryTree, ProgressBar, Static
from markdown_it import MarkdownIt
from rich.syntax import Syntax
assert '<a href=' in MarkdownIt('commonmark', {{'linkify': True}}).enable('linkify').render('https://example.test')
assert importlib.resources.files('textual').joinpath('app.py').is_file()
class Demo(App):
    def compose(self) -> ComposeResult:
        yield Static('offline bundled UI')
async def run():
    app = Demo()
    async with app.run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        assert '<svg' in app.export_screenshot()
asyncio.run(run())
print(json.dumps({{'runtime_path': str(root)}}))
"""
        env = dict(os.environ, HOME=str(home), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            env.pop(name, None)
        result = subprocess.run([sys.executable, "-S", "-c", code], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise UiRuntimeError("clean offline UI smoke failed: " + result.stderr.strip())
        receipt = json.loads(result.stdout)
        if Path(receipt["runtime_path"]).exists():
            raise UiRuntimeError("UI process did not clean its temporary runtime")
        if list(home.rglob("*")):
            raise UiRuntimeError("UI smoke wrote into its HOME")
        return receipt


def check(repo: Path = ROOT, *, run_smoke: bool = True, check_pin: bool = True) -> dict:
    inventory = runtime_inventory(repo)
    if inventory["status"] != "available":
        raise UiRuntimeError("; ".join(inventory["issues"]))
    if check_pin and inventory["root_requirement"] != root_requirement(repo):
        raise UiRuntimeError("UI bundle root requirement differs from provisioner TEXTUAL_PIN")
    if run_smoke:
        smoke(repo)
    return {key: inventory[key] for key in ("bundle_id", "root_requirement", "package_count", "size_bytes", "expanded_bytes", "license_file_count", "pure_python")}


def build(*, refresh: bool = False, from_wheels: Path | None = None) -> dict:
    requirement = root_requirement()
    target = ROOT / "compose/ui_runtime"
    previous = runtime_inventory(ROOT)
    with tempfile.TemporaryDirectory(prefix="agent-bios-ui-build-") as temporary:
        temporary = Path(temporary)
        wheels = temporary / "wheels"
        wheels.mkdir()
        if from_wheels is not None:
            for source in from_wheels.glob("*.whl"):
                shutil.copy2(source, wheels / source.name)
        else:
            development = temporary / "development"
            venv.EnvBuilder(with_pip=True).create(development)
            command = [str(development / "bin/python"), "-m", "pip", "--isolated", "--no-cache-dir", "download",
                       "--index-url", "https://pypi.org/simple", "--only-binary=:all:", "--python-version", "3.11",
                       "--implementation", "py", "--abi", "none", "--platform", "any", "--dest", str(wheels)]
            locked = previous["status"] == "available" and previous["root_requirement"] == requirement and not refresh
            if locked:
                command.extend(["--no-deps", *[f"{row['name']}=={row['version']}" for row in previous["packages"]]])
            else:
                command.append(requirement)
            subprocess.run(command, check=True)
        packages = []
        for path in sorted(wheels.glob("*.whl")):
            row = wheel_metadata(path.name, path.read_bytes())
            request = urllib.request.Request(f"https://pypi.org/pypi/{row['name']}/{row['version']}/json",
                                             headers={"User-Agent": "agent-bios-ui-bundle-builder"})
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.load(response)
            published = next((entry for entry in release["urls"] if entry["filename"] == path.name), None)
            if published is None or published["digests"]["sha256"] != row["sha256"]:
                raise UiRuntimeError(f"download does not match the official PyPI artifact: {path.name}")
            packages.append(row)
        packages.sort(key=lambda row: row["name"])
        manifest = {"schema_version": 1, "source": "pypi", "python_requirement": ">=3.11",
                    "root_requirement": requirement, "packages": packages}
        manifest["bundle_id"] = _bundle_id(manifest)
        if previous["status"] == "available" and previous["root_requirement"] == requirement and not refresh \
                and manifest["bundle_id"] != previous["bundle_id"]:
            raise UiRuntimeError("reproduced UI bundle differs from its manifest; use --refresh for a deliberate dependency update")
        candidate = temporary / "candidate"
        destination = candidate / "compose/ui_runtime"
        destination.parent.mkdir(parents=True)
        shutil.copytree(wheels, destination)
        (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = check(candidate, check_pin=False)
        if target.is_symlink():
            raise UiRuntimeError("refusing to replace a symlinked UI bundle")
        target.mkdir(parents=True, exist_ok=True)
        for path in target.iterdir():
            if not path.is_file() or path.is_symlink():
                raise UiRuntimeError(f"unexpected UI bundle path: {path}")
        for path in destination.iterdir():
            shutil.copy2(path, target / path.name)
        expected = {path.name for path in destination.iterdir()}
        for path in target.iterdir():
            if path.name not in expected:
                path.unlink()
        return result


def self_test() -> dict:
    check()
    controls = []
    for name in ("missing wheel", "corrupted wheel", "manifest fingerprint", "missing license", "unsafe wheel path", "impure wheel"):
        with tempfile.TemporaryDirectory(prefix="agent-bios-ui-control-") as temporary:
            repo = Path(temporary)
            bundle = repo / "compose/ui_runtime"
            bundle.parent.mkdir()
            shutil.copytree(ROOT / "compose/ui_runtime", bundle)
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            row = manifest["packages"][0]
            wheel = bundle / row["filename"]
            if name == "missing wheel":
                wheel.unlink()
            elif name == "corrupted wheel":
                data = bytearray(wheel.read_bytes()); data[len(data) // 2] ^= 1; wheel.write_bytes(data)
            elif name == "manifest fingerprint":
                manifest["root_requirement"] = "textual==0.0.0"
                manifest_path.write_text(json.dumps(manifest))
            else:
                replacement = wheel.with_suffix(".tmp")
                with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(replacement, "w", zipfile.ZIP_DEFLATED) as target:
                    for member in source.infolist():
                        if name == "missing license" and member.filename in row["license_files"]:
                            continue
                        body = source.read(member)
                        if name == "impure wheel" and member.filename.endswith(".dist-info/WHEEL"):
                            body = body.replace(b"Root-Is-Purelib: true", b"Root-Is-Purelib: false")
                        target.writestr(member, body)
                    if name == "unsafe wheel path":
                        target.writestr("../escaped.py", "raise RuntimeError('must not extract')")
                replacement.replace(wheel)
                row["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
                row["size_bytes"] = wheel.stat().st_size
                manifest["bundle_id"] = _bundle_id(manifest)
                manifest_path.write_text(json.dumps(manifest))
            inventory = runtime_inventory(repo)
            if inventory["status"] != "unavailable":
                raise UiRuntimeError("UI bundle negative control survived: " + name)
            expected = {"missing wheel": "missing", "corrupted wheel": "SHA256", "manifest fingerprint": "fingerprint",
                        "missing license": "license", "unsafe wheel path": "unsafe", "impure wheel": "not pure"}[name]
            if expected not in " ".join(inventory["issues"]):
                raise UiRuntimeError("UI bundle control failed for an unrelated reason: " + name + ": " + str(inventory["issues"]))
            controls.append(name)
    with tempfile.TemporaryDirectory(prefix="agent-bios-ui-pin-control-") as temporary:
        repo = Path(temporary)
        (repo / "compose").mkdir()
        (repo / "launch").mkdir()
        shutil.copytree(ROOT / "compose/ui_runtime", repo / "compose/ui_runtime")
        (repo / "launch/provision-venv.sh").write_text('TEXTUAL_PIN="textual==0.0.0"\n')
        try:
            check(repo, run_smoke=False)
        except UiRuntimeError as exc:
            if "TEXTUAL_PIN" not in str(exc):
                raise UiRuntimeError("pin control failed for an unrelated reason") from exc
        else:
            raise UiRuntimeError("UI bundle pin drift control survived")
        controls.append("root pin drift")
    return {"positive": "clean offline import, rendering and cleanup", "negative_controls": controls}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--build", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--self-test", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="resolve a deliberate new transitive graph when building")
    parser.add_argument("--from-wheels", type=Path, help="build from previously downloaded wheels; verify official PyPI hashes")
    args = parser.parse_args()
    if (args.refresh or args.from_wheels) and not args.build:
        parser.error("--refresh and --from-wheels require --build")
    try:
        result = build(refresh=args.refresh, from_wheels=args.from_wheels) if args.build else self_test() if args.self_test else check()
        print(json.dumps(result, indent=2))
        return 0
    except (UiRuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"UI runtime: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
