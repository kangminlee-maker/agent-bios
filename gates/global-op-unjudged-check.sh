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

# ─── Sanitization, before ANY git command this script runs — including the ones that build the
# --self-test's decoy. It used to sit after the self-test branch, which is to say after a `git init`
# and three `git config` writes. With `GIT_CONFIG` inherited, and under the commit hook it is,
# `git config core.worktree` run inside the decoy writes `core.worktree` into the repository
# `GIT_CONFIG` names instead (measured on git 2.50.1: the other repository's config changed and
# carried the decoy's worktree path). That is AGENTS.md's first trap, and the decoy was performing
# it on whatever repository the caller's environment pointed at.
#
# EVERY inherited GIT_* variable, swept from the environment rather than listed. A list is what the
# first version of this script had, and it named five: `GIT_CONFIG`, `GIT_CONFIG_COUNT` with its
# `GIT_CONFIG_KEY_n`/`VALUE_n` pairs, `GIT_COMMON_DIR` and `GIT_TEMPLATE_DIR` all survived it, and
# each of them can send this harness's writes into the REAL repository's config. Under the commit
# hook those variables are exactly what is set.
while IFS='=' read -r held _; do
  case "$held" in GIT_*) unset "$held" || true ;; esac
done < <(env)
# `git` also reads these two without a GIT_ prefix.
unset XDG_CONFIG_HOME GIT_CEILING_DIRECTORIES 2>/dev/null || true
export GIT_CONFIG_NOSYSTEM=1        # no /etc/gitconfig either
export GIT_CONFIG_GLOBAL=/dev/null  # and no ~/.gitconfig, whatever HOME happens to be
# Nothing here writes a .pyc: the gate and the refusal below run out of the REAL checkout, and a
# stale bytecode file planted there outlives this run.
export PYTHONDONTWRITEBYTECODE=1

# --self-test: run the check again with HOSTILE GIT_* variables pointing at a DECOY repository, and
# assert the decoy is untouched. That is the negative control for the finding this script was fixed
# for: a list of five variables to unset let GIT_CONFIG and the GIT_CONFIG_COUNT family through, and
# any of them can redirect a git write into the repository they name. The decoy stands in for the
# real one so the control can be run without risking it.
if [ "${1:-}" = "--self-test" ]; then
  # mktemp's success is checked before any path is built out of it: `set -u` does not catch an empty
  # DECOY, and "$DECOY/.git" would then be "/.git".
  DECOY="$(mktemp -d "/tmp/global-op-decoy.XXXXXX")" || { echo "FAIL: mktemp refused"; exit 1; }
  [ -n "$DECOY" ] && [ -d "$DECOY" ] || { echo "FAIL: mktemp gave no usable directory"; exit 1; }
  trap 'rm -rf "$DECOY"' EXIT
  mkdir -p "$DECOY/worktree" "$DECOY/home" || { echo "FAIL: could not build the decoy tree"; exit 1; }
  # The decoy's own HOME as well, so `git init` cannot read the caller's templates or hooksPath.
  ( cd "$DECOY" && HOME="$DECOY/home" git init -q . && HOME="$DECOY/home" git config core.worktree "$DECOY/worktree" \
      && HOME="$DECOY/home" git config user.email d@e.invalid && HOME="$DECOY/home" git config user.name d ) || {
    echo "FAIL: could not build the decoy repository"; exit 1; }
  # The canary control below re-enters this branch only to reach this point. It stops here, so the
  # recursion is one level deep by construction and no inner run spawns a third.
  if [ -n "${GLOBAL_OP_DECOY_ONLY:-}" ]; then
    echo "decoy built at $DECOY"; exit 0
  fi
  before=$(shasum "$DECOY/.git/config" | cut -d' ' -f1)
  GIT_DIR="$DECOY/.git" GIT_WORK_TREE="$DECOY" GIT_CONFIG="$DECOY/.git/config"     GIT_COMMON_DIR="$DECOY/.git" GIT_TEMPLATE_DIR="$DECOY/template"     GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="core.worktree" GIT_CONFIG_VALUE_0="/hijacked"     GIT_OBJECT_DIRECTORY="$DECOY/.git/objects" GIT_INDEX_FILE="$DECOY/.git/index"     bash "${BASH_SOURCE[0]}" > "$DECOY/run.log" 2>&1
  code=$?
  after=$(shasum "$DECOY/.git/config" | cut -d' ' -f1)
  held=()
  [ "$code" -eq 0 ] || held+=("the check did not pass under hostile GIT_* variables (exit $code): $(tail -3 "$DECOY/run.log")")
  [ "$before" = "$after" ] || held+=("the decoy repository's config CHANGED: the sweep did not hold")
  if git -C "$DECOY" config --get core.worktree | grep -q hijacked; then
    held+=("core.worktree in the decoy was rewritten to the hijacked value")
  fi
  # The canary. The assertions above watch the DECOY, which is what the child run could have
  # written; they say nothing about the git commands that BUILD the decoy, and those ran before the
  # sweep did. So: a third repository nothing in this script is allowed to touch, named by a hostile
  # GIT_CONFIG while a nested run builds its own decoy. `GLOBAL_OP_DECOY_ONLY` stops that run as
  # soon as its decoy stands, so what is measured is the decoy-building commands alone.
  CANARY="$DECOY/canary"
  mkdir -p "$CANARY/home" || { echo "FAIL: could not build the canary tree"; exit 1; }
  ( cd "$CANARY" && HOME="$CANARY/home" git init -q . && HOME="$CANARY/home" git config user.email c@e.invalid ) || {
    echo "FAIL: could not build the canary repository"; exit 1; }
  canary_before=$(shasum "$CANARY/.git/config" | cut -d' ' -f1)
  GIT_CONFIG="$CANARY/.git/config" GIT_DIR="$CANARY/.git" GIT_WORK_TREE="$CANARY" \
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="core.worktree" GIT_CONFIG_VALUE_0="/hijacked" \
    GLOBAL_OP_DECOY_ONLY=1 bash "${BASH_SOURCE[0]}" --self-test > "$DECOY/canary.log" 2>&1
  canary_code=$?
  canary_after=$(shasum "$CANARY/.git/config" | cut -d' ' -f1)
  [ "$canary_code" -eq 0 ] || held+=("building the decoy under hostile GIT_* variables failed (exit $canary_code): $(tail -3 "$DECOY/canary.log")")
  [ "$canary_before" = "$canary_after" ] || held+=("the canary repository's config CHANGED while the decoy was being built: a git command ran before the sweep")
  if grep -q hijacked "$CANARY/.git/config" 2>/dev/null; then
    held+=("the canary's config carries the hijacked worktree: the decoy's git commands wrote into the repository GIT_CONFIG named")
  fi

  if [ "${#held[@]}" -gt 0 ]; then
    for row in "${held[@]}"; do echo "FAIL: $row"; done
    echo "global-op-unjudged-check --self-test: FAILED (${#held[@]})"
    exit 1
  fi
  echo "global-op-unjudged-check --self-test: OK (the check passes with GIT_DIR, GIT_CONFIG, the"
  echo "GIT_CONFIG_COUNT family, GIT_COMMON_DIR, GIT_TEMPLATE_DIR, GIT_OBJECT_DIRECTORY and"
  echo "GIT_INDEX_FILE all aimed at a decoy repository, and the decoy's config is byte-identical"
  echo "afterwards)"
  exit 0
fi
LIMIT="${GLOBAL_OP_CHECK_TIMEOUT:-180}"
WORK="$(mktemp -d "/tmp/global-op.XXXXXX")" || { echo "FAIL: mktemp refused"; exit 1; }
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "FAIL: mktemp gave no usable directory"; exit 1; }
trap 'rm -rf "$WORK"' EXIT

# The GIT_* sweep and the config isolation are at the top of this file, ahead of the self-test's own
# git commands. What is left here is the fixture's own HOME, which cannot be set before the temp
# directory exists.
export HOME="$WORK/home" CLAUDE_CONFIG_DIR="$WORK/home/.claude" CODEX_HOME="$WORK/home/.codex"
export TMPDIR="$WORK/tmp"

# Every step that builds the fixture is fatal: a failed mkdir, a failed cd or a failed init leaves
# the next git command running somewhere this script did not choose, and the repository it would
# then write into is whichever one encloses the working directory.
mkdir -p "$HOME" "$TMPDIR" "$WORK/repo/claude" || { echo "FAIL: could not build the fixture tree"; exit 1; }
cd "$WORK/repo" || { echo "FAIL: could not enter the scratch repository"; exit 1; }
git init -q . || { echo "FAIL: git init refused in the scratch repository"; exit 1; }
# After init, prove the repository git now answers for is the scratch one and not the real tree.
held_top=$(git rev-parse --show-toplevel 2>/dev/null || true)
case "$held_top" in
  "$WORK/repo"|"/private$WORK/repo") : ;;
  *) echo "FAIL: git answers for $held_top, not the scratch repository at $WORK/repo"; exit 1 ;;
esac
git config user.email "fixture@example.invalid" || { echo "FAIL: git config refused"; exit 1; }
git config user.name "fixture" || { echo "FAIL: git config refused"; exit 1; }

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
