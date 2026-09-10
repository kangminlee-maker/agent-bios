#!/usr/bin/env python3
"""Fixture snapshots: every response starts from the same bytes.

A scenario whose fixture carries the previous response's edits is not the same
scenario, and the drift runs one way — toward the state a HIT produces — so the
second repetition of a cell is easier than the first. The snapshot is taken once
per run, hashed, and restored before every response; the hash goes in the receipt
so a response can be tied to the fixture it actually saw.

Fixture-less scenarios get a fresh empty directory instead, for the same reason:
a working directory that accumulates is a fixture nobody declared.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import tempfile


class FixtureError(RuntimeError):
    """A fixture that cannot be restored to a known state."""


def hash_dir(path: pathlib.Path) -> str:
    """sha256 over (relpath, bytes) of every file, sorted."""
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file())
    for p in files:
        digest.update(str(p.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(p.read_bytes())
        digest.update(b"\0")
    digest.update(f"|files={len(files)}".encode())
    return digest.hexdigest()


class Snapshot:
    """A pristine copy of one fixture, plus the working directory handed to a run."""

    def __init__(self, source: pathlib.Path | None, workroot: pathlib.Path, name: str):
        self.name = name
        self.work = workroot / name
        self.pristine = workroot / f".pristine-{name}"
        if source is None:
            self.pristine.mkdir(parents=True, exist_ok=True)
        else:
            if not source.is_dir():
                raise FixtureError(f"{source}: fixture directory not found")
            if self.pristine.exists():
                shutil.rmtree(self.pristine)
            shutil.copytree(source, self.pristine)
        self.hash = hash_dir(self.pristine)
        self.reset()

    def reset(self) -> str:
        """Restore the working directory and return the hash it was restored to."""
        if self.work.exists():
            shutil.rmtree(self.work)
        shutil.copytree(self.pristine, self.work)
        got = hash_dir(self.work)
        if got != self.hash:
            raise FixtureError(
                f"{self.name}: restored fixture hashes {got[:12]}, snapshot is "
                f"{self.hash[:12]} — the reset did not reproduce the declared state")
        return got


def workroot(prefix: str = "bench-fixtures-") -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix=prefix))
