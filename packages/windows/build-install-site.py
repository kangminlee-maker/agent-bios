#!/usr/bin/env python3
"""Promote an explicitly pinned, already published bootstrap to a fixed Pages URL.

The site contains distribution files only. It neither builds a new application
release nor follows GitHub's mutable latest-release selector.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
POSIX_BOOTSTRAP = ROOT / "packages/posix/install.sh"


def release_identity(config: dict, repository: str) -> tuple[str, str, str]:
    repository = repository.removeprefix("git+").removesuffix(".git")
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected a GitHub repository URL")
    tag = config.get("tag", "")
    if not re.fullmatch(r"windows-script-v\d+\.\d+\.\d+(?:-preview\.\d+)?", tag):
        raise ValueError("Expected an immutable Windows script release tag")
    if not re.fullmatch(r"[a-f0-9]{64}", config.get("bootstrap_sha256", "")):
        raise ValueError("Expected the published bootstrap SHA256")
    channel = "preview" if "-preview." in tag else "stable"
    return repository + "/releases/tag/" + tag, repository + "/releases/download/" + tag + "/install.ps1", channel


def install_command(site_url: str, channel: str) -> str:
    # Keep the URL safe inside a PowerShell literal and an HTML attribute.
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._/-]+)?", site_url):
        raise ValueError("Expected an HTTPS site URL without query, credentials or fragments")
    suffix = " -AcceptUnsignedPreview" if channel == "preview" else ""
    # The whole PowerShell program is one double-quoted argument, so the program
    # itself must contain no double quote: cmd.exe would end the argument there.
    program = ("$p = Join-Path $env:TEMP ([guid]::NewGuid().ToString('N') + '.ps1'); iwr "
               + "'" + site_url.rstrip("/") + "/install.ps1'"
               + " -UseBasicParsing -OutFile $p -ErrorAction Stop; & $p" + suffix)
    if '"' in program:
        raise ValueError("The quoted PowerShell program cannot contain a double quote")
    # -ExecutionPolicy Bypass applies to this process alone and leaves the machine's
    # policy untouched; without it the default Restricted policy refuses `& $p`.
    # Naming powershell.exe also lets the command start from cmd.exe or Win+R,
    # not only from an existing PowerShell prompt.
    return 'powershell -NoProfile -ExecutionPolicy Bypass -Command "' + program + '"'


def posix_install_command(site_url: str) -> str:
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._/-]+)?", site_url):
        raise ValueError("Expected an HTTPS site URL without query, credentials or fragments")
    return "curl -fsSL " + site_url.rstrip("/") + "/install.sh | bash"


def posix_bootstrap() -> bytes:
    """Serve the macOS and Linux bootstrap exactly as authored.

    Nothing is substituted. npm resolves the version and verifies the tarball, so
    a version pinned here would only add a promotion step whose omission serves an
    old release without saying so. The Windows route pins because its bootstrap
    carries the release assets' own digests; this one carries no digests at all.
    """
    text = POSIX_BOOTSTRAP.read_text(encoding="utf-8")
    if "agent-bios@latest" not in text:
        raise ValueError("The POSIX bootstrap must install the published latest release")
    return text.encode("utf-8")


def build(config: dict, repository: str, site_url: str, bootstrap: bytes, output: Path) -> dict:
    release_url, asset_url, channel = release_identity(config, repository)
    command = install_command(site_url, channel)
    digest = hashlib.sha256(bootstrap).hexdigest()
    if digest != config["bootstrap_sha256"]:
        raise ValueError("Published bootstrap SHA256 mismatch; refusing to promote it")
    posix = posix_bootstrap()
    posix_command = posix_install_command(site_url)
    metadata = {**config, "channel": channel, "release_url": release_url,
                "asset_url": asset_url, "install_url": site_url.rstrip("/") + "/install.ps1",
                "posix_install_url": site_url.rstrip("/") + "/install.sh",
                "posix_bootstrap_sha256": hashlib.sha256(posix).hexdigest()}
    notice = ("This is an unsigned preview. Run it only where your organization permits unsigned scripts."
              if channel == "preview" else "This is the signed stable distribution.")
    page = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Install agent-bios</title>
<style>body{{font:17px/1.6 system-ui,sans-serif;max-width:850px;margin:4rem auto;padding:0 1.5rem;color:#182b2b}}pre{{padding:1rem;background:#eef3f2;white-space:pre-wrap;overflow-wrap:anywhere}}a{{color:#006b60}}h2{{margin-top:2.5rem}}</style>
<main><h1>Install agent-bios</h1>
<h2>Windows</h2>
<p>Run this one line. It works from PowerShell, from the Command Prompt and from the Run box, and needs no manual download, npm or preinstalled Python.</p>
<pre><code>{html.escape(command)}</code></pre>
<p>{notice} It relaxes the execution policy for that one process and leaves the machine's policy unchanged.</p>
<p>Current release: <a href="{html.escape(release_url)}">{html.escape(config['tag'])}</a>.</p>
<h2>macOS and Linux</h2>
<p>Run this one line. It installs the published package, which needs Node.js 18+ and python3 3.11+ already present; it then tells you the command that deploys your work environment.</p>
<pre><code>{html.escape(posix_command)}</code></pre>
<p>Installs the current published release and prints the version it installed. It changes no shell profile and installs no package manager.</p>
<h2>What these commands trust</h2>
<p>Each convenience command trusts this HTTPS site for the initial script and does not pin or verify that script before execution. The Windows script then verifies every dependent download against digests pinned inside it. For a command that verifies the initial script too, use the version-specific release instructions.</p>
<p><a href="install.ps1">Windows script</a> · <a href="install.sh">macOS and Linux script</a> · <a href="bootstrap.json">Versions and SHA256</a></p>
</main></html>
'''
    # Never decode/re-encode the bootstrap: Authenticode signatures cover its bytes.
    output.mkdir(parents=True, exist_ok=True)
    (output / "install.ps1").write_bytes(bootstrap)
    (output / "install.sh").write_bytes(posix)
    (output / "bootstrap.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / ".nojekyll").touch()
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "packages/windows/install-site.json")
    parser.add_argument("--bootstrap", type=Path, help="Use a local copy of the pinned published asset")
    parser.add_argument("--site-url", help="Override the repository's default GitHub Pages URL")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/install-site")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    repository = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["repository"]["url"]
    _, asset_url, _ = release_identity(config, repository)
    owner, name = urlsplit(repository.removeprefix("git+")).path.strip("/").removesuffix(".git").split("/")
    site_url = args.site_url or f"https://{owner.lower()}.github.io/{name}"
    with tempfile.TemporaryDirectory(prefix="agent-bios-install-site-") as directory:
        bootstrap = args.bootstrap or Path(directory) / "install.ps1"
        if args.bootstrap is None:
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location",
                            "--proto", "=https", "--proto-redir", "=https", "--retry", "3",
                            "--connect-timeout", "20", "--max-time", "120",
                            "--output", str(bootstrap), asset_url], check=True)
        metadata = build(config, repository, site_url, bootstrap.read_bytes(), args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
