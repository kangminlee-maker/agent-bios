"""Isolated native-home inputs for author-side legacy projection checks.

The native backend and adapter files are availability fixtures, not provider implementations. These
checks inspect routing/serialization and must never dispatch an actual model.
"""
import contextlib
import os
from pathlib import Path
import shutil


@contextlib.contextmanager
def launcher_environment(root, repo, *, backends=("claude", "codex"), isolate_home=True):
    """Supply offline availability; callers may omit or override backend fixtures."""
    root, repo = Path(root), Path(repo)
    home, codex, claude = root / "home", root / "codex", root / "claude"
    home.mkdir(parents=True)
    binaries = root / "bin"
    binaries.mkdir()
    for name in backends:
        if name not in {"claude", "codex"}:
            raise ValueError(f"unknown fixture backend: {name}")
        backend = binaries / name
        backend.write_text("#!/bin/sh\nexit 0\n")
        backend.chmod(0o755)
    shutil.copytree(repo / "codex/agents", codex / "agents")
    for directory, names in ((codex, ("codex-run", "codex-helm")), (claude, ("claude-run",))):
        (directory / "bin").mkdir(parents=True, exist_ok=True)
        for name in names:
            adapter = directory / "bin" / name
            adapter.write_text("#!/bin/sh\nexit 0\n")
            adapter.chmod(0o755)
    values = {"HOME": str(home), "CODEX_HOME": str(codex), "CLAUDE_CONFIG_DIR": str(claude),
              "AGENT_BIOS_PRIVATE_INSTRUCTIONS": "0", "AGENT_BIOS_STATE_DIR": str(root / "state"),
              "XDG_CACHE_HOME": str(root / "cache"),
              "PATH": os.pathsep.join(filter(None, (str(binaries), os.environ.get("PATH", os.defpath))))}
    if not isolate_home:
        values.pop("HOME")
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield values
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
