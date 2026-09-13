#!/usr/bin/env python3
"""Resolve the confirmed private release for an explicitly registered app skill."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    expected = {"SKILL.md", "agents/openai.yaml", "scripts/bridge.py",
                "scripts/corpus_transaction.py", "bridge.json"}
    try:
        paths = list(root.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise RuntimeError("registered bridge contains a symlink")
        files = {path.relative_to(root).as_posix(): path.read_bytes() for path in paths if path.is_file()}
        if set(files) != expected:
            raise RuntimeError("registered bridge member inventory changed")
        digest = hashlib.sha256()
        for relative, data in sorted(files.items()):
            digest.update(relative.encode("utf-8") + b"\0" + data + b"\0")
        if digest.hexdigest() != root.name:
            raise RuntimeError("registered bridge content changed")
        config = json.loads(files["bridge.json"])
        if config.get("schema_version") != 1:
            raise RuntimeError("registered bridge configuration is unsupported")
        for key in ("home", "state_root", "user_root", "discovery_path"):
            if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
                raise RuntimeError("registered bridge needs absolute private roots")
        sys.dont_write_bytecode = True
        from corpus_transaction import confirmed_release, guard_pending, reject_symlink_ancestors
        state = Path(config["state_root"])
        reject_symlink_ancestors(state)
        reject_symlink_ancestors(Path(config["user_root"]))
        guard_pending(state)
        release = confirmed_release(state)
        reject_symlink_ancestors(release)
        env = dict(os.environ)
        env.update({"HOME": config["home"], "AGENT_BIOS_STATE_DIR": config["state_root"],
                    "AGENT_BIOS_CORPUS_DIR": config["user_root"],
                    "AGENT_BIOS_PACKAGE_ROOT": str(release), "AGENT_BIOS_PRIVATE_CORPUS": "1",
                    "AGENT_BIOS_LEGACY_INSTALL": "0",
                    "PYTHONDONTWRITEBYTECODE": "1"})
        if "launch_venv" in config:
            value = config["launch_venv"]
            if not isinstance(value, str) or (value and not Path(value).is_absolute()):
                raise RuntimeError("registered bridge has an invalid managed runtime path")
            env["AGENT_LAUNCH_VENV"] = value
        args = sys.argv[1:]
        command = args[0] if args else "session"
        tail = args[1:] if args else ["status", "--json"]
        if command == "bootstrap":
            print((release / "compose/bootstrap/SKILL.md").read_text(encoding="utf-8"), end="")
            return 0
        if command == "tui":
            argv = ["/bin/bash", str(release / "install.sh"), "corpus", *tail]
        elif command in {"setup", "corpus", "import", "learn"}:
            argv = ["/bin/bash", str(release / "install.sh"), command, *tail]
        elif command == "session":
            argv = [sys.executable, str(release / "compose/corpus_app.py"), "--repo", str(release),
                    "--state-dir", config["state_root"], "--user-dir", config["user_root"], "session", *tail]
        else:
            raise RuntimeError("bridge supports setup, session, corpus, import, learn, bootstrap and tui")
        os.execve(argv[0], argv, env)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"agent-bios app bridge: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
