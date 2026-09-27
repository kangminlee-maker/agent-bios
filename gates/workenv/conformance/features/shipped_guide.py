"""The shipped guide: what a routing's memory usage contract points at.

An activated `session_routing` carries the usage contract with a pointer to its guide: a path,
and the digest of the guide bytes this installation holds. A scenario states that digest as a
literal, which stands for the guide the installation ships. Before the first step this states
each pointer's digest as the sha256 of the file the code under test ships at that path, under
its `workenv` package, so the answer is held to the guide that exists and not to a stand-in. A
path the code under test does not ship is left as stated, and the step that answers it fails by
name.
"""
from __future__ import annotations

import hashlib
import pathlib

import cases

PACKAGE = "workenv"


def install(run) -> None:
    run.prepare_hooks.append(build)


def shipped(root: pathlib.Path, path: str) -> str | None:
    """The digest of the guide the code under `root` ships at `path`, or None."""
    target = root / PACKAGE / path
    return hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None


def build(run) -> None:
    for name in cases.guide_pointers(run.built):
        guide = run.templates[name]["delivery"]["memory_usage"]["guide"]
        digest = shipped(pathlib.Path(run.root), guide["path"])
        if digest is not None:
            guide["digest"] = digest
    run.forget()
