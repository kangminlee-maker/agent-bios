#!/usr/bin/env python3
"""S3: turn raw files into analysis units and measure the corpus structurally.

Outputs
  units.jsonl        one record per heading section (the labelling unit)
  headings.json      normalized heading vocabulary, star-weighted  <- the full-corpus check
  dupes.json         near-duplicate clusters (template propagation) so frequency isn't inflated
  stats.json         corpus shape
"""
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "raw")
DERIVED = os.path.join(BASE, "derived")
os.makedirs(DERIVED, exist_ok=True)

FENCE = re.compile(r"^\s*(```|~~~)")
ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


def split_sections(text):
    """Fence-aware ATX split. Returns [(level, heading, body)] with a preamble at level 0."""
    lines = text.splitlines()
    sections, cur = [], {"level": 0, "heading": "(preamble)", "body": []}
    in_fence, fence_tok = False, None
    for line in lines:
        m_fence = FENCE.match(line)
        if m_fence:
            tok = m_fence.group(1)
            if not in_fence:
                in_fence, fence_tok = True, tok
            elif tok == fence_tok:
                in_fence = False
            cur["body"].append(line)
            continue
        if in_fence:
            cur["body"].append(line)
            continue
        m = ATX.match(line)
        if m:
            sections.append(cur)
            cur = {"level": len(m.group(1)), "heading": m.group(2).strip(), "body": []}
        else:
            cur["body"].append(line)
    sections.append(cur)
    return [s for s in sections if s["heading"] != "(preamble)" or "".join(s["body"]).strip()]


MAX_UNIT_CHARS = 3000
TARGET_UNIT_CHARS = 1500


def split_long(body):
    """Files that use no headings (or one huge section) would otherwise become a single
    unlabelable unit. Break oversized bodies at blank lines, never inside a fence."""
    if len(body) <= MAX_UNIT_CHARS:
        return [body]
    blocks, cur, in_fence, fence_tok = [], [], False, None
    for line in body.splitlines():
        m = FENCE.match(line)
        if m:
            tok = m.group(1)
            if not in_fence:
                in_fence, fence_tok = True, tok
            elif tok == fence_tok:
                in_fence = False
        if not line.strip() and not in_fence and cur:
            blocks.append("\n".join(cur))
            cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))

    parts, acc = [], ""
    for b in blocks:
        if acc and len(acc) + len(b) > TARGET_UNIT_CHARS:
            parts.append(acc)
            acc = b
        else:
            acc = f"{acc}\n\n{b}" if acc else b
    if acc.strip():
        parts.append(acc)
    return [p for p in parts if p.strip()] or [body]


def norm_heading(h):
    h = unicodedata.normalize("NFKC", h)
    h = EMOJI.sub("", h)
    h = re.sub(r"[`*_~\[\]()]", "", h)
    h = re.sub(r"^\s*[\d.]+\s+", "", h)          # "1.2 Foo" -> "Foo"
    h = re.sub(r"[^\w\s/&+-]", " ", h, flags=re.UNICODE)
    return re.sub(r"\s+", " ", h).strip().lower()


def norm_text(t):
    t = unicodedata.normalize("NFKC", t).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t)).strip()


def shingles(t, k=8):
    toks = t.split()
    return {hashlib.blake2b(" ".join(toks[i:i + k]).encode(), digest_size=8).digest()
            for i in range(max(1, len(toks) - k + 1))}


def main():
    files = [json.loads(l) for l in open(os.path.join(RAW, "corpus.jsonl"))]
    print(f"corpus: {len(files)} files")

    units_path = os.path.join(DERIVED, "units.jsonl")
    heading_stat = defaultdict(lambda: {"n_units": 0, "n_files": 0, "repos": [], "stars": 0, "raw": Counter()})
    body_hash = defaultdict(list)
    file_hash = defaultdict(list)
    n_units = 0
    per_file_units = Counter()

    with open(units_path, "w") as out:
        for f in files:
            file_hash[hashlib.blake2b(norm_text(f["text"]).encode(), digest_size=16).hexdigest()].append(f["id"])
            seen_headings = set()
            for si, sec in enumerate(split_sections(f["text"])):
                body = "\n".join(sec["body"]).strip()
                if not body and sec["level"] == 0:
                    continue
                nh = norm_heading(sec["heading"])
                parts = split_long(body)
                for pi, part in enumerate(parts):
                    uid = f'{f["id"]}#{si}' + (f".{pi}" if len(parts) > 1 else "")
                    out.write(json.dumps({
                        "unit_id": uid,
                        "file_id": f["id"],
                        "full_name": f["full_name"],
                        "path": f["path"],
                        "kind": f["kind"],
                        "stars": f["stars"],
                        "owner_followers": f.get("owner_followers"),
                        "qualifies": f["qualifies"],
                        "language": f.get("language"),
                        "level": sec["level"],
                        "heading": sec["heading"],
                        "heading_norm": nh,
                        "part": pi if len(parts) > 1 else None,
                        "n_chars": len(part),
                        "text": part,
                    }, ensure_ascii=False) + "\n")
                    n_units += 1
                    per_file_units[f["id"]] += 1
                    st = heading_stat[nh]
                    st["n_units"] += 1
                    st["stars"] += f["stars"]
                    st["raw"][sec["heading"]] += 1
                    if nh not in seen_headings:
                        st["n_files"] += 1
                        seen_headings.add(nh)
                    if len(st["repos"]) < 5:
                        st["repos"].append(f["full_name"])
                    if len(part) >= 120:
                        body_hash[hashlib.blake2b(norm_text(part).encode(), digest_size=16).hexdigest()].append(uid)

    headings = sorted(
        ({"heading_norm": k, "n_units": v["n_units"], "n_files": v["n_files"],
          "star_sum": v["stars"], "top_raw": v["raw"].most_common(3), "examples": v["repos"]}
         for k, v in heading_stat.items()),
        key=lambda d: -d["n_files"])
    json.dump(headings, open(os.path.join(DERIVED, "headings.json"), "w"), ensure_ascii=False, indent=1)

    dup_files = {h: ids for h, ids in file_hash.items() if len(ids) > 1}
    dup_secs = {h: ids for h, ids in body_hash.items() if len(ids) > 1}
    json.dump({"identical_files": sorted(dup_files.values(), key=len, reverse=True)[:200],
               "identical_sections": sorted(dup_secs.values(), key=len, reverse=True)[:200]},
              open(os.path.join(DERIVED, "dupes.json"), "w"), ensure_ascii=False, indent=1)

    stats = {
        "n_files": len(files),
        "n_units": n_units,
        "n_repos": len({f["full_name"] for f in files}),
        "by_kind": Counter(f["kind"] for f in files),
        "by_qualifier": Counter("+".join(f["qualifies"]) for f in files),
        "distinct_headings": len(heading_stat),
        "headings_covering_80pct_units": sum(
            1 for _ in _prefix_covering(headings, n_units, 0.8)),
        "files_in_identical_clusters": sum(len(v) for v in dup_files.values()),
        "sections_in_identical_clusters": sum(len(v) for v in dup_secs.values()),
        "median_units_per_file": sorted(per_file_units.values())[len(per_file_units) // 2] if per_file_units else 0,
        "median_bytes": sorted(f["byte_size"] for f in files)[len(files) // 2] if files else 0,
    }
    json.dump(stats, open(os.path.join(DERIVED, "stats.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


def _prefix_covering(headings, total, frac):
    acc = 0
    for h in headings:
        if acc >= total * frac:
            return
        acc += h["n_units"]
        yield h


if __name__ == "__main__":
    main()
