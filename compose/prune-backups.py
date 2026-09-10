#!/usr/bin/env python3
"""Retention for the copies this repo makes before it overwrites or removes something.

A backup exists so a mistake is recoverable, so pruning is the one operation here that can
destroy the thing the feature is for. That decides the rule: a copy is deleted only when it is
BOTH older than the age window AND outside the most recent N. Either condition alone would be
enough to delete something someone still wants — a busy week would age out yesterday's work, and
a quiet quarter would trim a set small enough to keep whole.

Worked through, that single condition gives the intended behaviour:

  20 copies made inside one month   -> none are old enough; keep all 20
  8 copies spread over two months   -> none are outside the newest 10; keep all 8
  11 copies, 7 of them this month   -> the oldest is both aged and outside the 10; keep 10

Two groups are pruned, because this repo writes backups in two shapes: timestamped directories
under the state dir, and sibling backup files next to the file they copy (assemble, learn and
migrate write those). They are pruned independently — ten of each — since losing one group's
history to the other group's churn is not what either was kept for.

This module also answers WHICH loose files are ours (`OWNED_SIBLING`, `owned_siblings`), for
itself and for uninstall. Both delete, so the rule lives in one place.

  --claude-dir/--codex-dir/--state-dir   where to look
  --dry-run     print what would go, delete nothing
  --list-owned  print the owned loose backups, NUL-separated (uninstall reads this)
  --self-test   the retention rule and the ownership rule, both directions
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
import time

KEEP_RECENT = 10
MAX_AGE_DAYS = 30

# What counts as OUR loose backup — and the only place that question is answered.
# `install.sh` asks this module rather than restating the pattern, because both sides
# delete, and a rule stated twice is a rule that drifts on one side.
#
# The shapes below are exactly what this repo writes: compose/assemble.py (a plain
# timestamp for settings.json, `legacy` for a migrated entry file), learn/collect-learning.py,
# learn/migrate-learnings.py, and install.sh's codex-config removal. A bare `.bak-`
# substring — what this used to match — also claims `notes.bak-old`, which is the user's.
# These live in directories we SHARE with the user and with other tools, so ownership has
# to be carried by the name; the directory cannot confer it.
# The bare `.bak-<timestamp>` form carries no marker of its own, so it is pinned to the ONE
# basename that receives it — `settings.json`, from merge_settings. Left generic it also claimed
# a `notes.bak-20260101-000000` the user wrote, which is a correctly shaped timestamp on a file
# that is not ours; matching the timestamp SHAPE is not the same as matching our ownership.
_TS = r"\d{8}-\d{6}"
OWNED_SIBLING = re.compile(
    rf"^(?:settings\.json\.bak-{_TS}"
    rf"|.+\.bak-(?:legacy|learn|migrate)-{_TS}"
    rf"|.+\.bak-agent-bios-uninstall)$")


def owned_siblings(root):
    """Every loose backup under `root` that this repo wrote. Nothing else is ours."""
    if not root.is_dir():
        return []
    return [f for f in root.rglob("*") if f.is_file() and OWNED_SIBLING.search(f.name)]


def to_delete(entries, now, keep_recent=KEEP_RECENT, max_age_days=MAX_AGE_DAYS):
    """(path, mtime) pairs -> the ones both aged out AND outside the newest `keep_recent`.

    Both conditions, never either: this is the whole retention policy, and it is a pure function
    so the policy can be tested without creating and destroying real backups.
    """
    newest_first = sorted(entries, key=lambda e: e[1], reverse=True)
    cutoff = now - max_age_days * 86400
    return [path for i, (path, mtime) in enumerate(newest_first)
            if i >= keep_recent and mtime < cutoff]


def _entries(paths):
    out = []
    for p in paths:
        try:
            out.append((p, p.stat().st_mtime))
        except OSError:
            continue  # vanished under us; nothing to prune
    return out


def prune(state_dir, homes, now=None, dry=False):
    """Prune both groups. Returns the paths removed (or that would be)."""
    now = time.time() if now is None else now
    removed = []

    # Recorded AFTER the removal is confirmed gone. Both deleters swallow their errors on
    # purpose — a backup that will not delete must not fail an install — but appending
    # first made the returned list a record of what was ATTEMPTED, and the caller prints it
    # as what was removed. A copy still on disk being reported as pruned is the reading
    # that sends someone looking for space that was never freed.
    def take(path, remove):
        if dry:
            removed.append(path)
            return
        remove(path)
        if path.exists():
            print(f"  warning: could not remove {path}", file=sys.stderr)
            return
        removed.append(path)

    backups = state_dir / "backups"
    if backups.is_dir():
        for path in to_delete(_entries([d for d in backups.iterdir() if d.is_dir()]), now):
            take(path, lambda p: shutil.rmtree(p, ignore_errors=True))

    for home in homes:
        for path in to_delete(_entries(owned_siblings(home)), now):
            take(path, lambda p: p.unlink(missing_ok=True))
    return removed


def self_test():
    day = 86400
    now = 1_000_000_000.0
    cases = [
        ("20 within a month -> keep all",
         [(f"b{i}", now - i * day) for i in range(20)], 0),
        ("8 over two months -> keep all",
         [(f"b{i}", now - i * 8 * day) for i in range(8)], 0),
        ("11 with 7 recent -> drop the oldest one",
         [(f"b{i}", now - i * day) for i in range(7)]
         + [(f"o{i}", now - (40 + i * 5) * day) for i in range(4)], 1),
        ("11 all recent -> drop none",
         [(f"b{i}", now - i * day) for i in range(11)], 0),
        ("30 all aged -> keep the newest ten",
         [(f"b{i}", now - (40 + i) * day) for i in range(30)], 20),
    ]
    bad = 0
    for label, entries, want in cases:
        got = len(to_delete(entries, now))
        ok = got == want
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label} (deleted {got}, want {want})")
    # A rule that deletes nothing whatever the input would pass every case above by accident.
    proof = to_delete([(f"x{i}", now - (100 + i) * day) for i in range(50)], now)
    if len(proof) != 40:
        print("  FAIL contrast control: the rule never deletes anything")
        bad += 1
    else:
        print("  ok   contrast control: it does delete when both conditions hold")

    # Ownership, in both directions. The first list is every shape this repo writes; the
    # second is what a person or another tool leaves in the same directories. Matching the
    # first proves the rule still finds our copies after a rename; refusing the second is
    # the half that matters, because uninstall DELETES whatever this claims.
    ours = ["settings.json.bak-20260101-000000", "CLAUDE.md.bak-legacy-20260101-000000",
            "learnings.md.bak-learn-20260101-000000", "learnings.md.bak-migrate-20260101-000000",
            "config.toml.bak-agent-bios-uninstall"]
    theirs = ["notes.bak-old", "db.bak-2026", "x.bak-", "report.bak-final.txt",
              "settings.json.bak-2026010-000000", "a.bak-legacy-nope",
              # A correctly shaped timestamp on a basename that is not ours. The first pass
              # only rejected MALFORMED timestamps, which tested the shape and not the
              # ownership — so the rule went on claiming these and the control stayed green.
              "notes.bak-20260101-000000", "db.bak-20240301-120000",
              "settings.json.txt.bak-20260101-000000"]
    missed = [n for n in ours if not OWNED_SIBLING.search(n)]
    grabbed = [n for n in theirs if OWNED_SIBLING.search(n)]
    for name in missed:
        print(f"  FAIL ownership: {name} is ours but went unclaimed")
    for name in grabbed:
        print(f"  FAIL ownership: {name} is NOT ours but was claimed for deletion")
    bad += len(missed) + len(grabbed)
    if not missed and not grabbed:
        print(f"  ok   ownership: claims {len(ours)} shapes we write, "
              f"refuses {len(theirs)} we do not")
    # The reported list is what the caller prints as removed, so it has to be what is GONE.
    # Both deleters swallow their errors by design — a stuck copy must not fail an install —
    # and appending before the call made the list a record of attempts instead. Driven on a
    # real directory, because the defect lives in the deletion and not in the pure retention
    # rule above; the deletable run beside it is what keeps this from passing on a pruner
    # that reports nothing at all.
    import os as os_, tempfile as tempfile_

    def reported_vs_gone(block_one):
        root = pathlib.Path(tempfile_.mkdtemp())
        state = root / "state"
        (state / "backups").mkdir(parents=True)
        made = []
        for i in range(KEEP_RECENT + 2):
            aged = state / "backups" / f"2020{i:04d}-000000"
            aged.mkdir()
            (aged / "f.txt").write_text("x")
            stamp = now - (MAX_AGE_DAYS + 10 + i) * day
            os_.utime(aged, (stamp, stamp))
            made.append(aged)
        stuck = sorted(made, key=lambda q: q.stat().st_mtime)[0]
        if block_one:
            stuck.chmod(0o500)
        count = len(prune(state, [], now=now))
        gone = len([q for q in made if not q.exists()])
        if block_one:
            stuck.chmod(0o700)
        shutil.rmtree(root, ignore_errors=True)
        return count, gone

    for label, block_one in (("every aged backup deletable", False),
                             ("one of them undeletable", True)):
        count, gone = reported_vs_gone(block_one)
        if count != gone or (not block_one and gone == 0):
            print(f"  FAIL {label}: reported {count} removed, {gone} actually gone")
            bad += 1
        else:
            print(f"  ok   {label}: reported {count} == gone {gone}")

    print(f"prune-backups self-test: {'OK' if not bad else 'FAIL'} ({len(cases) + 4} checks)")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir")
    ap.add_argument("--claude-dir")
    ap.add_argument("--codex-dir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--list-owned", action="store_true",
                    help="print every owned loose backup under the config dirs, NUL-separated, "
                         "then exit. uninstall consumes this instead of restating the rule.")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())

    state = pathlib.Path(args.state_dir or pathlib.Path.home() / ".local/share/agent-bios")
    homes = [pathlib.Path(d) for d in (
        args.claude_dir or os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude",
        args.codex_dir or os.environ.get("CODEX_HOME") or pathlib.Path.home() / ".codex")]
    if args.list_owned:
        # NUL-separated: these are real paths from a user's home, and a newline in one would
        # otherwise split a single file into two entries — one of which the caller then deletes.
        for home in homes:
            for path in owned_siblings(home):
                sys.stdout.write(f"{path}\0")
        return
    removed = prune(state, homes, dry=args.dry_run)
    for path in removed:
        print(f"  {'[dry] ' if args.dry_run else ''}pruned backup  {path}")
    if removed and not args.dry_run:
        print(f"  pruned {len(removed)} backup(s) past retention "
              f"(kept: newest {KEEP_RECENT}, plus anything under {MAX_AGE_DAYS} days)")


if __name__ == "__main__":
    main()
