#!/usr/bin/env python3
"""Print the installation page's command for one platform, exactly as published.

The page, the README and this script all take the command from the same builder,
so a caller that runs what this prints is running what a user would paste.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def commands() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(
        "agent_bios_install_site_command", ROOT / "packages/windows/build-install-site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["repository"]["url"]
    repository = raw.removeprefix("git+").removesuffix(".git")
    owner, name = repository.split("/")[-2:]
    site = f"https://{owner.lower()}.github.io/{name}"
    config = json.loads((ROOT / "packages/windows/install-site.json").read_text(encoding="utf-8"))
    _, _, channel = module.release_identity(config, repository)
    return {"windows": module.install_command(site, channel),
            "posix": module.posix_install_command(site)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("windows", "posix"), default="windows")
    print(commands()[parser.parse_args().platform])


if __name__ == "__main__":
    main()
