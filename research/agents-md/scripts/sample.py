#!/usr/bin/env python3
"""S4a: draw the stratified samples and materialize reader packets.

Strata: file kind (AGENTS/CLAUDE) x star bucket x qualifier class. One representative per
identical-text cluster, so a widely copy-pasted template cannot dominate a stratum.
Selection is seeded by a hash of the file id, so re-running reproduces the same sample.

  sample.py open   45   -> derived/sample_open.jsonl   + packets/open/*.md
  sample.py closed 180  -> derived/sample_closed.jsonl + packets/closed/*.md
"""
import hashlib
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, DERIVED = os.path.join(BASE, "raw"), os.path.join(BASE, "derived")

STAR_BUCKETS = [(1000, 3000), (3000, 10000), (10000, 50000), (50000, 10**9)]


def star_bucket(n):
    for lo, hi in STAR_BUCKETS:
        if lo <= n < hi:
            return f"{lo//1000}k-{hi//1000 if hi < 10**9 else 'inf'}k"
    return "sub1k"


def qual_class(q):
    return "both" if len(q) > 1 else q[0]


def rank(fid, salt):
    return hashlib.blake2b(f"{salt}:{fid}".encode(), digest_size=8).hexdigest()


def main(which, n):
    files = [json.loads(l) for l in open(os.path.join(RAW, "corpus.jsonl"))]
    dupes = json.load(open(os.path.join(DERIVED, "dupes.json")))
    by_id = {f["id"]: f for f in files}
    drop = set()
    for cluster in dupes["identical_files"]:
        # keep the most-starred copy of a propagated template, not an arbitrary one, so the
        # surviving representative lands in the stratum a reader would consider authoritative
        keep = max(cluster, key=lambda i: (by_id[i]["stars"], i))
        drop.update(set(cluster) - {keep})
    pool = [f for f in files if f["id"] not in drop]

    strata = defaultdict(list)
    for f in pool:
        strata[(f["kind"], star_bucket(f["stars"]), qual_class(f["qualifies"]))].append(f)

    # proportional allocation with a floor of 2 per non-empty stratum, capped by stratum size
    total = len(pool)
    alloc, chosen = {}, []
    for k, group in strata.items():
        alloc[k] = min(len(group), max(2, round(n * len(group) / total)))
    # trim/grow to hit n, largest strata absorb the difference
    order = sorted(strata, key=lambda k: -len(strata[k]))
    while sum(alloc.values()) > n:
        for k in reversed(order):
            if alloc[k] > 2 and sum(alloc.values()) > n:
                alloc[k] -= 1
    while sum(alloc.values()) < n:
        for k in order:
            if alloc[k] < len(strata[k]) and sum(alloc.values()) < n:
                alloc[k] += 1
    for k, group in strata.items():
        group.sort(key=lambda f: rank(f["id"], which))
        chosen.extend(group[:alloc[k]])

    chosen.sort(key=lambda f: -f["stars"])
    out = os.path.join(DERIVED, f"sample_{which}.jsonl")
    with open(out, "w") as fh:
        for f in chosen:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    print(f"{which}: pool={total} (dropped {len(drop)} dup) -> sampled {len(chosen)}")
    for k in sorted(alloc, key=lambda k: -alloc[k]):
        if alloc[k]:
            print(f"  {k}: {alloc[k]}/{len(strata[k])}")
    print(f"-> {out}")


def packets(which, per_packet):
    """Split a sample into reader packets, one markdown file per packet."""
    src = os.path.join(DERIVED, f"sample_{which}.jsonl")
    files = [json.loads(l) for l in open(src)]
    pdir = os.path.join(BASE, "packets", which)
    os.makedirs(pdir, exist_ok=True)
    for i in range(0, len(files), per_packet):
        chunk = files[i:i + per_packet]
        path = os.path.join(pdir, f"packet-{i//per_packet:02d}.md")
        with open(path, "w") as fh:
            for f in chunk:
                fh.write(f'\n\n===== FILE {f["id"]} | stars={f["stars"]} '
                         f'followers={f.get("owner_followers")} lang={f.get("language")} '
                         f'bytes={f["byte_size"]} =====\n\n')
                fh.write(f["text"])
        print(f"  {path}: {len(chunk)} files")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "packets":
        packets(sys.argv[2], int(sys.argv[3]))
    else:
        main(cmd, int(sys.argv[2]))
