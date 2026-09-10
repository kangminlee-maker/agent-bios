#!/usr/bin/env python3
"""S4b: cut the closed-coding sample's units into labelling batches.

  make_label_batches.py closed 150   -> packets/units/batch-NN.jsonl
  make_label_batches.py audit  150   -> packets/units/audit-00.jsonl  (random draw for kappa)

The audit draw is a random subset of the SAME units the primary batches cover, so a second
analyst's labels can be compared unit-for-unit.
"""
import hashlib
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED, RAW = os.path.join(BASE, "derived"), os.path.join(BASE, "raw")
PDIR = os.path.join(BASE, "packets", "units")

FIELDS = ("unit_id", "full_name", "path", "heading", "text")


def load_sample_units(which="closed"):
    ids = {json.loads(l)["id"] for l in open(os.path.join(DERIVED, f"sample_{which}.jsonl"))}
    units = [json.loads(l) for l in open(os.path.join(DERIVED, "units.jsonl"))
             if json.loads(l)["file_id"] in ids]
    units.sort(key=lambda u: u["unit_id"])
    return units


def coverage(n, per_batch):
    """Uniform random draw from the WHOLE corpus, excluding the stratified sample's files.

    The heading vocabulary is too long-tailed to verify coverage by heading alone (60,601 of
    71,913 headings appear in a single file), so codebook coverage is tested directly: if a
    purpose exists outside the sample that the codebook cannot express, it shows up here as
    an elevated OTHER rate.
    """
    os.makedirs(PDIR, exist_ok=True)
    seen = {json.loads(l)["id"] for l in open(os.path.join(DERIVED, "sample_closed.jsonl"))}
    pool = [json.loads(l) for l in open(os.path.join(DERIVED, "units.jsonl"))]
    pool = [u for u in pool if u["file_id"] not in seen]
    pool.sort(key=lambda u: hashlib.blake2b(("cov:" + u["unit_id"]).encode(), digest_size=8).hexdigest())
    draw = pool[:n]
    batches = [draw[i:i + per_batch] for i in range(0, len(draw), per_batch)]
    for i, chunk in enumerate(batches):
        with open(os.path.join(PDIR, f"cover-{i:02d}.jsonl"), "w") as f:
            for u in chunk:
                f.write(json.dumps({k: u[k] for k in FIELDS}, ensure_ascii=False) + "\n")
    print(f"coverage draw: {len(draw)} units from {len(pool)} out-of-sample units "
          f"({len({u['file_id'] for u in draw})} files) -> {len(batches)} batches")


def main(which, per_batch):
    os.makedirs(PDIR, exist_ok=True)
    units = load_sample_units("closed")
    if which == "audit":
        # deterministic random draw over the same population the primary pass labels
        units = sorted(units, key=lambda u: hashlib.blake2b(
            ("audit:" + u["unit_id"]).encode(), digest_size=8).hexdigest())[:per_batch]
        path = os.path.join(PDIR, "audit-00.jsonl")
        with open(path, "w") as f:
            for u in units:
                f.write(json.dumps({k: u[k] for k in FIELDS}, ensure_ascii=False) + "\n")
        print(f"{path}: {len(units)} units")
        return

    batches = [units[i:i + per_batch] for i in range(0, len(units), per_batch)]
    for i, chunk in enumerate(batches):
        path = os.path.join(PDIR, f"batch-{i:02d}.jsonl")
        with open(path, "w") as f:
            for u in chunk:
                f.write(json.dumps({k: u[k] for k in FIELDS}, ensure_ascii=False) + "\n")
    tot_chars = sum(len(u["text"]) for u in units)
    print(f"{len(units)} units from {len({u['file_id'] for u in units})} files "
          f"-> {len(batches)} batches of <={per_batch} ({tot_chars/len(batches)/1000:.0f}k chars each)")


if __name__ == "__main__":
    if sys.argv[1] == "coverage":
        coverage(int(sys.argv[2]), int(sys.argv[3]))
    else:
        main(sys.argv[1], int(sys.argv[2]))
