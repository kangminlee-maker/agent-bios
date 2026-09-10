#!/usr/bin/env python3
"""S2: decide which qualifying repos actually carry an agent-instruction file.

Three commands:

  probe.py user-repos            users.jsonl -> user_repos.jsonl   (repo list only, no files)
  probe.py files repos.jsonl     -> hits_repos.jsonl               (file existence per repo)
  probe.py files user_repos.jsonl -> hits_user_repos.jsonl

Why the split: measured on the live API, traversing a user's `repositories` connection costs
~0.42 s/user, while a direct `repository(owner:,name:)` alias with all eight path lookups costs
~0.031 s/repo. Asking for files *inside* the user connection multiplies the two and blows past
GitHub's ~10 s query timeout (observed: 4 users x 40 repos -> HTTP 502). Listing cheaply first
and probing files in flat alias batches keeps every query well inside the timeout.
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

PATHS = [
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    ".github/AGENTS.md",
    ".github/CLAUDE.md",
    "docs/AGENTS.md",
    "docs/CLAUDE.md",
    "agents.md",
]
PUSHED_SINCE = "2025-01-01"
REPO_META = ("nameWithOwner stargazerCount pushedAt isArchived isFork isPrivate "
             "primaryLanguage{name} licenseInfo{spdxId} defaultBranchRef{name}")
LIGHT_META = "nameWithOwner stargazerCount pushedAt isArchived"

TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
LOCK = threading.Lock()
TLS = threading.local()
STATE = {"done": 0, "remaining": None, "failed_batches": 0, "total_batches": 0}

# Deliberately gentle: this shares one GitHub account with the user's other tools, so the pass
# runs well inside every limit rather than at the edge of it. Slower is the point.
WORKERS = 2
BATCH_REPOS = 20          # measured safe ceiling is ~30/query; stay below it
BATCH_USERS = 8
POLITE_DELAY = 1.5        # seconds after each query, per worker
BUDGET_FLOOR = 1500       # leave this many GraphQL points for everything else


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def gql(query):
    if not hasattr(TLS, "s"):
        TLS.s = requests.Session()
        TLS.s.headers.update({"Authorization": f"Bearer {TOKEN}", "User-Agent": "agents-md-research"})
    for attempt in range(6):
        try:
            r = TLS.s.post("https://api.github.com/graphql", json={"query": query}, timeout=90)
        except requests.RequestException as e:
            log(f"  network error: {e}; retrying")
            time.sleep(2 ** attempt)
            continue
        if r.status_code >= 500 or r.status_code in (403, 408, 429):
            wait = int(r.headers.get("retry-after", 0)) or 2 ** attempt * 4
            log(f"  http {r.status_code}; sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        body = r.json()
        rl = (body.get("data") or {}).get("rateLimit")
        if rl:
            with LOCK:
                STATE["remaining"] = rl["remaining"]
            while rl["remaining"] < BUDGET_FLOOR:
                log(f"  graphql budget at {rl['remaining']} (floor {BUDGET_FLOOR}); waiting 5 min")
                time.sleep(300)
                probe_rl = TLS.s.post("https://api.github.com/graphql",
                                      json={"query": "query{rateLimit{remaining}}"}, timeout=30)
                rl = probe_rl.json()["data"]["rateLimit"] if probe_rl.status_code == 200 else rl
        time.sleep(POLITE_DELAY)
        if body.get("data") is None:
            msg = json.dumps(body.get("errors"))[:200]
            if "rate limit" in msg.lower():
                time.sleep(60)
                continue
            log(f"  graphql error: {msg}")
            return None
        return body
    return None


def file_fields():
    return " ".join(f'p{i}:object(expression:"HEAD:{p}"){{... on Blob{{byteSize isBinary}}}}'
                    for i, p in enumerate(PATHS))


def extract_files(node):
    out = []
    for i, p in enumerate(PATHS):
        blob = node.get(f"p{i}")
        if blob and blob.get("byteSize") is not None and not blob.get("isBinary"):
            out.append({"path": p, "byte_size": blob["byteSize"]})
    return out


def run_batches(batches, worker, label, total_items):
    def wrapped(arg):
        bi, chunk = arg
        with LOCK:
            STATE["total_batches"] += 1
        try:
            return worker(bi, chunk)
        except Exception as e:                       # a dead batch must be visible, not silent
            with LOCK:
                STATE["failed_batches"] += 1
            log(f"  batch {bi} raised {type(e).__name__}: {e}")
            return 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        got = sum(ex.map(wrapped, enumerate(batches)))
    fail = STATE["failed_batches"]
    log(f"{label} done: {got} records from {total_items} items; "
        f"failed batches {fail}/{STATE['total_batches']}")
    if fail:
        log(f"WARNING: {fail} batches produced nothing — results are incomplete")
    return got


# ------------------------------------------------------- list a user's recent repos

def user_repos(per_user=40, batch=BATCH_USERS, repair=False):
    users = [json.loads(l) for l in open(os.path.join(RAW, "users.jsonl"))]
    dst = os.path.join(RAW, "user_repos.jsonl")
    if repair:
        # A transport failure and a genuinely repo-less user both leave a login absent from the
        # output, so re-probe every absent login. The second pass is self-limiting: whoever is
        # still absent afterwards really has no qualifying repo.
        covered = {json.loads(l)["owner"] for l in open(dst)} if os.path.exists(dst) else set()
        users = [u for u in users if u["login"] not in covered]
        log(f"repair: {len(users)} users absent from {os.path.basename(dst)}")
        if not users:
            return
    log(f"user-repos: {len(users)} users x {per_user} most-recently-pushed own repos")
    out = open(dst, "a" if repair else "w")
    batches = [users[i:i + batch] for i in range(0, len(users), batch)]

    def worker(bi, chunk):
        parts = [
            f'u{j}:user(login:{json.dumps(u["login"])})'
            f'{{login followers{{totalCount}} repositories(first:{per_user},isFork:false,'
            f'privacy:PUBLIC,ownerAffiliations:[OWNER],orderBy:{{field:PUSHED_AT,direction:DESC}})'
            f'{{nodes{{{LIGHT_META}}}}}}}'
            for j, u in enumerate(chunk)
        ]
        body = gql("query{" + " ".join(parts) + " rateLimit{cost remaining}}")
        if body is None:
            with LOCK:
                STATE["failed_batches"] += 1
            return 0
        lines = []
        for j, u in enumerate(chunk):
            node = (body["data"] or {}).get(f"u{j}")
            if not node:
                continue
            followers = node["followers"]["totalCount"]
            for repo in (node.get("repositories") or {}).get("nodes") or []:
                if not repo or repo.get("isArchived"):
                    continue
                if (repo.get("pushedAt") or "") < PUSHED_SINCE:
                    continue        # nodes are pushed-desc, but a short list may still mix
                lines.append(json.dumps({
                    "full_name": repo["nameWithOwner"],
                    "owner": node["login"],
                    "owner_followers": followers,
                    "stars": repo["stargazerCount"],
                    "pushed_at": repo["pushedAt"],
                    "source": "followers",
                }))
        with LOCK:
            out.write("\n".join(lines) + ("\n" if lines else ""))
            STATE["done"] += len(chunk)
            if bi % 20 == 0:
                out.flush()
                log(f"  {STATE['done']}/{len(users)} users, budget left {STATE['remaining']}")
        return len(lines)

    run_batches(batches, worker, "user-repos", len(users))
    out.close()


# ------------------------------------------------------- probe files on a repo list

def files(src_name, batch=BATCH_REPOS):
    """Resumable: every probed repo is recorded in a sidecar `.done` file, so an interrupted
    run picks up where it stopped instead of re-probing from the top. At most one batch is
    repeated across a restart."""
    src = os.path.join(RAW, src_name)
    seen, repos = set(), []
    for line in open(src):
        rec = json.loads(line)
        if rec["full_name"] in seen:
            continue
        seen.add(rec["full_name"])
        repos.append(rec)

    dst_name = "hits_" + src_name.replace(".jsonl", "") + ".jsonl"
    done_path = os.path.join(RAW, dst_name + ".done")
    already = set()
    if os.path.exists(done_path):
        already = {l.strip() for l in open(done_path) if l.strip()}
        repos = [r for r in repos if r["full_name"] not in already]
        log(f"files: resuming — {len(already)} repos already probed")
    log(f"files: {len(repos)} repos left from {src_name} -> {dst_name}")
    if not repos:
        return
    out = open(os.path.join(RAW, dst_name), "a")
    donef = open(done_path, "a")
    batches = [repos[i:i + batch] for i in range(0, len(repos), batch)]

    def worker(bi, chunk):
        parts = []
        for j, r in enumerate(chunk):
            owner, name = r["full_name"].split("/", 1)
            parts.append(f'r{j}:repository(owner:{json.dumps(owner)},name:{json.dumps(name)})'
                         f'{{{REPO_META} {file_fields()}}}')
        body = gql("query{" + " ".join(parts) + " rateLimit{cost remaining}}")
        if body is None:
            with LOCK:
                STATE["failed_batches"] += 1
            return 0
        lines = []
        for j, r in enumerate(chunk):
            node = (body["data"] or {}).get(f"r{j}")
            if not node or node.get("isArchived") or node.get("isFork") or node.get("isPrivate"):
                continue
            found = extract_files(node)
            if not found:
                continue
            lines.append(json.dumps({
                "full_name": node["nameWithOwner"],
                "owner": node["nameWithOwner"].split("/")[0],
                "owner_followers": r.get("owner_followers"),
                "stars": node["stargazerCount"],
                "pushed_at": node["pushedAt"],
                "language": (node.get("primaryLanguage") or {}).get("name"),
                "license": (node.get("licenseInfo") or {}).get("spdxId"),
                "default_branch": (node.get("defaultBranchRef") or {}).get("name"),
                "qualifies": [r.get("source", "stars")],
                "files": found,
            }))
        with LOCK:
            out.write("\n".join(lines) + ("\n" if lines else ""))
            out.flush()
            donef.write("".join(f'{r["full_name"]}\n' for r in chunk))
            donef.flush()
            STATE["done"] += len(chunk)
            if bi % 25 == 0:
                log(f"  {STATE['done']}/{len(repos)} repos, budget left {STATE['remaining']}")
        return len(lines)

    run_batches(batches, worker, "files", len(repos))
    out.close()
    donef.close()


if __name__ == "__main__":
    cmd = sys.argv[1]
    t0 = time.time()
    if cmd == "user-repos":
        user_repos()
    elif cmd == "user-repos-repair":
        user_repos(repair=True)
    elif cmd == "files":
        files(sys.argv[2])
    else:
        raise SystemExit("usage: probe.py user-repos | user-repos-repair | files <list.jsonl>")
    log(f"elapsed {time.time() - t0:.0f}s")
