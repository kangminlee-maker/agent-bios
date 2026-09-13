#!/usr/bin/env python3
"""Project instances/graph.json into LEXICON.md.

LEXICON was the terminology SSOT and the ontology's node layer restated it — two
canonical sites for one set of names, which is GR-1, the rule this ontology states.
So the tables move into graph.json and this emits the file. `gates/check-lexicon.py`
is untouched: it still parses LEXICON.md, so its input changes and its behaviour does
not.

Prose stays here as a template because it is exposition, not data; the four tables
(core concepts, concept homes, deprecated aliases, archive allowlist) come from the
graph. `--check` fails on any hand edit.

Faithfulness is provable rather than argued: the first emit reproduced the
hand-written LEXICON.md byte for byte, so the projection demonstrably lost nothing.

Usage: emit-lexicon.py [--check] [-o OUT]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
GRAPH = HERE / "instances" / "graph.json"
DEFAULT_OUT = REPO / "LEXICON.md"


def build(graph: dict) -> str:
    lex = graph.get("lexicon")
    if not lex:
        print("FAIL: graph.json carries no `lexicon` block", file=sys.stderr)
        sys.exit(1)
    for key in ("core_concepts", "homes", "deprecated", "archive_allowlist"):
        if not lex.get(key):
            print(f"FAIL: lexicon.{key} is empty — a terminology gate over an empty "
                  f"subject would pass vacuously", file=sys.stderr)
            sys.exit(1)

    core = "\n".join(
        f'| {c["concept"]} | {c["canonical_term"]} | {c["trigger"]} | {c["bindings"]} |'
        for c in lex["core_concepts"])
    homes = "\n".join(
        f'| {h["concept"]} | `{h["slug"]}` | `{h["home"]}` |' for h in lex["homes"])
    deprecated = "\n".join(
        f'| `{d["token"]}` | `{d["replaced_by"]}` | {d["reason"]} |' for d in lex["deprecated"])
    archive = "\n".join(f'- {a["display"]}' for a in lex["archive_allowlist"])

    return f"""# LEXICON — canonical terminology (operated)

Single source of truth for the repo's shared, lasting concept names. Every
concept below has **one** canonical term and declared concrete bindings
(paths, config keys, variable/function prefixes, triggers). A binding may retain
an existing implementation name when its entry explains why. Deprecated aliases
must not appear as live identifiers where the denylist enforces them — the
`gates/check-lexicon.py` gate enforces this (it fails if a deprecated token
resurfaces outside the archive allowlist, and fails if any token it enforces
is missing from this file, so the two can never drift).

Why operate a lexicon: it keeps the concept graph compact and grep-navigable,
so a rename or a new feature reuses the established name instead of minting a
near-duplicate — fewer name-driven bugs, smoother maintenance.

한국어 요약: 저장소의 공유 개념명을 한 곳에서 관리한다. 개념마다 정규명은
하나, 그 정규명이 실제 식별자(경로·설정키·변수/함수 접두사·트리거)에 어떻게
묶이는지 명시한다. deprecated 별칭은 라이브 코드에 다시 나타나면 게이트가
막는다.

## Core concepts

| Concept | Canonical term | Trigger | Bound identifiers / paths |
| --- | --- | --- | --- |
{core}

Semantic model: users **LEARN** (capture a learning) → curators **DISTILL**
(reduce collected learnings) → **Instructions** are redistributed. `learning` is
the artifact and stays valid wherever it means the artifact (e.g. "the
learning ledger", "placed learning items"); only the compound proper noun of
the heavy subsystem changed.

## Concept homes (gated)

A concept whose files are scattered is findable only by memory. Each concept below
names one canonical **home**; any machinery file whose path carries that concept's
**slug** must live under it. `gates/check-lexicon.py` enforces this, which is what
keeps the layout guessable from a concept name instead of from a translation table.

Scope: machinery only. The instruction trees (`claude/`, `codex/`, `ko/`) are organized by
target because the harness loads fixed paths, `packages/` is organized by package
identity for the same reason — a package carries its own manifest and prose, so the
concept names repeat inside every package root — and `design/`, `benchmarks/` hold dated
records. A slug appearing in any of those is a mention, not a home, so they are exempt.

| Concept | Path slug | Home |
| --- | --- | --- |
{homes}

## Deprecated aliases (must not appear as live identifiers)

The gate forbids these exact tokens outside the archive allowlist. Bare
`learning` / `learnings` (the artifact noun) is NOT deprecated — only the
compound and identifier forms below are.

| Deprecated token | Replaced by | Reason |
| --- | --- | --- |
{deprecated}

Bare `distillation` is intentionally NOT gated: the heavy pipeline legitimately
uses "upward distillation" (deriving a principle). Only the specific
light-flow identifier tokens above are forbidden.

## Archive allowlist (deprecated tokens tolerated as dated history)

Historical design records are dated snapshots; their prose keeps the term as
written at the time. The gate ignores deprecated tokens under these paths:

{archive}

When you add a concept: find the nearest existing term here first; reuse,
extend, rename, or split explicitly, and update this file in the same change.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("-o", "--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    doc = build(graph)

    if args.check:
        if not args.out.is_file():
            print(f"FAIL: {args.out} does not exist (run emit-lexicon.py)", file=sys.stderr)
            sys.exit(1)
        if args.out.read_text(encoding="utf-8") != doc:
            print(f"FAIL: {args.out} is stale vs instances/graph.json (run emit-lexicon.py)",
                  file=sys.stderr)
            sys.exit(1)
        print("emit-lexicon: OK (LEXICON.md matches graph.json)")
        return

    args.out.write_text(doc, encoding="utf-8")
    lex = graph["lexicon"]
    print(f"emit-lexicon: wrote {args.out} — {len(lex['core_concepts'])} concepts, "
          f"{len(lex['homes'])} homes, {len(lex['deprecated'])} deprecated tokens")


if __name__ == "__main__":
    main()
