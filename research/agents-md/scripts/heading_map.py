#!/usr/bin/env python3
"""S4d: the full-corpus check that the sampled codebook did not miss a purpose.

Precise labelling runs on a stratified sample, so a category present only outside that sample
would go unseen. The heading vocabulary is small even when the corpus is not, so mapping every
frequent heading to a codebook category covers the whole corpus cheaply and exposes any purpose
the codebook has no home for.

  heading_map.py packet 400   -> packets/headings.md  (headings to map, with real frequencies)
  heading_map.py apply        -> derived/heading_coverage.json
"""
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED = os.path.join(BASE, "derived")


def packet(n):
    headings = json.load(open(os.path.join(DERIVED, "headings.json")))
    total_files = json.load(open(os.path.join(DERIVED, "stats.json")))["n_files"]
    top = [h for h in headings if h["heading_norm"] and h["heading_norm"] != "preamble"][:n]
    covered = sum(h["n_units"] for h in top)
    all_units = sum(h["n_units"] for h in headings)

    out = os.path.join(BASE, "packets", "headings.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(f"# Heading vocabulary — top {len(top)} of {len(headings)} distinct headings\n\n")
        f.write(f"These cover {covered}/{all_units} units ({covered/all_units:.1%}) across "
                f"{total_files} files.\n\n")
        f.write("`n_files` = how many distinct files use this heading. Map each to one codebook\n"
                "category id, or `OTHER` if the codebook has no home for the purpose it names.\n\n")
        f.write("| heading (normalized) | n_files | n_units | most common raw forms |\n")
        f.write("|---|---|---|---|\n")
        for h in top:
            raw = ", ".join(f'"{r[0]}"' for r in h["top_raw"][:2])
            f.write(f'| {h["heading_norm"]} | {h["n_files"]} | {h["n_units"]} | {raw} |\n')
    print(f"{out}: {len(top)} headings covering {covered/all_units:.1%} of units")


def apply():
    headings = {h["heading_norm"]: h for h in json.load(open(os.path.join(DERIVED, "headings.json")))}
    mapping = {}
    path = os.path.join(BASE, "labels", "heading-map.jsonl")
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        rec = json.loads(line)
        mapping[rec["heading_norm"]] = rec["category"]

    cat = defaultdict(lambda: {"n_files": 0, "n_units": 0, "star_sum": 0, "headings": []})
    mapped_units = unmapped_units = 0
    for norm, h in headings.items():
        if norm in mapping:
            c = cat[mapping[norm]]
            c["n_files"] += h["n_files"]
            c["n_units"] += h["n_units"]
            c["star_sum"] += h["star_sum"]
            if len(c["headings"]) < 12:
                c["headings"].append(norm)
            mapped_units += h["n_units"]
        else:
            unmapped_units += h["n_units"]

    rows = sorted(({"category": k, **{kk: vv for kk, vv in v.items()}} for k, v in cat.items()),
                  key=lambda r: -r["n_files"])
    out = {"mapped_units": mapped_units, "unmapped_units": unmapped_units,
           "mapped_share": round(mapped_units / (mapped_units + unmapped_units), 4),
           "categories": rows}
    json.dump(out, open(os.path.join(DERIVED, "heading_coverage.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"mapped {out['mapped_share']:.1%} of units by heading")
    for r in rows:
        print(f"  {r['category']:34s} files={r['n_files']:6d} units={r['n_units']:6d}")


if __name__ == "__main__":
    if sys.argv[1] == "packet":
        packet(int(sys.argv[2]) if len(sys.argv) > 2 else 400)
    else:
        apply()
