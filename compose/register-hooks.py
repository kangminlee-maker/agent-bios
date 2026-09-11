#!/usr/bin/env python3
"""Legacy utility: merge canonical hook registrations into Claude settings.

The private installer registers no global host hooks. Explicit native session
activation is shared by Claude and Codex through corpus_catalog/corpus_session.
This compatibility utility retains the legacy Claude settings.json ownership
and merge behavior by calling the assembler's merge_settings implementation.

Usage: register-hooks.py <repo> <claude-dir>
Exit 0 on success; non-zero with a message if the legacy merge cannot run.
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
