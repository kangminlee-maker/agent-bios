#!/usr/bin/env python3
"""S4c: fold labels back into frequency, adoption and agreement tables.

  aggregate.py score   labels/*.jsonl   -> derived/category_stats.json
  aggregate.py agree   labels/audit-*.jsonl vs primary labels -> inter-rater agreement
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED = os.path.join(BASE, "derived")

# 10.1% of units are a heading with no body — a structural container whose content lives in its
# subsections. They carry no instruction, so counting them inflates OTHER and dilutes every real
# category. Excluded from the statistics; the exclusion is reported, not silent.
MIN_CHARS = 40


def load_units():
    units = {}
    for line in open(os.path.join(DERIVED, "units.jsonl")):
        u = json.loads(line)
        units[u["unit_id"]] = u
    return units


def load_labels(pattern):
    out = {}
    for path in sorted(glob.glob(os.path.join(BASE, "labels", pattern))):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "unit_id" in rec and "category" in rec:
                out[rec["unit_id"]] = rec
    return out


def score(pattern="label-*.jsonl"):
    units, labels = load_units(), load_labels(pattern)
    missing = [uid for uid in labels if uid not in units]
    skipped = sum(1 for uid in labels if uid in units and units[uid]["n_chars"] < MIN_CHARS)
    print(f"labels={len(labels)} (unmatched unit_ids: {len(missing)}; "
          f"heading-only units excluded: {skipped})")

    cat = defaultdict(lambda: {"n_units": 0, "n_files": set(), "n_repos": set(), "star_sum": 0,
                               "by_kind": Counter(), "low_conf": 0, "chars": 0})
    for uid, lab in labels.items():
        u = units.get(uid)
        if not u or u["n_chars"] < MIN_CHARS:
            continue
        c = cat[lab["category"]]
        c["n_units"] += 1
        c["n_files"].add(u["file_id"])
        c["n_repos"].add(u["full_name"])
        c["star_sum"] += u["stars"]
        c["by_kind"][u["kind"]] += 1
        c["chars"] += u["n_chars"]
        if lab.get("confidence") == "low":
            c["low_conf"] += 1

    labelled_files = {units[uid]["file_id"] for uid in labels
                      if uid in units and units[uid]["n_chars"] >= MIN_CHARS}
    total_units = sum(c["n_units"] for c in cat.values())
    rows = []
    for name, c in cat.items():
        rows.append({
            "category": name,
            "n_units": c["n_units"],
            "share_units": round(c["n_units"] / total_units, 4) if total_units else 0,
            "n_files": len(c["n_files"]),
            "file_adoption": round(len(c["n_files"]) / len(labelled_files), 4) if labelled_files else 0,
            "n_repos": len(c["n_repos"]),
            "mean_stars": round(c["star_sum"] / c["n_units"]) if c["n_units"] else 0,
            "mean_chars": round(c["chars"] / c["n_units"]) if c["n_units"] else 0,
            "agents_vs_claude": dict(c["by_kind"]),
            "low_confidence": c["low_conf"],
        })
    rows.sort(key=lambda r: -r["file_adoption"])
    out = {"n_labelled_units": total_units, "n_labelled_files": len(labelled_files), "categories": rows}
    json.dump(out, open(os.path.join(DERIVED, "category_stats.json"), "w"), ensure_ascii=False, indent=1)

    w = max(len(r["category"]) for r in rows) if rows else 10
    print(f"{'category'.ljust(w)}  units  share  files  adopt  meanStars  lowConf")
    for r in rows:
        print(f"{r['category'].ljust(w)}  {r['n_units']:5d}  {r['share_units']:.3f}  "
              f"{r['n_files']:5d}  {r['file_adoption']:.3f}  {r['mean_stars']:9d}  {r['low_confidence']:6d}")
    return out


def agree():
    units = load_units()
    primary, audit = load_labels("label-*.jsonl"), load_labels("audit-*.jsonl")
    shared = {u for u in set(primary) & set(audit)
              if u in units and units[u]["n_chars"] >= MIN_CHARS}
    if not shared:
        print("no overlapping units between primary and audit label sets")
        return
    hits = sum(1 for uid in shared if primary[uid]["category"] == audit[uid]["category"])
    obs = hits / len(shared)

    # Cohen's kappa against chance agreement from each rater's own marginals
    cats = sorted({primary[u]["category"] for u in shared} | {audit[u]["category"] for u in shared})
    p_marg = Counter(primary[u]["category"] for u in shared)
    a_marg = Counter(audit[u]["category"] for u in shared)
    exp = sum((p_marg[c] / len(shared)) * (a_marg[c] / len(shared)) for c in cats)
    kappa = (obs - exp) / (1 - exp) if exp < 1 else 1.0
    print(f"double-labelled units: {len(shared)}")
    print(f"observed agreement: {obs:.3f}   expected-by-chance: {exp:.3f}   Cohen's kappa: {kappa:.3f}")

    conf = Counter((primary[u]["category"], audit[u]["category"]) for u in shared if
                   primary[u]["category"] != audit[u]["category"])
    print("\ntop disagreements (primary -> audit):")
    for (a, b), n in conf.most_common(12):
        print(f"  {n:3d}  {a} -> {b}")
    json.dump({"n": len(shared), "observed": obs, "expected": exp, "kappa": kappa,
               "disagreements": [{"primary": a, "audit": b, "n": n} for (a, b), n in conf.most_common()]},
              open(os.path.join(DERIVED, "agreement.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "score":
        score()
    elif cmd == "agree":
        agree()
