#!/usr/bin/env bash
# Author-side: O10 end to end against the REAL global-file gate (WP-21 done-when 1).
#
# Not a leg of the umbrella, and not a control inside `runlib/drift.py`'s self-test, for two
# reasons. `session-distill/runlib/` ships, so a suite there calling `gates/check-global-file.py`
# would be a shipped file naming a path a packaged user does not have — `gates/check-package.sh`'s
# third direction. And it drives git over a scratch repository, which the shipped suites do not.
#
# What it shows, in one run: a deletion paired with an unrelated shorter line PASSES WP-14's gate,
# because that gate holds `claude/CLAUDE.md` to a 20 KiB ceiling and only DISCLOSES added lines, and
# S11 then refuses the same operation by name (`GLOBAL_OP_UNJUDGED`) for want of a merge judgment.
# The gate's verdict and the refusal are therefore both read from the things that produce them,
# never re-implemented here.
#
#   bash gates/global-op-unjudged-check.sh
#
# Exits 0 when the gate passed AND the refusal fired; 1 naming which half did not.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIMIT="${GLOBAL_OP_CHECK_TIMEOUT:-180}"
WORK="$(mktemp -d "/tmp/global-op.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# A scratch repository with every GIT_* variable scrubbed: under the commit hook they point at the
# hook's snapshot, and a `git init` inheriting them rewrites the REAL repository's config
# (AGENTS.md's first trap).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
export HOME="$WORK/home" CLAUDE_CONFIG_DIR="$WORK/home/.claude" CODEX_HOME="$WORK/home/.codex"
export TMPDIR="$WORK/tmp"
mkdir -p "$HOME" "$TMPDIR" "$WORK/repo/claude" "$WORK/repo/gates"

cd "$WORK/repo"
git init -q .
git config user.email "fixture@example.invalid"
git config user.name "fixture"

# A global file with two rules, committed as the base.
printf 'A rule that stays.\nA rule that goes.\n' > claude/CLAUDE.md
git add claude/CLAUDE.md
git commit -q -m "base"

# The O10 edit: the second rule DELETED and an unrelated, shorter line added. The file shrinks.
printf 'A rule that stays.\nUnrelated.\n' > claude/CLAUDE.md
git add claude/CLAUDE.md

before=$(git show HEAD:claude/CLAUDE.md | wc -c | tr -d ' ')
after=$(git show :claude/CLAUDE.md | wc -c | tr -d ' ')

set +e
# The gate is run FROM the real repository and POINTED at the scratch index, which is exactly how
# the commit hook runs it: it reads the index through git, and the inherited GIT_DIR / GIT_WORK_TREE
# decide which index. Copying the gate into the fixture does not work - it loads
# `session-distill/runlib/gitread.py` relative to its own repository root.
gate_out=$(GIT_DIR="$WORK/repo/.git" GIT_WORK_TREE="$WORK/repo" \
  perl -e 'alarm shift; exec @ARGV or exit 127' "$LIMIT" \
  python3 -I "$REPO/gates/check-global-file.py" 2>&1)
gate_code=$?
set -e

failures=()
if [ "$gate_code" -ne 0 ]; then
  failures+=("the ceiling gate did not pass the O10 edit (exit $gate_code): under the ceiling
version a smaller file passes, so either the gate changed or this fixture no longer builds the case")
fi
# The added line must be DISCLOSED: that disclosure is the only thing the gate says about it, which
# is why S11's refusal has to exist.
if ! printf '%s' "$gate_out" | grep -q "Unrelated."; then
  failures+=("the gate did not disclose the added line, so this check is not reading the disclosure
it claims to read")
fi

# S11's half, through the real function over the same operation.
set +e
refusal=$(perl -e 'alarm shift; exec @ARGV or exit 127' "$LIMIT" \
  python3 -I -c "
import sys, json
sys.path.insert(0, '$REPO/session-distill')
from runlib import drift
f = [{'item_id': 'i-o10', 'operations': [
    {'type': 'delete', 'target': 'claude/CLAUDE.md', 'before_state_sha256': 'a' * 64},
    {'type': 'edit', 'target': 'claude/CLAUDE.md', 'before_state_sha256': 'a' * 64}]}]
print(json.dumps({'unjudged': drift.global_op_problems(f),
                  'judged': drift.global_op_problems(f, {'i-o10': 'yes'})}))
" 2>&1)
refusal_code=$?
set -e

if [ "$refusal_code" -ne 0 ]; then
  failures+=("S11's refusal could not be read (exit $refusal_code): $refusal")
elif ! printf '%s' "$refusal" | grep -q "GLOBAL_OP_UNJUDGED i-o10"; then
  failures+=("S11 did not refuse the operation the gate passed: $refusal")
elif ! printf '%s' "$refusal" | python3 -I -c "
import json, sys
held = json.loads(sys.stdin.read())
sys.exit(0 if held['judged'] == [] else 1)
"; then
  failures+=("the same operation stayed refused with a faithful merge judgment, so the refusal is
not reading the judgment")
fi

echo "global file: ${before} bytes -> ${after} bytes (the ceiling is 20480)"
echo "WP-14 gate:  exit ${gate_code}, added line disclosed"
echo "S11:         $(printf '%s' "$refusal" | head -c 200)"

if [ "${#failures[@]}" -gt 0 ]; then
  for held in "${failures[@]}"; do echo "FAIL: $held"; done
  echo "global-op-unjudged-check: FAILED (${#failures[@]})"
  exit 1
fi
echo "global-op-unjudged-check: OK (the ceiling gate passes a deletion paired with an unrelated
shorter line and discloses the added line; S11 refuses it as GLOBAL_OP_UNJUDGED, and accepts it when
S7b judged the merge faithful)"
