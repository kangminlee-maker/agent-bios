#!/usr/bin/env python3
"""Register the manifest's hooks in a deployed settings.json (full-install path).

The packaged path gets this for free: assemble.py composes the corpus and calls
merge_settings on the way out. A full install never runs the assembler, so the
hook files were deployed and nothing ever registered them — they sat on disk and
never fired. This runs the assembler's own merge so both paths register
identically, under the same name-based ownership rule.

Usage: register-hooks.py <repo> <claude-dir>
Exit 0 on success; non-zero (with a message) if the merge could not run, which
the installer reports as a note rather than failing the whole install.
"""
import importlib.util
import json
import pathlib
import sys


def load_assemble(repo):
    """Import assemble.py by path — compose/ is a flat toolbox, not a package."""
    spec = importlib.util.spec_from_file_location("assemble", repo / "compose" / "assemble.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: register-hooks.py <repo> <claude-dir>")
    repo, claude_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    manifest = json.loads((repo / "compose" / "domains.json").read_text(encoding="utf-8"))
    names = sorted(manifest.get("hooks", {}))
    if not names:
        sys.exit("register-hooks: manifest declares no hooks — refusing to rewrite settings")
    mod = load_assemble(repo)
    mod.merge_settings(claude_dir, names,
                       repo / "claude" / "settings.template.json",
                       owned_names=names)
    print(f"  hooks registered ({len(names)})")


if __name__ == "__main__":
    main()
