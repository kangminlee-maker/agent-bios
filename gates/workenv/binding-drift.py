#!/usr/bin/env python3
"""Has the tree moved away from the case binding a contract freeze recorded?

`P01` freezes, for every profile the plan names, what that profile runs and what it runs it
with: the case set, the profile's own digest, an adapter fingerprint over the driver and the
contract bytes its cases drive, and a fixture fingerprint over the bytes its cases read. The
frozen artifact is `P01/case-bindings.json` in the accepted run, and at the moment of the
freeze it equals what `cases.py --bindings` emits from the tree.

**Nothing holds it there.** The evaluator compares the artifact with the `bindings` recorded in
the same run — two copies of one producer's output — and never recomputes from the tree. So an
edit to shared machinery after the freeze moves what a later profile would run under, and
every check stays green: editing `gates/workenv/conformance/driver.py` moves every profile
whose cases the driver runs, because the driver's bytes are inside each one's adapter
fingerprint. `P00`, whose binding is carried, and `P01`, whose cases are bootstrap commands, do
not move, which is why an accepted node keeps its acceptance and the drift is invisible.

This discloses that drift and exits 0 either way. It does not block, because a drift can be
either a regression or the intended result of shared work that the freeze has yet to catch up
with, and only a person can tell those apart. What it removes is the need to notice.

    python3 gates/workenv/binding-drift.py --accepted <run.json>

The run is required rather than defaulted: the artifact lives outside the repository with the
rest of the evidence, and a tool that reported "no drift" because it found no freeze to compare
against would be worse than no tool.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases  # noqa: E402

PARTS = ("cases", "profile_digest", "adapter_fingerprint", "fixture_fingerprint")
MEANING = {
    "cases": "which cases the profile runs",
    "profile_digest": "the catalog profile itself",
    "adapter_fingerprint": "the driver, the commands, or the contract bytes its cases drive",
    "fixture_fingerprint": "the fixture bytes its cases read, or the case definitions",
}


class DriftError(ValueError):
    """A comparison this tool refuses to call clean."""


def frozen_bindings(run_path: pathlib.Path) -> tuple[dict, pathlib.Path]:
    """(the bindings the freeze recorded, the artifact they came from).

    Taken from the artifact the run's record points at rather than from the run's own
    `bindings` field, because those two being equal is what the evaluator already checks; the
    open question is whether the tree still agrees with them.
    """
    run = json.loads(run_path.read_text(encoding="utf-8"))
    records = run.get("records")
    if not isinstance(records, dict) or not records:
        raise DriftError(f"{run_path}: it records no node, so it freezes nothing")
    for node, record in sorted(records.items()):
        item = (record.get("artifacts") or {}).get("case-bindings")
        if not isinstance(item, dict) or not item.get("path"):
            continue
        artifact = (run_path.parent / item["path"]).resolve()
        if not artifact.is_file():
            raise DriftError(f"{node} names {item['path']} and it is not there")
        held = json.loads(artifact.read_text(encoding="utf-8"))
        bindings = held.get("bindings")
        if not isinstance(bindings, dict) or not bindings:
            raise DriftError(f"{artifact}: it holds no binding to compare against")
        return bindings, artifact
    raise DriftError(f"{run_path}: no record in it names a case-bindings artifact")


def compare(frozen: dict, current: dict) -> list[dict]:
    """One row per profile that moved, naming which part moved and what it means."""
    moved = []
    for profile in sorted(set(frozen) | set(current)):
        was, now = frozen.get(profile), current.get(profile)
        if was == now:
            continue
        if was is None or now is None:
            moved.append({"profile": profile,
                          "why": "the freeze holds it and the tree does not"
                                 if now is None else "the tree holds it and the freeze does not"})
            continue
        parts = [part for part in PARTS if was.get(part) != now.get(part)]
        moved.append({"profile": profile, "moved": parts,
                      "why": "; ".join(MEANING[part] for part in parts) or "an unnamed field"})
    return moved


def report(run_path: pathlib.Path) -> int:
    frozen, artifact = frozen_bindings(run_path)
    current = cases.bindings()["bindings"]
    if not current:
        raise DriftError("cases.py emitted no binding, so there is nothing to compare")
    moved = compare(frozen, current)
    print(f"binding-drift: {len(frozen)} frozen profile(s) in {artifact.name}, "
          f"{len(current)} emitted from the tree")
    if not moved:
        print("binding-drift: the tree still emits what the freeze recorded")
        return 0
    print(f"binding-drift: {len(moved)} profile(s) moved since the freeze")
    for row in moved:
        parts = ",".join(row.get("moved", [])) or "-"
        print(f"  {row['profile']:<4} {parts:<38} {row['why']}")
    print("binding-drift: this discloses and does not block. A drift is either a regression or "
          "shared work the freeze has not caught up with, and only a person can tell them apart.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--accepted", type=pathlib.Path,
                        help="the run evidence whose record names the frozen case-bindings")
    parser.add_argument("--self-test", action="store_true",
                        help="run the controls; needs no evidence and reads no tree")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.accepted is None:
        parser.error("--accepted is required: there is no default freeze to compare against, "
                     "and reporting no drift because none was found would say nothing")
    try:
        return report(args.accepted)
    except DriftError as error:
        print(f"binding-drift: {error}", file=sys.stderr)
        return 2


def self_test() -> int:
    """Each control plants one thing and requires this tool to say so by name.

    The first is the positive control: an unmoved pair must report no drift, or a tool that
    called everything moved would pass every other control here for the wrong reason.
    """
    import tempfile

    failures = []

    def check(name: str, got: object, want: object):
        if got != want:
            failures.append(f"{name}: got {got!r}, wanted {want!r}")

    frozen = {"P02": {"cases": {"A": "N02"}, "profile_digest": "d", "adapter_fingerprint": "a",
                      "fixture_fingerprint": "f"},
              "P03": {"cases": {}, "profile_digest": "d", "adapter_fingerprint": "a",
                      "fixture_fingerprint": "f"}}
    check("an unmoved pair reports no drift", compare(frozen, frozen), [])

    moved_adapter = json.loads(json.dumps(frozen))
    moved_adapter["P02"]["adapter_fingerprint"] = "other"
    rows = compare(frozen, moved_adapter)
    check("a moved adapter names one profile", [r["profile"] for r in rows], ["P02"])
    check("a moved adapter names the part", rows[0]["moved"], ["adapter_fingerprint"])

    moved_two = json.loads(json.dumps(frozen))
    moved_two["P03"]["cases"] = {"B": "N03"}
    moved_two["P03"]["fixture_fingerprint"] = "other"
    rows = compare(frozen, moved_two)
    check("two moved parts are both named", rows[0]["moved"], ["cases", "fixture_fingerprint"])

    added = json.loads(json.dumps(frozen))
    added["P99"] = dict(frozen["P02"])
    rows = compare(frozen, added)
    check("a profile the freeze does not hold is reported",
          [r["profile"] for r in rows], ["P99"])
    dropped = {k: v for k, v in frozen.items() if k != "P03"}
    rows = compare(frozen, dropped)
    check("a profile the tree no longer emits is reported",
          [r["profile"] for r in rows], ["P03"])

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        empty = root / "no-records.json"
        empty.write_text(json.dumps({"records": {}}), encoding="utf-8")
        try:
            frozen_bindings(empty)
            failures.append("a run recording nothing was not refused")
        except DriftError as error:
            check("a run recording nothing is refused by name",
                  "freezes nothing" in str(error), True)

        missing = root / "missing-artifact.json"
        missing.write_text(json.dumps(
            {"records": {"P01": {"artifacts": {"case-bindings": {"path": "gone.json"}}}}}),
            encoding="utf-8")
        try:
            frozen_bindings(missing)
            failures.append("a named artifact that is absent was not refused")
        except DriftError as error:
            check("an absent artifact is refused by name", "is not there" in str(error), True)

        hollow = root / "hollow.json"
        (root / "held.json").write_text(json.dumps({"bindings": {}}), encoding="utf-8")
        hollow.write_text(json.dumps(
            {"records": {"P01": {"artifacts": {"case-bindings": {"path": "held.json"}}}}}),
            encoding="utf-8")
        try:
            frozen_bindings(hollow)
            failures.append("an artifact holding no binding was not refused")
        except DriftError as error:
            check("an empty artifact is refused rather than called clean",
                  "no binding to compare against" in str(error), True)

    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)
    print(f"binding-drift --self-test: {'FAILED' if failures else 'passed'}, "
          f"9 control(s), {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
