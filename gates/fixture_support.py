#!/usr/bin/env python3
"""Author-side fixtures for legacy projections and tracked-tree scenarios."""
from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


@contextlib.contextmanager
def patched_environment(values):
    """Restore each overridden variable, including its original absence."""
    before = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def legacy_host_environment(repo):
    """Give legacy gates their own host assets and explicit installation mode.

    Apply at the observation boundary, before importing the launcher, so its
    in-process readers and child processes see the same environment. Private
    instructions tests select their own mode; this fixture is not an umbrella default.
    """
    repo = Path(repo).resolve()
    from launcher_fixture_env import launcher_environment
    with tempfile.TemporaryDirectory(prefix="agent-bios-legacy-fixture-") as raw:
        root = Path(raw)
        with launcher_environment(root, repo, isolate_home=False), patched_environment({
            "AGENT_BIOS_LEGACY_INSTALL": "1",
            "AGENT_BIOS_PACKAGE_ROOT": repo,
            "AGENT_LAUNCH_CONFIG": repo / "launch" / "agent-launch.toml",
            "AGENT_LAUNCH_LANG": "en",
            "AGENT_BIOS_STATE_DIR": root / "state",
            "AGENT_BIOS_INSTRUCTIONS_DIR": root / "instructions",
            "XDG_CACHE_HOME": root / "cache",
            "AGENT_BIOS_INSTRUCTIONS_STATUS": root / "no-corpus-status.json",
            "AGENT_BIOS_SESSION_DISTILL_STATE": root / "no-distill-state.json",
            "AGENT_BIOS_UPDATE_CHECK_STATE": root / "no-update-check.json",
            "AGENT_BIOS_UPDATE_CHECK": "0",
        }):
            yield root


def copy_tracked_tree(source, destination):
    """Copy current bytes for the effective index's paths, without walking extras.

    The pre-commit hook supplies GIT_DIR/WORK_TREE/INDEX_FILE for its materialized
    index. Preserve that identity rather than opening a different index. Direct
    runs use the checkout's index. Symlinks travel as links, never as targets.
    """
    source, destination = Path(source).resolve(), Path(destination)
    top = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "--show-toplevel"], text=True).strip()
    if Path(top).resolve() != source:
        raise ValueError("tracked fixture source does not match the effective Git work tree")
    raw = subprocess.check_output(["git", "-C", str(source), "ls-files", "--cached", "-z"])
    paths = sorted(set(os.fsdecode(name) for name in raw.split(b"\0") if name))
    if not paths:
        raise ValueError("tracked fixture source has no tracked paths")
    destination.mkdir(parents=True, exist_ok=False)
    for name in paths:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe tracked fixture path: {name!r}")
        src, dst = source / relative, destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            dst.symlink_to(os.readlink(src))
        elif src.is_file():
            shutil.copy2(src, dst)
        else:
            raise ValueError(f"tracked fixture member is missing or not a file: {name}")
    return paths


def self_test():
    import importlib.util
    import json
    import sys
    import unittest

    repo = Path(__file__).resolve().parents[1]

    def load(relative, name):
        spec = importlib.util.spec_from_file_location(name, repo / relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    class FixtureTests(unittest.TestCase):
        def test_tracked_copy_excludes_extras_and_respects_snapshot_index(self):
            with tempfile.TemporaryDirectory() as raw, patched_environment({
                key: None for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
            }):
                root = Path(raw)
                source = root / "source"
                source.mkdir()
                subprocess.run(["git", "init", "-q", str(source)], check=True)
                with self.assertRaisesRegex(ValueError, "no tracked paths"):
                    copy_tracked_tree(source, root / "empty")
                (source / ".gitignore").write_text("benchmarks/out/\n")
                script = source / "kept.sh"
                script.write_text("#!/bin/sh\necho staged\n")
                script.chmod(0o755)
                (source / "tracked-link").symlink_to("missing-target")
                subprocess.run(["git", "-C", str(source), "add", "--", ".gitignore", "kept.sh", "tracked-link"], check=True)
                script.write_text("#!/bin/sh\necho current\n")
                ignored = source / "benchmarks/out"
                ignored.mkdir(parents=True)
                (ignored / "broken-executable").symlink_to("absent-runtime")
                (source / "untracked.txt").write_text("not part of the subject")
                materialized = root / "materialized"
                paths = copy_tracked_tree(source, materialized)
                self.assertEqual([".gitignore", "kept.sh", "tracked-link"], paths)
                self.assertEqual(script.read_bytes(), (materialized / "kept.sh").read_bytes())
                self.assertTrue(os.access(materialized / "kept.sh", os.X_OK))
                self.assertEqual("missing-target", os.readlink(materialized / "tracked-link"))
                self.assertFalse((materialized / "benchmarks").exists())
                self.assertFalse((materialized / "untracked.txt").exists())
                index = root / "snapshot-index"
                shutil.copy2(source / ".git/index", index)
                (source / "later.txt").write_text("live index changed")
                subprocess.run(["git", "-C", str(source), "add", "later.txt"], check=True)
                # The materialized pre-commit subject has no .git directory of
                # its own; its borrowed index must remain the authority.
                with patched_environment({"GIT_DIR": source / ".git", "GIT_WORK_TREE": materialized,
                                          "GIT_INDEX_FILE": index}):
                    self.assertEqual(paths, copy_tracked_tree(materialized, root / "snapshot-copy"))
                    with self.assertRaisesRegex(ValueError, "effective Git work tree"):
                        copy_tracked_tree(source, root / "wrong-tree")
                (source / "later.txt").unlink()
                with self.assertRaisesRegex(ValueError, "member is missing"):
                    copy_tracked_tree(source, root / "missing-member")

        def test_legacy_context_owns_assets_on_both_observation_routes(self):
            with tempfile.TemporaryDirectory() as raw:
                ambient = Path(raw)
                state = ambient / "state"
                (state / "runtime").mkdir(parents=True)
                marker = state / "runtime/private-install.json"
                marker.write_text("ambient private-install sentinel")
                values = {"AGENT_BIOS_PRIVATE_INSTRUCTIONS": "1", "AGENT_BIOS_STATE_DIR": str(state),
                          "CODEX_HOME": str(ambient / "absent-codex"),
                          "CLAUDE_CONFIG_DIR": str(ambient / "absent-claude")}
                with patched_environment(values):
                    with legacy_host_environment(repo) as fixture:
                        launch = load("launch/agent-launch.py", "fixture_launch_test")
                        self.assertFalse(launch.private_instructions_enabled())
                        config = launch.load_config(repo / "launch/agent-launch.toml")
                        for binding in config["backends"].values():
                            binding["command"] = sys.executable
                        args = launch.project_args(launch.build_plan(config, "codex", "balanced"), materialize_agents=False)
                        self.assertIn(str(fixture / "claude/bin/claude-run"), "\n".join(args))
                        self.assertIn(str(fixture / "cache"), "\n".join(args))
                        for host, names in (("codex", ("codex-run", "codex-helm")), ("claude", ("claude-run",))):
                            for name in names:
                                self.assertTrue(os.access(fixture / host / "bin" / name, os.X_OK))
                                self.assertIn("exit 0", (fixture / host / "bin" / name).read_text())
                        self.assertEqual((repo / "codex/agents/frontier.toml").read_bytes(),
                                         (fixture / "codex/agents/frontier.toml").read_bytes())
                        child = json.loads(subprocess.check_output([sys.executable, "-c",
                            "import os,json; print(json.dumps({k:os.environ.get(k) for k in "
                            "['AGENT_BIOS_PRIVATE_INSTRUCTIONS','CODEX_HOME','CLAUDE_CONFIG_DIR']}))"], text=True))
                        self.assertEqual("0", child["AGENT_BIOS_PRIVATE_INSTRUCTIONS"])
                        self.assertEqual(str(fixture / "codex"), child["CODEX_HOME"])
                        self.assertEqual(str(fixture / "claude"), child["CLAUDE_CONFIG_DIR"])
                    self.assertEqual(values, {key: os.environ.get(key) for key in values})
                self.assertFalse((ambient / "absent-codex").exists())
                self.assertFalse((ambient / "absent-claude").exists())
                self.assertEqual("ambient private-install sentinel", marker.read_text())
                self.assertFalse(fixture.exists())

        def test_environment_restores_absent_empty_and_set_values_after_exception(self):
            values = {"CODEX_HOME": None, "CLAUDE_CONFIG_DIR": "", "AGENT_BIOS_PRIVATE_INSTRUCTIONS": "1"}
            with patched_environment(values):
                with self.assertRaisesRegex(RuntimeError, "fixture interruption"):
                    with legacy_host_environment(repo):
                        raise RuntimeError("fixture interruption")
                self.assertNotIn("CODEX_HOME", os.environ)
                self.assertEqual("", os.environ["CLAUDE_CONFIG_DIR"])
                self.assertEqual("1", os.environ["AGENT_BIOS_PRIVATE_INSTRUCTIONS"])

        def test_entrypoints_apply_and_restore_their_boundary(self):
            cases = (("gates/capture-review-goldens.py", "capture", "_capture", ()),
                     ("gates/check_parity.py", "main", "run_checks", ([],)),
                     ("launch/test-tier-effort.py", "main", "run_checks", ()))
            with patched_environment({"AGENT_BIOS_PRIVATE_INSTRUCTIONS": "1", "CODEX_HOME": "/absent-fixture-host"}):
                for index, (path, entry, inner, args) in enumerate(cases):
                    with self.subTest(entry=path):
                        module = load(path, f"fixture_entry_{index}")
                        def observe(*unused, **kwargs):
                            return (os.environ.get("AGENT_BIOS_PRIVATE_INSTRUCTIONS"),
                                    (Path(os.environ["CODEX_HOME"]) / "agents/frontier.toml").is_file())
                        setattr(module, inner, observe)
                        self.assertEqual(("0", True), getattr(module, entry)(*args))
                        self.assertEqual("1", os.environ["AGENT_BIOS_PRIVATE_INSTRUCTIONS"])
                        self.assertEqual("/absent-fixture-host", os.environ["CODEX_HOME"])

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixtureTests))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("source", nargs="?")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.source or not args.destination:
        parser.error("provide source and destination, or --self-test")
    copy_tracked_tree(args.source, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
