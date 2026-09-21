"""Project the closed name lists the contract modules own into the schemas that carry them.

A schema cannot import a Python table, so each list a record may draw a name from is written into
every document that uses it, and this file is the only thing that writes one. A document takes a
list by defining the named `$defs` entry; its value is replaced whole.

  $defs/operation              every operation a contract module declares
  $defs/output_kind            every record kind some operation returns
  $defs/gap code               every gap a contract module's operations answer with
  $defs/disclosed_gap code     the gaps that qualify a commit rather than prevent one

  python3 gates/workenv/project-names.py           # write the lists into the schemas
  python3 gates/workenv/project-names.py --check   # fail when a schema differs from its owners
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from workenv.contracts import errors, examples  # noqa: E402


def lists() -> dict[str, list[str]]:
    table = {name: row for module in errors.OWNERS
             for name, row in getattr(module, "OPERATIONS", {}).items()}
    return {"operation": sorted(table),
            "output_kind": sorted({kind for row in table.values() for kind in row["returns"]}),
            "gap": sorted(errors.in_results()),
            "disclosed_gap": sorted(errors.disclosed())}


def projected(document: dict, names: dict[str, list[str]]) -> dict:
    """The document with every list it takes replaced by the owners' current one."""
    document = json.loads(json.dumps(document))
    defs = document.get("$defs", {})
    for name, values in names.items():
        if name not in defs:
            continue
        if name in ("gap", "disclosed_gap"):
            defs[name]["properties"]["code"] = {"enum": values}
        else:
            defs[name] = {"enum": values}
    return document


def render(document: dict) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False).encode() + b"\n"


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    names = lists()
    stale, taken = [], 0
    for path in sorted(examples.SCHEMAS.glob("*.schema.json")):
        document = json.loads(path.read_text())
        if not names.keys() & document.get("$defs", {}).keys():
            continue
        taken += 1
        wanted = render(projected(document, names))
        if path.read_bytes() != wanted:
            stale.append(path.name)
            if not argv:
                path.write_bytes(wanted)
    if not taken:
        print("FAIL no schema takes a projected list")
        return 1
    if argv and stale:
        for name in stale:
            print(f"FAIL {name} differs from the lists its contract modules own")
        return 1
    print(f"NAMES OK ({taken} schemas; {', '.join(f'{k} {len(v)}' for k, v in names.items())}"
          f"{'; rewrote ' + str(len(stale)) if stale and not argv else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
