#!/usr/bin/env python3
"""S1: enumerate the two qualifying populations, deterministically.

  A) repositories with stars >= 1000  (active since 2025-01-01, non-fork, non-archived)
  B) users with followers >= 1000

Both GitHub search endpoints cap a single query at 1000 results, so each range is
split recursively until it fits under the cap. The /search/* rate limit (30/min)
is shared by both endpoints, so the two passes run sequentially in one process.
"""
import json
import math
import os
import subprocess
import sys
import time

import requests

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")
os.makedirs(OUT, exist_ok=True)

TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
S = requests.Session()
S.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "agents-md-research",
})

PUSHED_SINCE = "2025-01-01"
SPACING = 2.2  # 30 req/min shared search budget


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def search(endpoint, q, page=1, per_page=100):
    for attempt in range(8):
        r = S.get(f"https://api.github.com/search/{endpoint}",
                  params={"q": q, "per_page": per_page, "page": page})
        time.sleep(SPACING)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            wait = int(r.headers.get("retry-after", 0)) or 2 ** attempt * 5
            log(f"  throttled ({r.status_code}); sleeping {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 422:
            log(f"  422 on q={q!r}: {r.text[:200]}")
            return {"total_count": 0, "items": []}
        r.raise_for_status()
    raise RuntimeError(f"search failed after retries: {endpoint} {q}")


def collect(endpoint, q_for, lo, hi, sink, seen):
    """Recursively split [lo, hi] until total_count <= 1000, then paginate."""
    q = q_for(lo, hi)
    total = search(endpoint, q, per_page=1)["total_count"]
    if total == 0:
        return
    if total > 1000 and lo < hi:
        # geometric midpoint: the star/follower distribution is power-law
        mid = int(math.sqrt(lo * hi))
        mid = min(max(mid, lo), hi - 1)
        collect(endpoint, q_for, lo, mid, sink, seen)
        collect(endpoint, q_for, mid + 1, hi, sink, seen)
        return
    if total > 1000:
        log(f"  !! un-splittable bucket {lo}..{hi} has {total} > 1000; truncating")
    pages = min(10, (min(total, 1000) + 99) // 100)
    got = 0
    for page in range(1, pages + 1):
        for item in search(endpoint, q, page=page)["items"]:
            key = item.get("full_name") or item.get("login")
            if key in seen:
                continue
            seen.add(key)
            sink(item)
            got += 1
    log(f"  [{lo}..{hi}] total={total} kept={got} cumulative={len(seen)}")


def enumerate_repos(lo=1000, ceiling=1000000, target=800):
    """Sequential adaptive sweep upward through the star axis.

    Page 1 already carries total_count, so the window probe and the first 100 results are the
    same request — unlike a recursive bisection, no request is spent purely on counting and
    every response contributes records. Window width is re-derived from the observed density
    after each step to land near `target` results per query, comfortably under the 1000 cap.
    """
    path = os.path.join(OUT, "repos.jsonl")
    seen = set()
    empty_streak = 0
    w = 25  # near 1000 stars the distribution is dense; widen from evidence
    with open(path, "w") as f:
        def sink(items):
            n = 0
            for it in items:
                if it["full_name"] in seen:
                    continue
                seen.add(it["full_name"])
                f.write(json.dumps({
                    "full_name": it["full_name"],
                    "owner": it["owner"]["login"],
                    "owner_type": it["owner"]["type"],
                    "stars": it["stargazers_count"],
                    "pushed_at": it["pushed_at"],
                    "language": it.get("language"),
                    "license": (it.get("license") or {}).get("spdx_id"),
                    "default_branch": it.get("default_branch"),
                    "source": "stars",
                }) + "\n")
                n += 1
            return n

        while lo <= ceiling:
            hi = min(lo + w - 1, ceiling)
            q = f"stars:{lo}..{hi} pushed:>{PUSHED_SINCE} fork:false archived:false"
            first = search("repositories", q, page=1)
            total = first["total_count"]
            sink(first["items"])  # valid records even if we end up shrinking the window

            if total > 1000 and hi > lo:
                w = max(1, int(w * target / total))
                log(f"  [{lo}..{hi}] total={total} > cap; shrinking window to {w}")
                continue

            for page in range(2, min(10, (min(total, 1000) + 99) // 100) + 1):
                sink(search("repositories", q, page=page)["items"])
            log(f"  [{lo}..{hi}] total={total} cumulative={len(seen)}")

            if total == 0:
                empty_streak += 1
                if empty_streak >= 3 and lo > 200000:
                    log(f"  three empty windows past {lo} stars; stopping")
                    break
                w = max(w * 8, 64)
            else:
                empty_streak = 0
                w = max(1, min(int(w * target / total), 200000))
            lo = hi + 1
    log(f"S1A done: {len(seen)} repos -> {path}")
    return len(seen)


def enumerate_users():
    path = os.path.join(OUT, "users.jsonl")
    seen = set()
    with open(path, "w") as f:
        def sink(it):
            f.write(json.dumps({"login": it["login"], "id": it["id"], "source": "followers"}) + "\n")
        collect("users",
                lambda lo, hi: f"followers:{lo}..{hi} type:user",
                1000, 1000000, sink, seen)
    log(f"S1B done: {len(seen)} users -> {path}")
    return len(seen)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    if which in ("all", "users"):
        log("== S1B: users with followers >= 1000 ==")
        enumerate_users()
    if which in ("all", "repos"):
        log("== S1A: repos with stars >= 1000 ==")
        enumerate_repos()
    log(f"elapsed {time.time() - t0:.0f}s")
