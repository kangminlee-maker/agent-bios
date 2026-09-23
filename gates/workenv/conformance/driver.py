"""The conformance driver: what every family case's command runs through.

The catalog spells 27 of its families' commands as `<conformance-driver> --case-profile <P>
--family <Nxx>`, and the registry names this file as that driver, so a family case cannot run
until it exists. It resolves what a profile runs in one family, and it owns the joined-case
rule.

A **joined case** is one an implementation profile runs against an accepted predecessor's real
files. The registry says which case joins to which node (`selects[].joined`); this module is
what makes the joining real, because a marker that nothing acts on would let a name satisfy the
rule. Three things follow from that, and each is a refusal rather than a convention:

  a substituted resolver   `--subject-root` points subject resolution at some other tree. It is
                           how a fixture double would reach a joined run, so a selection holding
                           a joined case refuses it outright. Nothing else in the run is allowed
                           to decide this: a flag that is merely ignored still reads as accepted.
  an unaccepted predecessor  without the accepted run evidence there is no manifest to hold the
                           files against, so every joined case is `blocked` and named. It is
                           never `passed`: at this point in the plan nothing is accepted, and a
                           driver that reported otherwise would report the rule satisfied by its
                           own absence of work.
  files that moved         the predecessor's subjects are re-measured from the real tree and
                           their fingerprints compared with the ones its record was accepted on.
                           A difference means the bytes are not the accepted ones, and the run
                           stops there rather than proving a hash against itself.

What it hands back for a joined case is the verified member map — every path the predecessor's
accepted subjects cover and the sha256 each was accepted with — so a case that later reads any
of them is reading something already held against the accepted manifest, and the driver's own
output states which files that was.

Cases whose implementation does not exist yet are `blocked` with the node that owes them named.
That is the whole outcome set at this point in the plan; `passed` belongs to the node that
implements the family, not to the driver that resolves it.

  python3 gates/workenv/conformance/driver.py --case-profile P04 --family N27
  python3 gates/workenv/conformance/driver.py --case-profile P04 --family N27 --accepted RUN
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import cases  # noqa: E402
import subjects  # noqa: E402

BLOCKED = "blocked"
REFUSED = "refused"


class DriverError(ValueError):
    """A run this module refuses, named."""


def family_of(case: str) -> str:
    return case.split("-")[0]


def selection(registry: dict, profile: str) -> dict:
    """The profile's `selects` row, or a DriverError naming what is missing."""
    rows = [row for row in registry["selects"] if row["profile"] == profile]
    if not rows:
        raise DriverError(f"{profile}: the registry selects no cases for it")
    return rows[0]


def bound(registry: dict, profile: str, family: str) -> tuple[list[str], dict[str, str]]:
    """(the profile's cases in the family, case -> the node each joined one runs against)."""
    row = selection(registry, profile)
    chosen = sorted(case for case in row["cases"] if family_of(case) == family)
    if not chosen:
        raise DriverError(f"{profile}: it runs no case of {family}")
    joined = {entry["case"]: entry["predecessor"] for entry in row.get("joined", [])
              if family_of(entry["case"]) == family}
    return chosen, joined


def accepted_subjects(record: dict, node: str) -> dict[str, str]:
    """The subject fingerprints the predecessor's record was accepted on."""
    stated = record.get("subjects")
    if not isinstance(stated, dict) or not stated:
        raise DriverError(f"{node}: its record states no subject it was accepted on")
    return stated


def predecessor_members(node: str, accepted: dict, root: pathlib.Path) -> dict[str, str]:
    """Every path the node's accepted subjects cover, by the sha256 it was accepted with.

    The fingerprints are re-measured from `root` and compared with the accepted ones, so a
    member map only comes back when the tree still holds the bytes the record was accepted on.
    """
    records = accepted.get("records") or {}
    if node not in records:
        raise DriverError(f"{node}: the run evidence holds no accepted record for it")
    declared = subjects.manifests()
    members: dict[str, str] = {}
    for name, stated in sorted(accepted_subjects(records[node], node).items()):
        if name not in declared:
            raise DriverError(f"{node}: it was accepted on subject {name}, which no manifest "
                              f"declares")
        identity, why = subjects.state(name, declared[name], root)
        if identity is None:
            raise DriverError(f"{node}: subject {name} measures nothing here: {why}")
        if subjects.fingerprint(identity) != stated:
            raise DriverError(f"{node}: subject {name} measures "
                              f"{subjects.fingerprint(identity)} and its record was accepted on "
                              f"{stated}")
        members.update(identity.get("members", {}))
    if not members:
        raise DriverError(f"{node}: its accepted subjects cover no file to run against")
    return members


def run(profile: str, family: str, accepted: dict | None, subject_root: pathlib.Path | None,
        root: pathlib.Path = cases.ROOT) -> dict:
    """What this profile runs of this family, and what each joined case was held against."""
    registry = cases.load()
    chosen, joined = bound(registry, profile, family)
    if joined and subject_root is not None:
        raise DriverError(f"{profile}: {', '.join(sorted(joined))} run against an accepted "
                          f"predecessor's real files, and --subject-root would resolve them "
                          f"somewhere else")
    outcomes, loaded = {}, {}
    for case in chosen:
        node = joined.get(case)
        if node is None:
            outcomes[case] = {"outcome": BLOCKED,
                              "why": f"{family} has no implementation to run against yet"}
            continue
        try:
            members = predecessor_members(node, accepted or {}, subject_root or root)
        except DriverError as error:
            outcomes[case] = {"outcome": BLOCKED, "joined_to": node, "why": str(error)}
            continue
        loaded[case] = members
        outcomes[case] = {"outcome": BLOCKED, "joined_to": node, "loaded": len(members),
                          "why": f"{node}'s files are held and {family} has no implementation "
                                 f"to run against them yet"}
    return {"profile": profile, "family": family, "driver": registry["driver"],
            "cases": outcomes, "joined": joined, "loaded_files": loaded}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case-profile", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--accepted", type=pathlib.Path,
                        help="run evidence holding the predecessors' accepted records")
    parser.add_argument("--subject-root", type=pathlib.Path,
                        help="resolve subjects from this tree; refused for a joined case")
    args = parser.parse_args(argv)
    evidence = json.loads(args.accepted.read_text()) if args.accepted else None
    try:
        report = run(args.case_profile, args.family, evidence, args.subject_root)
    except DriverError as error:
        print(json.dumps({"outcome": REFUSED, "why": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if all(c["outcome"] != REFUSED for c in report["cases"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
