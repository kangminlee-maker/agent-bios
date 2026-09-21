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

The manifest itself sits in the directory it describes, as `manifest.json` at its top (SSOT S13:
`objects/<revision-digest>/manifest.json`), and is not one of its own members: the revision digest
is taken over the manifest's bytes, so listing them inside it would hash itself. What `emit`
writes is exactly those bytes, with nothing appended, so they can be saved as that file.

  python3 -m workenv.contracts.inventory <directory> --source <src_id> --at <instant>
  python3 -m workenv.contracts.inventory <directory> --against <manifest.json>
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any, Iterable

from . import c01, canonical, schema

KIND = "source_manifest"
SCHEMA = 1
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"


class InventoryError(ValueError):
    """A directory this module will not inventory, or a manifest it cannot read."""


def files(directory: pathlib.Path) -> list[pathlib.Path]:
    """Every regular file under the directory but its own manifest, sorted. Two shapes are
    refused rather than walked past, because an inventory of either would state something
    untrue."""
    if not directory.is_dir():
        # rglob over a path that is not a directory yields nothing, which reads as an empty
        # revision rather than as the wrong path.
        raise InventoryError(f"{directory} is not a directory")
    own = directory / MANIFEST_NAME
    if own.exists() and not own.is_file():
        # The name is the manifest's own place in its revision (SSOT S13); anything else there
        # would leave the revision unable to hold its manifest.
        raise InventoryError(f"{MANIFEST_NAME} is not a regular file; the name belongs to the "
                             f"revision's manifest")
    found = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise InventoryError(f"{path.relative_to(directory).as_posix()} is a symbolic link; "
                                 f"a revision holds bytes, not a name for somebody else's")
        if path.is_dir() or path == directory / MANIFEST_NAME:
            continue
        if not path.is_file():
            raise InventoryError(f"{path.relative_to(directory).as_posix()} is not a regular "
                                 f"file")
        found.append(path)
    return found


def members(root: pathlib.Path, paths: Iterable[pathlib.Path]) -> list[dict[str, Any]]:
    """Each path by its position under `root`, with its digest and size. One walk answers for
    a source revision and for this package's own fixtures, in one vocabulary."""
    rows = []
    for path in paths:
        data = path.read_bytes()
        rows.append({"path": path.relative_to(root).as_posix(),
                     "digest": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return rows


def manifest(directory: pathlib.Path, source_id: str, produced_at: str,
             format_version: int = FORMAT_VERSION) -> dict[str, Any]:
    """The `source_manifest` record for what the directory holds."""
    rows = members(directory, files(directory))
    if not rows:
        raise InventoryError(f"{directory} holds no member; a revision of nothing has no digest "
                             f"to bind")
    return {"kind": KIND, "schema": SCHEMA, "source_id": source_id,
            "format_version": format_version, "members": rows,
            "produced_at": produced_at}


def emit(directory: pathlib.Path, source_id: str, produced_at: str,
         format_version: int = FORMAT_VERSION) -> bytes:
    """The manifest as canonical bytes. Its sha256 is the revision digest others reference.
    What its own schema refuses — a path with a space, say — is refused here, not emitted."""
    stated = manifest(directory, source_id, produced_at, format_version)
    refused = stated_manifest_refusals(stated)
    if refused:
        raise InventoryError(f"the manifest's schema refuses {refused[0].pointer}: "
                             f"{refused[0].code}")
    return canonical.encode(stated)


def differences(stated: dict[str, Any], directory: pathlib.Path) -> list[tuple[str, str]]:
    """(code, path) for every disagreement between a manifest and a directory, path order."""
    listed: dict[str, dict[str, Any]] = {}
    found: list[tuple[str, str]] = []
    for member in stated.get("members", []):
        path = member["path"]
        if path in listed and listed[path] != member:
            found.append((c01.ID_BOUND_TO_OTHER_BYTES, path))
        listed.setdefault(path, member)
    on_disk = {member["path"]: member
               for member in members(directory, files(directory))}
    for path, member in sorted(listed.items()):
        held = on_disk.get(path)
        if held is None:
            found.append((c01.REF_UNAVAILABLE, path))
        elif held["digest"] != member["digest"] or held["size"] != member["size"]:
            found.append((c01.ID_BOUND_TO_OTHER_BYTES, path))
    found += [(c01.MANIFEST_MEMBER_UNLISTED, path)
              for path in sorted(set(on_disk) - set(listed))]
    return sorted(found, key=lambda row: (row[1], row[0]))


def stated_manifest_refusals(stated: Any) -> list:
    """What the committed `source_manifest` schema says about a stated manifest. A comparison
    against a manifest the schema refuses — no member, one path twice — would report agreement
    with something that is not a manifest."""
    document = json.loads((pathlib.Path(__file__).with_name("schemas")
                           / "c01_source_manifest.schema.json").read_bytes())
    return schema.load_schema(document).validate(stated)


def main(argv: list[str]) -> int:
    usage = ("usage: python3 -m workenv.contracts.inventory <directory> "
             "--source <src_id> --at <instant> | <directory> --against <manifest.json>")
    if len(argv) == 3 and argv[1] == "--against":
        try:
            data = pathlib.Path(argv[2]).read_bytes()
            stated = canonical.load(data)
            refused = stated_manifest_refusals(stated)
            if refused:
                for violation in refused:
                    print(f"FAIL: manifest {violation.pointer or '/'}: {violation.code}")
                return 1
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
            sys.stdout.buffer.write(emit(pathlib.Path(argv[0]), argv[2], argv[4]))
        except (InventoryError, OSError) as error:
            print(f"FAIL: {error}")
            return 1
        return 0
    print(usage)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
