#!/usr/bin/env python3
"""Contract variants the required cases never exercise.

`cases.py` fails when an operation no case drives. Its subject is the operation, so a
request that carries four routes is driven when any one of them is used: the C01 source
request kept an `extend_supplied` route that no scenario ever sent, and every gate passed.

This reports one level finer, on the branches of a `oneOf`. A branch is identified by its
**discriminator**: the one property every sibling pins to a const, each to a different
value. That is what tells the branches apart, and it is the only literal worth looking
for. A branch's other consts are not identifying — `extend_supplied` also pinned
`base_bytes` to `"unmodified"`, a word the scenarios use freely, so accepting any const
would have called the dead route exercised and missed the case this tool exists for.

It discloses and exits 0. Which uncovered branch deserves a case is a judgement: a binding
record's frozen choice and the driver's own fixture mode are meant to sit outside the
scenarios, and a gate on that judgement is one people learn to route around. What the tool
owes the reader is the list and an honest denominator, not a verdict.

  python3 gates/workenv/variant-coverage.py             # report
  python3 gates/workenv/variant-coverage.py --self-test # controls
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMAS = ROOT / "workenv" / "contracts" / "schemas"
SCENARIOS = HERE / "fixtures" / "scenarios"


def _consts(node: object) -> dict[str, str]:
    if not isinstance(node, dict):
        return {}
    return {name: value["const"] for name, value in (node.get("properties") or {}).items()
            if isinstance(value, dict) and isinstance(value.get("const"), str)}


def branches(schemas: pathlib.Path) -> dict[tuple[str, str], str]:
    """Every oneOf branch that a discriminator identifies, as {(stem, branch): literal}."""
    found: dict[tuple[str, str], str] = {}
    for path in sorted(schemas.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        defs = document.get("$defs") or {}
        for group in defs.values():
            if not isinstance(group, dict) or not isinstance(group.get("oneOf"), list):
                continue
            named = []
            for member in group["oneOf"]:
                ref = member.get("$ref", "") if isinstance(member, dict) else ""
                name = ref.rsplit("/", 1)[-1] if ref.startswith("#/$defs/") else ""
                if name and name in defs:
                    named.append((name, _consts(defs[name])))
            if len(named) < 2:
                continue
            shared = set.intersection(*(set(consts) for _, consts in named))
            for prop in sorted(shared):
                values = [consts[prop] for _, consts in named]
                if len(set(values)) == len(values):      # it tells every branch apart
                    for (name, consts) in named:
                        found[(path.stem, name)] = consts[prop]
                    break
    return found


def stated(scenarios: pathlib.Path) -> str:
    """One blob of every generated scenario, which is what a literal is looked for in."""
    return "".join(path.read_text(encoding="utf-8")
                   for path in sorted(scenarios.glob("*/scenario.json")))


def report(schemas: pathlib.Path = SCHEMAS, scenarios: pathlib.Path = SCENARIOS) -> dict:
    identified = branches(schemas)
    blob = stated(scenarios)
    if not identified or not blob:
        # An empty subject would let this print a clean sheet over nothing at all.
        raise SystemExit(f"FAIL variant-coverage: {len(identified)} branches over "
                         f"{len(blob)} bytes of scenarios is nothing to judge")
    uncovered = sorted(key for key, literal in identified.items()
                       if f'"{literal}"' not in blob)
    return {"branches": len(identified), "uncovered": uncovered, "identified": identified}


def self_test() -> None:
    """It has to see a branch nobody sends, and not be fooled by a word that is not the
    discriminator — the exact way the dead C01 route hid from an earlier draft."""
    with tempfile.TemporaryDirectory(prefix="variant-coverage-") as tmp:
        root = pathlib.Path(tmp)
        schemas, scenarios = root / "schemas", root / "scenarios"
        schemas.mkdir()
        (scenarios / "one").mkdir(parents=True)
        (schemas / "c99_fixture.schema.json").write_text(json.dumps({"$defs": {
            "route": {"oneOf": [{"$ref": "#/$defs/used_route"},
                                {"$ref": "#/$defs/idle_route"}]},
            "used_route": {"properties": {"route": {"const": "a_route_in_use"}}},
            "idle_route": {"properties": {"route": {"const": "a_route_nobody_sends"},
                                          "base_bytes": {"const": "unmodified"}}},
            "not_a_branch": {"properties": {"note": {"type": "string"}}},
        }}), encoding="utf-8")
        # The scenario states the word the idle branch also pins, but never its route.
        (scenarios / "one" / "scenario.json").write_text(
            json.dumps({"steps": [{"route": "a_route_in_use", "bytes": "unmodified"}]}),
            encoding="utf-8")
        result = report(schemas, scenarios)
        assert result["branches"] == 2, result
        assert result["uncovered"] == [("c99_fixture.schema", "idle_route")], result
        assert result["identified"][("c99_fixture.schema", "idle_route")] \
            == "a_route_nobody_sends", "a non-discriminating const was used to identify"
        empty = root / "empty"
        empty.mkdir()
        try:
            report(schemas, empty)
        except SystemExit as exc:
            assert "nothing to judge" in str(exc), exc
        else:
            raise AssertionError("an empty scenario set reported a result")
    print("VARIANT COVERAGE SELF-TEST OK (3 controls)")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        self_test()
        return 0
    result = report()
    for schema, name in result["uncovered"]:
        print(f"  {schema}: {name}  ({result['identified'][(schema, name)]})")
    print(f"variant-coverage: {len(result['uncovered'])} of {result['branches']} "
          f"identified oneOf branches are sent by no required case (disclosure only)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
