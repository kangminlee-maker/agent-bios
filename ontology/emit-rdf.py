#!/usr/bin/env python3
"""Project ontology/instances/graph.json into RDF/XML for Ontology Playground.

The playground (microsoft/Ontology-Playground) is an external viewer, so this is a
projection, not an authority: graph.json stays canonical and this file is regenerated.
`--check` fails when the emitted RDF has drifted, so the projection cannot go stale
silently — the same contract gates/emit-mirrors.py holds for the codex/ tree.

Contract read out of the playground's own source rather than inferred from samples:
  - entity id  = uncapitalize(local name of the class URI)     (parser.ts:176-177)
  - names      = ^[A-Za-z0-9]([A-Za-z0-9_-]{0,24}[A-Za-z0-9])?$ (designerStore.ts:23)
  - each entity needs exactly one identifier property, string or integer
  - a property name reused across entities must keep the same type
  - cardinality one-to-one | one-to-many | many-to-one | many-to-many

Usage: emit-rdf.py [--check] [-o OUT]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from xml.sax.saxutils import escape

HERE = pathlib.Path(__file__).resolve().parent
GRAPH = HERE / "instances" / "graph.json"
DEFAULT_OUT = HERE / "agent-bios.rdf"
PATHS_OUT = HERE / "agent-bios-routes.rdf"

BASE = "http://agent-bios.local/ontology/agent-bios/"
NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9_-]{0,24}[A-Za-z0-9])?$")
CARDINALITIES = {"one-to-one", "one-to-many", "many-to-one", "many-to-many"}

# Colour carries the judgment question — what is actually holding this obligation —
# so an unguarded entity is red on sight. Family rides on the icon instead, because
# the graph is read for risk first and taxonomy second.
GUARD_COLOR = {
    "derived": "#107C10",
    "gated": "#0078D4",
    "partial": "#FFB900",
    "unguarded": "#D13438",
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check_name(kind: str, name: str) -> None:
    if not NAME_RE.match(name):
        fail(f"{kind} name {name!r} violates the Fabric IQ name rule (<=26 chars, alphanumeric ends, no spaces)")


# Colour in THIS view means exactly one thing: how many routes the step is on.
# Per-route colours were tried and removed — they reused the guard palette
# (#D13438 is `unguarded` in the obligation view), so the same red meant "install"
# here and "nothing enforces this" there. The repo's SVG rule is that a role colour
# stays stable across diagrams, and route identity is already on every edge label,
# so multiplicity is what the node colour is spent on: a step shared by several
# routes is where one change lands in more than one place.
ROUTE_COUNT_COLOR = {1: "#A8B4C0", 2: "#7719AA", 3: "#E3008C"}


def route_colour(n: int) -> str:
    return ROUTE_COUNT_COLOR[min(n, 3)]


def build_paths(graph: dict) -> str:
    """A SECOND view: the service's routes, as sequences.

    Kept out of the obligation graph on purpose. Path adjacency is temporal — install
    runs migrate_state then assembles — and an obligation edge means "changing this
    obliges that". Merging them would let a reader traverse a sequence as if it were a
    dependency, which is the exact confusion `dependency_rules.md` was written to end.
    Same canonical source, different projection.

    Entities on no declared path are omitted: this view answers "what are the routes",
    and the obligation view already carries the full set.
    """
    paths = graph.get("happy_paths", {}).get("paths")
    if not paths:
        fail("graph.json declares no happy_paths — nothing to project as routes")
    by_id = {e["id"]: e for e in graph["entities"]}

    membership: dict[str, list[str]] = {}
    for pname, p in paths.items():
        for s in p["steps"]:
            membership.setdefault(s["entity"], [])
            if pname not in membership[s["entity"]]:
                membership[s["entity"]].append(pname)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<rdf:RDF",
        f'    xml:base="{BASE}"',
        '    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '    xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"',
        '    xmlns:owl="http://www.w3.org/2002/07/owl#"',
        '    xmlns:xsd="http://www.w3.org/2001/XMLSchema#"',
        f'    xmlns:ont="{BASE}">',
        "",
        f'    <owl:Ontology rdf:about="{BASE}">',
        "        <rdfs:label>agent-bios service routes</rdfs:label>",
        "        <rdfs:comment>The six paths the service actually runs, in call order. "
        "Edges are SEQUENCE, not obligation, and the label carries the route and step number. "
        "Colour is ROUTE COUNT — pale slate on one route, purple on two, magenta on three or "
        "more; a darker node is a step where one change lands on several routes. "
        "Entities on no declared route are omitted; the obligation view carries them."
        "</rdfs:comment>",
        "    </owl:Ontology>",
        "",
        "    <!-- Steps -->",
    ]

    for eid, on in membership.items():
        e = by_id[eid]
        desc = (f'{e["desc"]}. On {len(on)} route(s): {", ".join(on)}; guard {e["guard"]}')
        out += [
            "",
            f'    <owl:Class rdf:about="{BASE}{e["class"]}">',
            f'        <rdfs:label>{e["class"]}</rdfs:label>',
            f"        <rdfs:comment>{escape(desc)}</rdfs:comment>",
            f'        <ont:icon>{"🔀" if len(on) > 1 else "▸"}</ont:icon>',
            f"        <ont:color>{route_colour(len(on))}</ont:color>",
            "    </owl:Class>",
        ]

    out += ["", "    <!-- Route sequences -->"]
    props = [("entityId", lambda e, on: e["id"]), ("routes", lambda e, on: ", ".join(on)),
             ("guard", lambda e, on: e["guard"]), ("anchor", lambda e, on: e["anchor"])]
    for eid, on in membership.items():
        e = by_id[eid]
        for name, fn in props:
            out += [
                "",
                f'    <owl:DatatypeProperty rdf:about="{BASE}{e["id"]}_{name}">',
                f"        <rdfs:label>{name}</rdfs:label>",
                f'        <rdfs:domain rdf:resource="{BASE}{e["class"]}"/>',
                '        <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>',
                f"        <rdfs:comment>{escape(str(fn(e, on)))}</rdfs:comment>",
            ]
            if name == "entityId":
                out.append('        <ont:isIdentifier rdf:datatype='
                           '"http://www.w3.org/2001/XMLSchema#boolean">true</ont:isIdentifier>')
            out += ["        <ont:propertyType>string</ont:propertyType>",
                    "    </owl:DatatypeProperty>"]

    seen = set()
    for pname, p in paths.items():
        chain = [s["entity"] for s in p["steps"]]
        for i, (a, b) in enumerate(zip(chain, chain[1:]), start=1):
            if a == b:
                continue  # the same entity twice in a row is one step split, not a hop
            rid = f"{pname.replace('-', '_')}_{i}"
            if (a, b, pname) in seen:
                continue
            seen.add((a, b, pname))
            out += [
                "",
                f'    <owl:ObjectProperty rdf:about="{BASE}{rid}">',
                f'        <rdfs:label>{pname}.{i}</rdfs:label>',
                f'        <rdfs:domain rdf:resource="{BASE}{by_id[a]["class"]}"/>',
                f'        <rdfs:range rdf:resource="{BASE}{by_id[b]["class"]}"/>',
                f'        <rdfs:comment>{escape(f"step {i} of {pname}: {p["steps"][i - 1]["step"]} then {p["steps"][i]["step"]}")}</rdfs:comment>',
                "        <ont:cardinality>one-to-one</ont:cardinality>",
                f'        <ont:fromEntityId>{by_id[a]["class"]}</ont:fromEntityId>',
                f'        <ont:toEntityId>{by_id[b]["class"]}</ont:toEntityId>',
                "    </owl:ObjectProperty>",
            ]

    out += ["", "</rdf:RDF>", ""]
    return "\n".join(out)


def build(graph: dict) -> str:
    entities = graph["entities"]
    rels = graph["relationships"]
    fams = graph["families"]

    if not entities:
        fail("graph.json declares no entities — an empty subject would emit a vacuously valid ontology")

    by_id = {}
    for e in entities:
        check_name("Entity type", e["class"])
        if e["id"] in by_id:
            fail(f"duplicate entity id {e['id']!r}")
        if e["guard"] not in GUARD_COLOR:
            fail(f"entity {e['id']!r} has unknown guard {e['guard']!r}")
        if e["family"] not in fams:
            fail(f"entity {e['id']!r} has unknown family {e['family']!r}")
        by_id[e["id"]] = e

    seen_rel = set()
    for r in rels:
        if r["id"] in seen_rel:
            fail(f"duplicate relationship id {r['id']!r}")
        seen_rel.add(r["id"])
        for end in ("from", "to"):
            if r[end] not in by_id:
                fail(f"relationship {r['id']!r} points {end} at unknown entity {r[end]!r}")
        if r["card"] not in CARDINALITIES:
            fail(f"relationship {r['id']!r} has unknown cardinality {r['card']!r}")

    # The invariant the map page also asserts: unguarded <=> no P6 assertion.
    bad = [e["id"] for e in entities if (e["guard"] == "unguarded") != ("P6" not in e["pos"])]
    if bad:
        fail("guard/P6 invariant violated for: " + ", ".join(bad))

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<rdf:RDF",
        f'    xml:base="{BASE}"',
        '    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '    xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"',
        '    xmlns:owl="http://www.w3.org/2002/07/owl#"',
        '    xmlns:xsd="http://www.w3.org/2001/XMLSchema#"',
        f'    xmlns:ont="{BASE}">',
        "",
        f'    <owl:Ontology rdf:about="{BASE}">',
        "        <rdfs:label>agent-bios</rdfs:label>",
        "        <rdfs:comment>Change one concept — how far do the obligations reach, "
        "and which of them is anything actually holding? Colour is guard status: "
        "red is unguarded.</rdfs:comment>",
        "    </owl:Ontology>",
        "",
        "    <!-- Entity types -->",
    ]

    for e in entities:
        fam = fams[e["family"]]
        desc = f'{e["desc"]}. Family {e["family"]} {fam["label"]}; reaches {"/".join(e["pos"])}; guard {e["guard"]}'
        out += [
            "",
            f'    <owl:Class rdf:about="{BASE}{e["class"]}">',
            f'        <rdfs:label>{e["class"]}</rdfs:label>',
            f"        <rdfs:comment>{escape(desc)}</rdfs:comment>",
            f'        <ont:icon>{fam["icon"]}</ont:icon>',
            f'        <ont:color>{GUARD_COLOR[e["guard"]]}</ont:color>',
            "    </owl:Class>",
        ]

    out += ["", "    <!-- Data properties: the ontology's own facts, one shape for every entity -->"]
    # Same property names across every entity, same type each time — the playground
    # rejects a name that changes type between entities.
    props = [
        ("entityId", "string", True, lambda e: e["id"]),
        ("family", "string", False, lambda e: f'{e["family"]} {fams[e["family"]]["label"]}'),
        ("reaches", "string", False, lambda e: "/".join(e["pos"])),
        ("guard", "string", False, lambda e: e["guard"]),
        ("anchor", "string", False, lambda e: e["anchor"]),
    ]
    for name, _t, _ident, _fn in props:
        check_name("Property", name)

    for e in entities:
        for name, ptype, ident, fn in props:
            out += [
                "",
                f'    <owl:DatatypeProperty rdf:about="{BASE}{e["id"]}_{name}">',
                f"        <rdfs:label>{name}</rdfs:label>",
                f'        <rdfs:domain rdf:resource="{BASE}{e["class"]}"/>',
                '        <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>',
                f"        <rdfs:comment>{escape(str(fn(e)))}</rdfs:comment>",
            ]
            if ident:
                out.append(
                    '        <ont:isIdentifier rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">true</ont:isIdentifier>'
                )
            out += [
                f"        <ont:propertyType>{ptype}</ont:propertyType>",
                "    </owl:DatatypeProperty>",
            ]

    out += ["", "    <!-- Object properties: the obligation edges -->"]
    for r in rels:
        src, dst = by_id[r["from"]], by_id[r["to"]]
        desc = f'{r["desc"]}. Edge kind {r["kind"]}; enforcement {r["guard"]}'
        out += [
            "",
            f'    <owl:ObjectProperty rdf:about="{BASE}{r["id"]}">',
            f'        <rdfs:label>{r["name"]}</rdfs:label>',
            f'        <rdfs:domain rdf:resource="{BASE}{src["class"]}"/>',
            f'        <rdfs:range rdf:resource="{BASE}{dst["class"]}"/>',
            f"        <rdfs:comment>{escape(desc)}</rdfs:comment>",
            f'        <ont:cardinality>{r["card"]}</ont:cardinality>',
            f'        <ont:fromEntityId>{src["class"]}</ont:fromEntityId>',
            f'        <ont:toEntityId>{dst["class"]}</ont:toEntityId>',
            "    </owl:ObjectProperty>",
        ]

    out += ["", "</rdf:RDF>", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if the emitted RDF differs from the file on disk")
    ap.add_argument("-o", "--out", type=pathlib.Path)
    ap.add_argument("--view", choices=("obligations", "routes"), default="obligations",
                    help="obligations = the dependency graph; routes = the service's happy paths as sequences")
    args = ap.parse_args()

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    args.out = args.out or (DEFAULT_OUT if args.view == "obligations" else PATHS_OUT)
    rdf = build(graph) if args.view == "obligations" else build_paths(graph)

    if args.check:
        if not args.out.is_file():
            fail(f"{args.out} does not exist (run emit-rdf.py)")
        if args.out.read_text(encoding="utf-8") != rdf:
            fail(f"{args.out} is stale vs instances/graph.json (run emit-rdf.py)")
        print(f"emit-rdf: OK ({args.out.name} matches graph.json)")
        return

    args.out.write_text(rdf, encoding="utf-8")
    n_cls = rdf.count("<owl:Class ")
    n_obj = rdf.count("<owl:ObjectProperty ")
    print(f"emit-rdf[{args.view}]: wrote {args.out} — {n_cls} classes, {n_obj} object properties")


if __name__ == "__main__":
    main()
