"""The inventory of one source revision: what a directory holds, by member and hash.

A revision is its members, so the manifest is derived from the bytes rather than written beside
them. `manifest` walks a directory and returns a `source_manifest` record; `differences` reads
one back against a directory and names every way the two disagree, in the vocabulary of the one
error table:

  a member on disk the manifest does not list   c01.MANIFEST_MEMBER_UNLISTED
  a listed member this installation does not hold   c01.REF_UNAVAILABLE
  a listed member whose bytes differ            c01.ID_BOUND_TO_OTHER_BYTES
  one path listed twice                         c01.ID_BOUND_TO_OTHER_BYTES

The first of those is the reason this module exists. An inventory that lists a subset of what is
there is not a smaller inventory; it is a revision digest taken over bytes nobody enumerated.

Two shapes are refused rather than inventoried, because an inventory of either would state
something untrue. A symbolic link is not bytes this revision holds — following one would hash
whatever it points at, including a file outside the revision entirely. And an empty directory
has no members to bind, so a manifest of it would be a digest over nothing.

  python3 -m workenv.contracts.inventory <directory> --source <src_id> --at <instant>
  python3 -m workenv.contracts.inventory <directory> --against <manifest.json>
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
from typing import Any

from . import c01, canonical

KIND = "source_manifest"
SCHEMA = 1
FORMAT_VERSION = 1


class InventoryError(ValueError):
    """A directory this module will not inventory, or a manifest it cannot read."""


def members(directory: pathlib.Path) -> list[dict[str, Any]]:
    """Every file under the directory, by path relative to it, with its digest and size."""
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise InventoryError(f"{path.relative_to(directory).as_posix()} is a symbolic link; "
                                 f"a revision holds bytes, not a name for somebody else's")
        if path.is_dir():
            continue
        if not path.is_file():
            raise InventoryError(f"{path.relative_to(directory).as_posix()} is not a regular "
                                 f"file")
        data = path.read_bytes()
        rows.append({"path": path.relative_to(directory).as_posix(),
                     "digest": hashlib.sha256(data).hexdigest(), "size": len(data)})
    if not rows:
        raise InventoryError(f"{directory} holds no member; a revision of nothing has no digest "
                             f"to bind")
    return rows


def manifest(directory: pathlib.Path, source_id: str, produced_at: str,
             format_version: int = FORMAT_VERSION) -> dict[str, Any]:
    """The `source_manifest` record for what the directory holds."""
    return {"kind": KIND, "schema": SCHEMA, "source_id": source_id,
            "format_version": format_version, "members": members(directory),
            "produced_at": produced_at}


def emit(directory: pathlib.Path, source_id: str, produced_at: str,
         format_version: int = FORMAT_VERSION) -> bytes:
    """The manifest as canonical bytes. Its sha256 is the revision digest others reference."""
    return canonical.encode(manifest(directory, source_id, produced_at, format_version))


def differences(stated: dict[str, Any], directory: pathlib.Path) -> list[tuple[str, str]]:
    """(code, path) for every disagreement between a manifest and a directory, path order."""
    listed: dict[str, dict[str, Any]] = {}
    found: list[tuple[str, str]] = []
    for member in stated.get("members", []):
        path = member["path"]
        if path in listed and listed[path] != member:
            found.append((c01.ID_BOUND_TO_OTHER_BYTES, path))
        listed.setdefault(path, member)
    on_disk = {member["path"]: member for member in members(directory)}
    for path, member in sorted(listed.items()):
        held = on_disk.get(path)
        if held is None:
            found.append((c01.REF_UNAVAILABLE, path))
        elif held["digest"] != member["digest"] or held["size"] != member["size"]:
            found.append((c01.ID_BOUND_TO_OTHER_BYTES, path))
    found += [(c01.MANIFEST_MEMBER_UNLISTED, path)
              for path in sorted(set(on_disk) - set(listed))]
    return sorted(found, key=lambda row: (row[1], row[0]))


def main(argv: list[str]) -> int:
    usage = ("usage: python3 -m workenv.contracts.inventory <directory> "
             "--source <src_id> --at <instant> | <directory> --against <manifest.json>")
    if len(argv) == 3 and argv[1] == "--against":
        try:
            stated = canonical.load(pathlib.Path(argv[2]).read_bytes())
            disagreements = differences(stated, pathlib.Path(argv[0]))
        except (InventoryError, canonical.CanonicalError, OSError) as error:
            print(f"FAIL: {error}")
            return 1
        for code, path in disagreements:
            print(f"FAIL: {path}: {code}")
        if not disagreements:
            print(f"INVENTORY OK: {len(stated['members'])} members")
        return 1 if disagreements else 0
    if len(argv) == 5 and argv[1] == "--source" and argv[3] == "--at":
        try:
            sys.stdout.buffer.write(emit(pathlib.Path(argv[0]), argv[2], argv[4]) + b"\n")
        except (InventoryError, OSError) as error:
            print(f"FAIL: {error}")
            return 1
        return 0
    print(usage)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
