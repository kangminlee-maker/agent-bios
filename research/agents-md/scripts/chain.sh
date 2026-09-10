#!/bin/bash
# Overnight collection. Every stage is resumable, so a stage is simply re-run until it reports
# nothing left; an interrupted process costs at most one batch.
set -u
cd "$(dirname "$0")/.."
step () {   # step <logfile> <cmd...>
  local log="$1"; shift
  for attempt in 1 2 3 4 5; do
    echo "[$(date +%H:%M:%S)] attempt $attempt: $*" >> "logs/$log"
    python3 "$@" >> "logs/$log" 2>&1
    if grep -aq "0 repos left\|0 left\|done:" "logs/$log"; then break; fi
    sleep 60
  done
}
step files_repos.log     scripts/probe.py files repos.jsonl
echo "=== stars hits: $(wc -l < raw/hits_repos.jsonl 2>/dev/null) ==="
step files_userrepos.log scripts/probe.py files user_repos.jsonl
echo "=== follower hits: $(wc -l < raw/hits_user_repos.jsonl 2>/dev/null) ==="
step fetch.log           scripts/fetch.py
echo "=== corpus: $(wc -l < raw/corpus.jsonl 2>/dev/null) files ==="
python3 scripts/normalize.py > logs/normalize.log 2>&1 || echo "NORMALIZE FAILED"
tail -25 logs/normalize.log
