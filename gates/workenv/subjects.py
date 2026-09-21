"""Subject fingerprints: one manifest per plan subject, and one rule that measures them.

The plan's evaluator compares a node's recorded subject fingerprints against current ones, so
every subject needs a declared closure and one derivation. `subjects.json` holds the manifests;
this module resolves them. Nothing here judges acceptance.

A manifest declares one of three identities.

  path_closure       tracked paths, each member by its sha256. The closure is what the manifest
                     declares plus the paths the plan says a node owns, so moving a node's
                     ownership moves the closure without an edit here.
  recorded           an identity a predecessor node measured and wrote down. The fingerprint is
                     reproduced from that record, not measured a second way.
  measured_elsewhere no bytes in this repository decide it. It resolves to unknown, with the
                     node that does measure it named.

A closure may name paths no node has written yet, because the plan says who will own them
before the owner exists. Such a subject is not yet measurable and resolves to unknown, naming
the node and the path. A digest over the part that happens to exist already would be a real
answer to a question nobody asked, and an evaluator would compare it as if it meant something.
The same prefix declared by hand in the manifest, matching nothing, is a stale declaration and
fails instead: nothing else will ever write it.

The fingerprint rule is the dated evaluator's: sha256 over the identity serialized with sorted
keys, no spaces and no ASCII escaping. `test_subjects.py` holds P00's recorded baseline input
and its recorded fingerprint as literals and requires this rule to reproduce it; deriving the
expectation here instead would compare the rule to itself.

An absent subject resolves to unknown. It never falls back to a digest of something near it,
because a fingerprint that answers for the wrong closure is accepted by an evaluator that would
have refused an honest silence.

  python3 gates/workenv/subjects.py            # resolve every subject
  python3 gates/workenv/subjects.py --check    # hold the manifests against the current plan
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import current_selector  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFESTS = pathlib.Path(__file__).with_name("subjects.json")
ENTRY = ROOT / "design/knowledge-and-history/CURRENT.md"
UNKNOWN = None


class SubjectError(ValueError):
    """A manifest this module cannot resolve, named."""


def fingerprint(identity: dict) -> str:
    """The dated evaluator's rule, applied to an identity object."""
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def manifests(path: pathlib.Path = MANIFESTS) -> dict[str, dict]:
    document = json.loads(path.read_bytes())
    return document["subjects"]


def plan(root: pathlib.Path = ROOT) -> dict:
    """The plan the one dated-bundle pointer selects, read the way the gates read it."""
    text = (root / "design/knowledge-and-history/CURRENT.md").read_text(encoding="utf-8")
    prose = current_selector.current_selector_prose(text)
    selected = re.findall(current_selector.PLAN_SELECTOR, prose)
    if len(selected) != 1 or not selected[0]:
        raise SubjectError(f"CURRENT.md names {len(selected)} implementation task graphs; "
                           f"exactly one is a pointer")
    return json.loads((root / "design/knowledge-and-history" / selected[0]).read_bytes())


def tracked(root: pathlib.Path = ROOT) -> list[str]:
    """Every tracked path, from git, so an untracked file cannot join a closure unseen."""
    done = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return sorted(p for p in done.stdout.decode().split("\0") if p)


def reaches(start: str, nodes: dict[str, dict]) -> list[str]:
    """`start` and every node it reaches through depends_on."""
    seen, stack = set(), [start]
    while stack:
        current = stack.pop()
        if current in seen or current not in nodes:
            continue
        seen.add(current)
        stack += nodes[current].get("depends_on") or []
    return sorted(seen)


def prefixes(name: str, manifest: dict, nodes: dict[str, dict],
             payload: list[str] | None = None) -> dict[str, str]:
    """prefix -> where it came from: `declared` for the manifest's own, otherwise the node
    whose owned_paths carry it. The origin is what decides how an unwritten path is read."""
    found: dict[str, str] = {}
    for prefix in manifest.get("declared", []):
        found.setdefault(prefix, "declared")
    include = manifest.get("include") or {}
    owners = list(include.get("owned_by", []))
    if "reaches" in include:
        start = include["reaches"]
        if start not in nodes:
            raise SubjectError(f"{name}: include.reaches names {start}, which the plan does "
                               f"not hold")
        owners += reaches(start, nodes)
    for node in owners:
        if node not in nodes:
            raise SubjectError(f"{name}: include.owned_by names {node}, which the plan does "
                               f"not hold")
        for prefix in nodes[node].get("owned_paths") or []:
            found.setdefault(prefix, node)
    if "payload_of" in include:
        if payload is None:
            raise SubjectError(f"{name}: include.payload_of needs the payload list")
        for prefix in payload:
            found.setdefault(prefix, "declared")
    if not found:
        raise SubjectError(f"{name}: the closure is empty, and a fingerprint over nothing "
                           f"matches every other nothing")
    return found


def payload_of(root: pathlib.Path, path: str, excepted: dict[str, str]) -> list[str]:
    """What `files[]` names, which is what npm packs, less the entries the manifest excepts by
    name with a reason. An exception that names a path files[] does not, or one that is in the
    tree after all, is stale and fails."""
    declared = json.loads((root / path).read_bytes()).get("files") or []
    if not declared:
        raise SubjectError(f"{path} declares no files[], so there is no payload to measure")
    entries = [entry.lstrip("./") for entry in declared]
    for name, reason in excepted.items():
        if name not in entries:
            raise SubjectError(f"the payload exception {name!r} names a path files[] does not, "
                               f"and its reason is {reason!r}")
        if (root / name).exists():
            raise SubjectError(f"the payload exception {name!r} is in the tree after all, so "
                               f"the reason {reason!r} no longer holds")
    # npm packs these whatever files[] says (npm-packlist's always-included set), so a payload
    # measured from files[] alone stays current while one of them changes.
    manifest = json.loads((root / path).read_bytes())
    always = {path} | {name.name for name in root.iterdir() if name.is_file()
                       and name.name.upper().startswith(("README", "LICENSE", "LICENCE"))}
    bins = manifest.get("bin") or {}
    always |= set(bins.values() if isinstance(bins, dict) else [bins])
    if manifest.get("main"):
        always.add(manifest["main"])
    return sorted({entry for entry in entries if entry not in excepted}
                  | {name.lstrip("./") for name in always})


def closure(name: str, wanted: dict[str, str],
            paths: list[str]) -> tuple[list[str], list[str]]:
    """(the tracked paths the prefixes select, the prefixes nobody has written yet). A prefix
    the manifest itself declares and nothing matches is a stale declaration and raises."""
    selected: set[str] = set()
    unwritten = []
    for prefix, origin in sorted(wanted.items()):
        under = [p for p in paths if p == prefix or p.startswith(prefix.rstrip("/") + "/")]
        if not under:
            if origin == "declared":
                raise SubjectError(f"{name}: {prefix!r} is declared in the closure and matches "
                                   f"no tracked file")
            unwritten.append(f"{origin} has not written {prefix}")
            continue
        selected.update(under)
    return sorted(selected), unwritten


def members(root: pathlib.Path, paths: list[str]) -> dict[str, str]:
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def identity(name: str, manifest: dict, root: pathlib.Path = ROOT,
             nodes: dict[str, dict] | None = None,
             paths: list[str] | None = None) -> dict | None:
    """The object this subject's fingerprint is taken over, or None when nothing here measures
    it yet. `unwritten` on the exception-free path is reported by `state`."""
    return state(name, manifest, root, nodes, paths)[0]


def state(name: str, manifest: dict, root: pathlib.Path = ROOT,
          nodes: dict[str, dict] | None = None,
          paths: list[str] | None = None) -> tuple[dict | None, str]:
    """(identity or None, why it is None)."""
    kind = manifest["identity"]
    if kind == "measured_elsewhere":
        return UNKNOWN, f"measured by {manifest['measured_by']}"
    if kind == "recorded":
        recorded = manifest.get("recorded")
        if not isinstance(recorded, dict) or not recorded:
            # A fingerprint of {} measures nothing and would still read as a real answer.
            raise SubjectError(f"{name}: a recorded identity records nothing")
        return recorded, ""
    if kind != "path_closure":
        raise SubjectError(f"{name}: identity {kind!r} is not one this module resolves")
    nodes = nodes if nodes is not None else {n["id"]: n for n in plan(root)["nodes"]}
    paths = paths if paths is not None else tracked(root)
    payload = None
    if "payload_of" in (manifest.get("include") or {}):
        payload = payload_of(root, manifest["include"]["payload_of"],
                             manifest.get("except") or {})
    selected, unwritten = closure(name, prefixes(name, manifest, nodes, payload), paths)
    if unwritten:
        return UNKNOWN, "not yet measurable: " + "; ".join(unwritten)
    return {"subject": name, "members": members(root, selected)}, ""


def resolve(name: str, root: pathlib.Path = ROOT, declared: dict[str, dict] | None = None,
            **measured) -> str | None:
    """This subject's fingerprint, or None when no manifest declares it or nothing here
    measures it."""
    declared = declared if declared is not None else manifests()
    manifest = declared.get(name)
    if manifest is None:
        return UNKNOWN
    built = identity(name, manifest, root, **measured)
    return UNKNOWN if built is None else fingerprint(built)


def brief(why: str, keep: int = 2) -> str:
    """A reason short enough to read. A bundle can wait on fifty paths and the list is the
    same fact fifty times."""
    head, _, rest = why.partition(": ")
    reasons = [r for r in rest.split("; ") if r]
    if len(reasons) <= keep:
        return why
    return f"{head}: {len(reasons)} paths, first {'; '.join(reasons[:keep])}"


def check(root: pathlib.Path = ROOT) -> tuple[list[str], list[str]]:
    """(problems, report). The manifest set is held against the plan's subject set, and every
    manifest is resolved."""
    report, problems = [], []
    declared = manifests()
    current = plan(root)
    wanted = set(current["subjects"])
    if not wanted:
        return ["the plan declares no subject, so this check would judge nothing"], report
    report.append(f"plan subjects: {len(wanted)}; manifests: {len(declared)}")
    problems += [f"subject {name!r} has no manifest" for name in sorted(wanted - set(declared))]
    problems += [f"manifest {name!r} is not a subject of the plan"
                 for name in sorted(set(declared) - wanted)]
    nodes = {n["id"]: n for n in current["nodes"]}
    paths = tracked(root)
    for name in sorted(set(declared) & wanted):
        try:
            built, why = state(name, declared[name], root, nodes, paths)
        except SubjectError as error:
            problems.append(str(error))
            continue
        report.append(f"{name}: {fingerprint(built) if built else 'unknown (' + brief(why) + ')'}")
    return problems, report


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print("usage: python3 gates/workenv/subjects.py [--check]")
        return 2
    problems, report = check()
    for line in report:
        print(line)
    for line in problems:
        print(f"FAIL: {line}")
    if not problems:
        print("SUBJECTS OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
