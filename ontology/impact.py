#!/usr/bin/env python3
"""Answer the question this ontology exists for: I am changing X — what else must move?

Two modes, both reading instances/graph.json:

  impact.py <entity|path>   the obligation closure of a change site
  impact.py --diff [RANGE]  obligations whose one side changed and whose other did not

Traversal is NOT "edges out of X". Obligation direction is a property of the edge kind
(dependency_rules.md): `forward` means changing `from` obliges `to`, `backward` means
changing `to` obliges `from`, `both` means either. Walking only outgoing edges answers
half the question while looking like it answered all of it.

What this cannot see, stated rather than implied: entity-to-file mapping comes from
anchor paths, so an entity whose anchor names no repo path is invisible to --diff, and
a file touching several entities attributes to all of them. It is a disclosure, not a
blocking check — the ontology's own rule is that only deterministically decidable
structural violations hard-block.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
GRAPH = HERE / "instances" / "graph.json"

OBLIGATION = {
    "projects_to": "forward",
    "owes_entry": "forward",
    "requires": "backward",
    "controls": "forward",
    "lockstep_with": "both",
    "asserts": "backward",
    "owes_removal": "forward",
    "migrates": "both",
    "precedes": "forward",
}

# Same rule as the gate: a $VAR-prefixed path is a runtime destination, not a repo file.
ANCHOR_PATH = re.compile(
    r"(\$\{?\w+\}?/)?((?:[\w.-]+/)*[\w.-]+\.(?:py|sh|md|json|toml|zsh|html))"
)


def load() -> dict:
    return json.loads(GRAPH.read_text(encoding="utf-8"))


def entity_files(graph: dict) -> dict[str, set[str]]:
    """Repo paths each entity is anchored to. Globs in anchors are expanded."""
    out: dict[str, set[str]] = {}
    for ent in graph["entities"]:
        paths: set[str] = set()
        for runtime, path in ANCHOR_PATH.findall(ent["anchor"]):
            if runtime:
                continue
            if (REPO / path).is_file():
                paths.add(path)
        for glob in re.findall(r"((?:[\w.-]+/)+[\w.*-]*\*[\w.*-]*)", ent["anchor"]):
            paths |= {str(p.relative_to(REPO)) for p in REPO.glob(glob) if p.is_file()}
        out[ent["id"]] = paths
    return out


def obligations_of(graph: dict, eid: str) -> list[dict]:
    """Everything that must move when `eid` changes, with why."""
    found = []
    for r in graph["relationships"]:
        d = OBLIGATION[r["kind"]]
        if r["from"] == eid and d in ("forward", "both"):
            found.append({"other": r["to"], "edge": r["name"], "kind": r["kind"],
                          "guard": r["guard"], "why": r["desc"], "dir": "→"})
        elif r["to"] == eid and d in ("backward", "both"):
            found.append({"other": r["from"], "edge": r["name"], "kind": r["kind"],
                          "guard": r["guard"], "why": r["desc"], "dir": "←"})
    return found


def resolve(graph: dict, token: str, files: dict[str, set[str]]) -> list[str]:
    ids = {e["id"] for e in graph["entities"]}
    if token in ids:
        return [token]
    by_class = {e["class"].lower(): e["id"] for e in graph["entities"]}
    if token.lower() in by_class:
        return [by_class[token.lower()]]
    hits = [eid for eid, ps in files.items() if any(token in p for p in ps)]
    if hits:
        return sorted(hits)
    near = sorted(i for i in ids if token.lower() in i)
    if near:
        print(f"no exact match for {token!r}; did you mean: {', '.join(near)}", file=sys.stderr)
    return []


def cmd_query(graph: dict, token: str, depth: int) -> int:
    files = entity_files(graph)
    roots = resolve(graph, token, files)
    if not roots:
        print(f"nothing in the ontology anchors to {token!r}", file=sys.stderr)
        return 1
    ent_by_id = {e["id"]: e for e in graph["entities"]}
    for root in roots:
        ent = ent_by_id[root]
        print(f"\n{ent['class']}  ({ent['family']}, guard {ent['guard']}, reaches {'/'.join(ent['pos'])})")
        print(f"  anchor: {ent['anchor']}")
        seen = {root}
        frontier = [(root, 0)]
        rows = []
        while frontier:
            cur, lvl = frontier.pop(0)
            if lvl >= depth:
                continue
            for ob in obligations_of(graph, cur):
                rows.append((lvl, cur, ob))
                if ob["other"] not in seen:
                    seen.add(ob["other"])
                    frontier.append((ob["other"], lvl + 1))
        if not rows:
            print("  no obligations recorded — either genuinely isolated, or the edge is missing")
            continue
        print(f"  {len(rows)} obligation(s), {len(seen) - 1} other entit(ies) in the closure:")
        for lvl, src, ob in rows:
            pad = "  " + "    " * lvl
            mark = {"unguarded": "!!", "partial": " ~", "gated": " ✓", "derived": " ="}[ob["guard"]]
            other = ent_by_id[ob["other"]]["class"]
            print(f"{pad}{mark} {ent_by_id[src]['class']} {ob['dir']} {other}"
                  f"   [{ob['kind']}/{ob['edge']}]")
            print(f"{pad}     {ob['why']}")
        unguarded = [r for r in rows if r[2]["guard"] == "unguarded"]
        if unguarded:
            print(f"  {len(unguarded)} of these is enforced by nothing — those are the ones to check by hand")
    return 0


def changed_files(rng: str | None) -> list[str]:
    """Tracked modifications UNION untracked files.

    `git diff` omits untracked paths, so a newly added file — the most common shape of
    "I added something and forgot the other half" — was invisible to this check. Taking
    the union always, rather than only when the diff came back empty, is the fix.
    """
    args = ["git", "diff", "--name-only"] + ([rng] if rng else ["HEAD"])
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"git diff failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    out = {p for p in r.stdout.split("\n") if p}
    if not rng:
        r2 = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                            cwd=REPO, capture_output=True, text=True)
        out |= {p for p in r2.stdout.split("\n") if p}
    return sorted(out)


def cmd_diff(graph: dict, rng: str | None) -> int:
    files = entity_files(graph)
    touched_files = set(changed_files(rng))
    if not touched_files:
        print("no changed files — nothing to check (an empty subject proves nothing)")
        return 0

    touched = {eid for eid, ps in files.items() if ps & touched_files}
    unmapped = touched_files - {p for ps in files.values() for p in ps}
    ent_by_id = {e["id"]: e for e in graph["entities"]}

    print(f"changed files: {len(touched_files)}   entities touched: {len(touched)}")
    if not touched:
        print("no changed file is anchored to an entity — the ontology has nothing to say about this diff")
        if unmapped:
            print(f"  unmapped ({len(unmapped)}): {', '.join(sorted(unmapped)[:8])}"
                  + (" …" if len(unmapped) > 8 else ""))
        return 0

    open_rows = []
    for eid in sorted(touched):
        for ob in obligations_of(graph, eid):
            other_files = files.get(ob["other"], set())
            if other_files & touched_files:
                continue  # both sides moved
            open_rows.append((eid, ob, other_files))

    for eid in sorted(touched):
        print(f"  touched  {ent_by_id[eid]['class']}")
    if unmapped:
        print(f"  unmapped {len(unmapped)} changed file(s) anchor to no entity: "
              f"{', '.join(sorted(unmapped)[:6])}" + (" …" if len(unmapped) > 6 else ""))

    if not open_rows:
        print("\nno open obligation: every counterpart of every touched entity also moved")
        return 0

    print(f"\n{len(open_rows)} obligation(s) where one side moved and the other did not:")
    for eid, ob, other_files in open_rows:
        mark = {"unguarded": "UNGUARDED", "partial": "partial  ", "gated": "gated    ", "derived": "derived  "}[ob["guard"]]
        where = ", ".join(sorted(other_files)[:2]) or "(no anchored file)"
        print(f"  [{mark}] {ent_by_id[eid]['class']} {ob['dir']} {ent_by_id[ob['other']]['class']}"
              f"  [{ob['kind']}]")
        print(f"              {ob['why']}")
        print(f"              counterpart lives in: {where}")

    hard = [r for r in open_rows if r[1]["guard"] in ("derived", "gated")]
    print(f"\n{len(hard)} of these already have a check that would catch it; "
          f"{len(open_rows) - hard.__len__()} would not.")
    print("Disclosure, not a verdict — an obligation can be legitimately one-sided. "
          "The ones marked UNGUARDED are where nothing else will tell you.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", help="entity id, class name, or path fragment")
    ap.add_argument("--diff", nargs="?", const="", metavar="RANGE",
                    help="check a git diff instead (default: uncommitted vs HEAD)")
    ap.add_argument("--depth", type=int, default=1, help="closure depth for a query (default 1)")
    args = ap.parse_args()

    graph = load()
    if args.diff is not None:
        sys.exit(cmd_diff(graph, args.diff or None))
    if not args.target:
        ap.error("give an entity/path, or use --diff")
    sys.exit(cmd_query(graph, args.target, args.depth))


if __name__ == "__main__":
    main()
