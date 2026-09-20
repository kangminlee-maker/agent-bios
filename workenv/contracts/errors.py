"""The one contract error table.

Each contract module owns its codes and their meanings in an `ERRORS` mapping. This module
joins them, refuses a code two modules claim, and emits `errors.json` beside itself for a
reader that does not run Python. That file is a projection: edit a module's `ERRORS`, then

  python3 -m workenv.contracts.errors --emit

The table is checked against the contract examples both ways by `coverage`: a code no
negative example exercises is a refusal nothing demonstrates, and an example that names a
code outside the table expects a refusal nothing produces.

Two kinds of module own rows. A reader module refuses bytes, so a refused example exercises
its codes. A contract module (`IN_RESULTS = True`) names the gaps an operation answers with;
no reader produces those from bytes, so an accepted result example states them instead, and an
expectation that asks the reader for one is refused.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Iterable

from . import c01, c02, c03, c04, c05, canonical, records, schema

TABLE_SCHEMA = 1
OWNERS = (canonical, schema, records, c01, c02, c03, c04, c05)
TABLE_PATH = pathlib.Path(__file__).with_name("errors.json")


def table() -> dict[str, dict[str, str]]:
    """code -> {owner, meaning}, or ValueError when two modules claim one code."""
    joined: dict[str, dict[str, str]] = {}
    for module in OWNERS:
        owner = module.__name__.rsplit(".", 1)[-1]
        for code, meaning in module.ERRORS.items():
            if code in joined:
                raise ValueError(f"error code {code!r} is claimed by {joined[code]['owner']} "
                                 f"and {owner}")
            joined[code] = {"owner": owner, "meaning": meaning}
    return joined


def emit() -> bytes:
    rows = [{"code": code, **entry} for code, entry in sorted(table().items())]
    # Exactly the canonical bytes, with no final newline, so the file loads as it is stored.
    return canonical.encode({"schema": TABLE_SCHEMA, "errors": rows})


def not_from_bytes() -> dict[str, str]:
    """code -> reason, for the codes their owning module declares unreachable from bytes."""
    joined: dict[str, str] = {}
    for module in OWNERS:
        joined.update(getattr(module, "NOT_FROM_BYTES", {}))
    return joined


def in_results() -> set[str]:
    """The codes contract modules own: stated inside a result, never raised by a reader."""
    return {code for module in OWNERS if getattr(module, "IN_RESULTS", False)
            for code in module.ERRORS}


def coverage(exercised: Iterable[str], stated: Iterable[str] = ()) -> list[str]:
    """Disagreements between the table and the examples: `exercised` are the codes refused
    examples expect of the reader, `stated` the gap codes accepted examples carry."""
    known, seen, told = set(table()), set(exercised), set(stated)
    exempt, results = not_from_bytes(), in_results()
    problems = [f"error code {code!r} is exercised by no negative example"
                for code in sorted(known - results - seen - set(exempt))]
    problems += [f"gap code {code!r} is stated by no accepted result example"
                 for code in sorted(results - told)]
    problems += [f"an expectation asks the reader for {code!r}, which only a result states"
                 for code in sorted(seen & results)]
    problems += [f"error code {code!r} is declared unreachable from bytes and an example "
                 f"exercises it; the declaration is stale" for code in sorted(seen & set(exempt))]
    problems += [f"{code!r} is declared unreachable from bytes and is not in the table"
                 for code in sorted(set(exempt) - known)]
    problems += [f"an example names error code {code!r}, which the table does not hold"
                 for code in sorted(seen - known)]
    problems += [f"an example states gap code {code!r}, which the table does not hold"
                 for code in sorted(told - known)]
    return problems


def main(argv: list[str]) -> int:
    if argv == ["--emit"]:
        TABLE_PATH.write_bytes(emit())
        print(f"wrote {TABLE_PATH.name}: {len(table())} codes")
        return 0
    if argv == ["--check"]:
        if not TABLE_PATH.is_file() or TABLE_PATH.read_bytes() != emit():
            print(f"FAIL: {TABLE_PATH.name} is not what the contract modules emit; "
                  f"run python3 -m workenv.contracts.errors --emit")
            return 1
        print(f"{TABLE_PATH.name} is current: {len(table())} codes")
        return 0
    print("usage: python3 -m workenv.contracts.errors --emit | --check")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
