#!/usr/bin/env python3
"""S5: the numbers the report is built from.

Everything here is computed from the label files and units.jsonl — no figure in the report
is typed by hand.
"""
import glob
import json
import os
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED, RAW = os.path.join(BASE, "derived"), os.path.join(BASE, "raw")
MIN_CHARS = 40

STAR_TIERS = [(1000, 3000, "1k-3k"), (3000, 10000, "3k-10k"),
              (10000, 50000, "10k-50k"), (50000, 10 ** 9, "50k+")]


def tier(stars):
    for lo, hi, name in STAR_TIERS:
        if lo <= stars < hi:
            return name
    return "<1k"


def load_units():
    return {u["unit_id"]: u for u in (json.loads(l) for l in open(os.path.join(DERIVED, "units.jsonl")))}


def load(pattern):
    out = {}
    for path in sorted(glob.glob(os.path.join(BASE, "labels", pattern))):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "unit_id" in r and "category" in r:
                out[r["unit_id"]] = r
    return out


def main():
    units = load_units()
    primary, cover = load("label-*.jsonl"), load("cover-*.jsonl")
    report = {}

    # ---- coverage probe: does the codebook hold outside the sample it came from?
    def other_breakdown(labels, name):
        kept = {u: l for u, l in labels.items()
                if u in units and units[u]["n_chars"] >= MIN_CHARS}
        dropped = len(labels) - len(kept)
        others = [l for l in kept.values() if l["category"] == "OTHER"]
        return {"labelled": len(labels), "heading_only_excluded": dropped,
                "scored": len(kept), "other": len(others),
                "other_rate": round(len(others) / len(kept), 4),
                "top_other_reasons": Counter(
                    (l.get("reason") or "")[:60].lower() for l in others).most_common(8)}

    report["primary"] = other_breakdown(primary, "primary")
    report["coverage_probe"] = other_breakdown(cover, "coverage")

    # ---- adoption by star tier: does purpose mix change with project size?
    by_tier = defaultdict(lambda: {"files": set(), "cats": defaultdict(set)})
    for uid, lab in primary.items():
        u = units.get(uid)
        if not u or u["n_chars"] < MIN_CHARS or lab["category"] == "OTHER":
            continue
        t = tier(u["stars"])
        by_tier[t]["files"].add(u["file_id"])
        by_tier[t]["cats"][lab["category"]].add(u["file_id"])
    report["adoption_by_star_tier"] = {
        t: {"n_files": len(d["files"]),
            **{c: round(len(f) / len(d["files"]), 3) for c, f in sorted(
                d["cats"].items(), key=lambda kv: -len(kv[1]))}}
        for t, d in sorted(by_tier.items(), key=lambda kv: kv[0])}

    # ---- AGENTS.md vs CLAUDE.md: are they used for different jobs?
    by_kind = defaultdict(lambda: {"files": set(), "cats": defaultdict(set)})
    for uid, lab in primary.items():
        u = units.get(uid)
        if not u or u["n_chars"] < MIN_CHARS or lab["category"] == "OTHER":
            continue
        by_kind[u["kind"]]["files"].add(u["file_id"])
        by_kind[u["kind"]]["cats"][lab["category"]].add(u["file_id"])
    report["adoption_by_kind"] = {
        k: {"n_files": len(d["files"]),
            **{c: round(len(f) / len(d["files"]), 3) for c, f in sorted(
                d["cats"].items(), key=lambda kv: -len(kv[1]))}}
        for k, d in by_kind.items()}

    # ---- how many jobs does one file actually do?
    jobs = defaultdict(set)
    for uid, lab in primary.items():
        u = units.get(uid)
        if u and u["n_chars"] >= MIN_CHARS and lab["category"] != "OTHER":
            jobs[u["file_id"]].add(lab["category"])
    counts = sorted(len(v) for v in jobs.values())
    report["categories_per_file"] = {
        "n_files": len(counts),
        "median": counts[len(counts) // 2],
        "mean": round(sum(counts) / len(counts), 2),
        "distribution": dict(sorted(Counter(counts).items())),
    }

    # ---- dual-job blocks: how often is one section doing two jobs?
    sec = [l for l in primary.values() if l.get("secondary")]
    report["dual_job_blocks"] = {
        "n": len(sec), "share": round(len(sec) / len(primary), 4),
        "top_pairs": Counter(
            tuple(sorted((l["category"], l["secondary"]))) for l in sec).most_common(8)}

    # ---- corpus-wide structure (all 12,749 files, not the sample)
    files = [json.loads(l) for l in open(os.path.join(RAW, "corpus.jsonl"))]
    sizes = sorted(f["byte_size"] for f in files)
    report["corpus"] = {
        "n_files": len(files),
        "size_p25": sizes[len(sizes) // 4], "size_median": sizes[len(sizes) // 2],
        "size_p75": sizes[3 * len(sizes) // 4], "size_p95": sizes[int(0.95 * len(sizes))],
        "size_max": sizes[-1],
    }

    json.dump(report, open(os.path.join(DERIVED, "report_stats.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
