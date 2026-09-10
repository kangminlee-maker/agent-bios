#!/usr/bin/env python3
"""Which purposes are transferable (global-suitable) and which are repo-bound?

Empirical proxy: a block whose exact text reappears in an UNRELATED repository is, by
demonstration, not tied to any one codebase — someone carried it across. A block that exists
in exactly one repo in a 12,749-file corpus is repo-bound.

Whole-file clones are excluded first: copying someone's entire AGENTS.md proves nothing about
any individual block's transferability, it just propagates the file. What remains is
section-level transfer, which is the signal we want.
"""
import glob
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED, RAW = os.path.join(BASE, "derived"), os.path.join(BASE, "raw")
MIN_CHARS = 40


def norm(t):
    t = unicodedata.normalize("NFKC", t).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t)).strip()


def main():
    dupes = json.load(open(os.path.join(DERIVED, "dupes.json")))
    cloned_files = {fid for cluster in dupes["identical_files"] for fid in cluster}

    units, by_hash = {}, defaultdict(set)
    for line in open(os.path.join(DERIVED, "units.jsonl")):
        u = json.loads(line)
        units[u["unit_id"]] = u
        if u["n_chars"] < MIN_CHARS or u["file_id"] in cloned_files:
            continue
        h = hashlib.blake2b(norm(u["text"]).encode(), digest_size=16).hexdigest()
        by_hash[h].add(u["full_name"])
        u["_h"] = h

    labels = {}
    for path in sorted(glob.glob(os.path.join(BASE, "labels", "label-*.jsonl")) +
                       glob.glob(os.path.join(BASE, "labels", "cover-*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "unit_id" in r and "category" in r:
                labels[r["unit_id"]] = r

    stat = defaultdict(lambda: {"n": 0, "shared": 0, "repos": Counter()})
    for uid, lab in labels.items():
        u = units.get(uid)
        if not u or "_h" not in u or lab["category"] == "OTHER":
            continue
        s = stat[lab["category"]]
        s["n"] += 1
        n_repos = len(by_hash[u["_h"]])
        if n_repos > 1:
            s["shared"] += 1
            s["repos"][n_repos] += 1

    rows = [{"category": c,
             "n_units": d["n"],
             "cross_repo_share": round(d["shared"] / d["n"], 4) if d["n"] else 0,
             "n_shared": d["shared"],
             "max_repos_one_block": max(d["repos"], default=1)}
            for c, d in stat.items()]
    rows.sort(key=lambda r: -r["cross_repo_share"])

    total_n = sum(r["n_units"] for r in rows)
    total_s = sum(r["n_shared"] for r in rows)
    print(f"labelled non-OTHER units scored: {total_n} "
          f"(whole-file clones excluded: {len(cloned_files)} files)")
    print(f"overall cross-repo share: {total_s/total_n:.1%}\n")
    print(f"{'category':24s}{'units':>7s}{'cross-repo':>12s}{'shared':>8s}{'max repos':>11s}")
    for r in rows:
        print(f"{r['category']:24s}{r['n_units']:7d}{r['cross_repo_share']:11.1%}"
              f"{r['n_shared']:8d}{r['max_repos_one_block']:11d}")

    json.dump(rows, open(os.path.join(DERIVED, "scope_split.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
