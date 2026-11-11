#!/bin/bash
# The REAL pre-commit hook, run once over one intermediate tree of a sequenced item set, in a scratch
# worktree. This is S-14's other half: `session-distill/runlib/sequencing.py` proves the SEARCH over a
# set's orders with a deterministic stand-in, and this script proves that the real hook runs over a
# materialised intermediate tree and returns a verdict the checker can read.
#
# It is deliberately NOT a leg of `gates/check-parity.sh`: the umbrella is itself run by the pre-commit
# hook, so a leg that ran the hook would start a hook inside a hook, and this repo has filled a disk
# that way. It refuses by name when it detects it is running under the hook, asking sequencing.py's
# `--under-the-hook` rather than re-deriving the markers, so the predicate has one owner.
#
# Run it on its own, from the checkout, at verification and again at the rehearsal:
#   bash gates/sequencing-real-hook-check.sh [SECONDS]
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIMIT="${1:-1800}"

if ! python3 "$REPO/session-distill/runlib/sequencing.py" --under-the-hook >/dev/null; then
  echo "sequencing-real-hook-check: refused" >&2
  exit 2
fi

HOOK="$REPO/.githooks/pre-commit"
[ -f "$HOOK" ] || { echo "REAL_HOOK_ABSENT $HOOK: there is no hook to run" >&2; exit 2; }

# A short TMPDIR on purpose: a deep one has broken this repo's socket tests (the 104-byte AF_UNIX cap).
WORK="$(mktemp -d "/tmp/seq-real-hook.XXXXXX")" || exit 1
cleanup() {
  git -C "$REPO" worktree remove --force "$WORK/tree" >/dev/null 2>&1
  rm -rf "$WORK"
  git -C "$REPO" worktree prune >/dev/null 2>&1
}
trap cleanup EXIT INT TERM

git -C "$REPO" worktree add --detach -q "$WORK/tree" || {
  echo "REAL_HOOK_WORKTREE: cannot add a scratch worktree" >&2; exit 2; }

# One intermediate tree: the probe stands for the state after one item of an ordered set has landed.
mkdir -p "$WORK/tree/session-distill/out"
printf 'one intermediate tree of a sequenced set\n' > "$WORK/tree/session-distill/out/sequencing-probe.txt"
git -C "$WORK/tree" add -f session-distill/out/sequencing-probe.txt || exit 2

# macOS has no `timeout`: perl's alarm is the bound, and the hook's own runtime is minutes.
cd "$WORK/tree" || exit 2
perl -e 'alarm shift; exec @ARGV or exit 127' "$LIMIT" bash "$HOOK" > "$WORK/hook.out" 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  tail -5 "$WORK/hook.out"
else
  # The whole output, now: the trap removes the scratch directory on exit, so a path to it would be a
  # path to nothing by the time anyone read this line.
  echo "sequencing-real-hook-check: the hook refused that tree, and its full output follows" >&2
  cat "$WORK/hook.out" >&2
fi
echo "sequencing-real-hook-check: hook rc=$rc over one intermediate tree (bound ${LIMIT}s)"
exit "$rc"
