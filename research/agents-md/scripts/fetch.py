#!/usr/bin/env python3
"""S2b: fetch the body of every qualifying file into one corpus.

Merges the two hit streams (star-qualified repos, follower-qualified owners), unions the
`qualifies` reason when a repo satisfies both, drops stubs and outliers, then pulls
Blob.text in alias batches.
"""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "raw")

MIN_BYTES = 200        # below this a file is a stub/pointer, not an instruction set
MAX_BYTES = 400_000    # above this it is a generated dump, not hand-written guidance

WORKERS = 2            # shares the account with the user's other tools; stay well inside limits
BATCH = 6              # bodies are large; small batches keep each query far from the timeout
POLITE_DELAY = 1.5
BUDGET_FLOOR = 1500

TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
LOCK = threading.Lock()
TLS = threading.local()
STATE = {"done": 0, "remaining": None}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def gql(query):
    if not hasattr(TLS, "s"):
        TLS.s = requests.Session()
        TLS.s.headers.update({"Authorization": f"Bearer {TOKEN}", "User-Agent": "agents-md-research"})
    for attempt in range(8):
        r = TLS.s.post("https://api.github.com/graphql", json={"query": query}, timeout=180)
        if r.status_code >= 500 or r.status_code in (403, 408, 429):
            wait = int(r.headers.get("retry-after", 0)) or 2 ** attempt * 5
            log(f"  http {r.status_code}; sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        body = r.json()
        rl = (body.get("data") or {}).get("rateLimit")
        if rl:
            STATE["remaining"] = rl["remaining"]
            while rl["remaining"] < BUDGET_FLOOR:
                log(f"  graphql budget at {rl['remaining']}; waiting 5 min")
                time.sleep(300)
                pr = TLS.s.post("https://api.github.com/graphql",
                                json={"query": "query{rateLimit{remaining}}"}, timeout=30)
                rl = pr.json()["data"]["rateLimit"] if pr.status_code == 200 else rl
        time.sleep(POLITE_DELAY)
        if body.get("data") is None:
            if "rate limit" in json.dumps(body.get("errors")).lower():
                time.sleep(60)
                continue
            return None
        return body
    return None


def load_hits():
    merged = {}
    for fname in ("hits_repos.jsonl", "hits_user_repos.jsonl"):
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            log(f"  (missing {fname}, skipping)")
            continue
        for line in open(path):
            rec = json.loads(line)
            key = rec["full_name"]
            if key in merged:
                prev = merged[key]
                prev["qualifies"] = sorted(set(prev["qualifies"]) | set(rec["qualifies"]))
                prev.setdefault("owner_followers", rec.get("owner_followers"))
                if rec.get("owner_followers") is not None:
                    prev["owner_followers"] = rec["owner_followers"]
                known = {f["path"] for f in prev["files"]}
                prev["files"] += [f for f in rec["files"] if f["path"] not in known]
            else:
                merged[key] = rec
    return merged


def main(batch=BATCH, workers=WORKERS):
    merged = load_hits()
    targets = []
    for repo in merged.values():
        for f in repo["files"]:
            if MIN_BYTES <= f["byte_size"] <= MAX_BYTES:
                targets.append((repo, f))
    log(f"{len(merged)} repos with hits -> {len(targets)} files in [{MIN_BYTES},{MAX_BYTES}] bytes")

    done_path = os.path.join(RAW, "corpus.jsonl.done")
    already = {l.strip() for l in open(done_path)} if os.path.exists(done_path) else set()
    if already:
        targets = [(r, f) for r, f in targets if f'{r["full_name"]}::{f["path"]}' not in already]
        log(f"  resuming — {len(already)} files already fetched, {len(targets)} left")
    if not targets:
        return
    out = open(os.path.join(RAW, "corpus.jsonl"), "a")
    donef = open(done_path, "a")
    batches = [targets[i:i + batch] for i in range(0, len(targets), batch)]

    def run(bi_chunk):
        bi, chunk = bi_chunk
        parts = []
        for j, (repo, f) in enumerate(chunk):
            owner, name = repo["full_name"].split("/", 1)
            parts.append(
                f'f{j}:repository(owner:{json.dumps(owner)},name:{json.dumps(name)})'
                f'{{object(expression:{json.dumps("HEAD:" + f["path"])}){{... on Blob{{text}}}}}}'
            )
        body = gql("query{" + " ".join(parts) + " rateLimit{cost remaining}}")
        if body is None:
            return 0
        data, lines = body["data"], []
        for j, (repo, f) in enumerate(chunk):
            node = data.get(f"f{j}") or {}
            obj = node.get("object") or {}
            text = obj.get("text")
            if not text:
                continue
            lines.append(json.dumps({
                "id": f'{repo["full_name"]}::{f["path"]}',
                "full_name": repo["full_name"],
                "owner": repo["owner"],
                "path": f["path"],
                "kind": "AGENTS" if "AGENTS" in f["path"] or f["path"] == "agents.md" else "CLAUDE",
                "stars": repo["stars"],
                "owner_followers": repo.get("owner_followers"),
                "qualifies": repo["qualifies"],
                "language": repo.get("language"),
                "license": repo.get("license"),
                "pushed_at": repo.get("pushed_at"),
                "byte_size": f["byte_size"],
                "text": text,
            }, ensure_ascii=False))
        with LOCK:
            for line in lines:
                out.write(line + "\n")
            out.flush()
            donef.write("".join(f'{r["full_name"]}::{f["path"]}\n' for r, f in chunk))
            donef.flush()
            STATE["done"] += len(chunk)
            if bi % 50 == 0:
                log(f"  {STATE['done']}/{len(targets)} fetched, budget left {STATE['remaining']}")
        return len(lines)

    def safe(arg):
        try:
            return run(arg)
        except Exception as e:                       # never let one dead batch kill the run
            log(f"  batch {arg[0]} raised {type(e).__name__}: {e}")
            return 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        total = sum(ex.map(safe, enumerate(batches)))
    out.close()
    donef.close()
    log(f"corpus written: {total} files this pass")


if __name__ == "__main__":
    t0 = time.time()
    main()
    log(f"elapsed {time.time() - t0:.0f}s")
