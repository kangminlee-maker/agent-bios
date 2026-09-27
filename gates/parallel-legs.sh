#!/usr/bin/env bash
# Concurrent legs for gates/check-parity.sh, which sources this file. Author-side, like all of
# gates/. Design: design/gate-parallelism/2026-09-28T0717--6c4f2c1--design.md.
#
# The umbrella writes each leg as one background job that keeps the leg's own commands in place:
#
#   leg "lexicon"; { leg_enter
#   python3 gates/check-lexicon.py >/dev/null \
#     || { echo "FAIL: lexicon gate (run gates/check-lexicon.py)"; fail=1; }
#   exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
#
# and ends with legs_finish. What that keeps from the serial umbrella:
#   - each leg's output, stdout and stderr in one slot, printed in the order the legs appear in
#     the file, whatever order they finish in;
#   - failure by name: a leg that exits non-zero gets `FAIL: leg '<name>' exited <status>` after
#     its output, so one that dies printing nothing still names itself (install.sh verify shows
#     only this umbrella's FAIL lines);
#   - the order inside a leg, since a leg is one job.
# PARITY_JOBS caps how many legs run at once (default: the online CPU count). A leg takes a token
# from a FIFO before it starts and returns it when it exits, so PARITY_JOBS=1 is the serial run.
# Each leg gets its own TMPDIR under one directory, removed when every leg passed and kept, and
# named, when one failed — the install scenarios keep their failing log there.
#
# `bash gates/parallel-legs.sh --self-test` is the negative control: planted umbrellas must keep
# order, run concurrently, honour the cap, return every token, and fail by name on a leg that
# fails loudly, silently, or by being killed.

legs_init() {
  PARITY_JOBS="${PARITY_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)}"
  case "$PARITY_JOBS" in
    ''|*[!0-9]*|0) echo "FAIL: PARITY_JOBS must be a positive integer, not '$PARITY_JOBS'"; return 1 ;;
  esac
  # The tokens sit in a pipe buffer until taken; a count past what the buffer holds would block
  # this write forever, so an absurd cap is refused rather than hung on.
  [ "$PARITY_JOBS" -le 1024 ] \
    || { echo "FAIL: PARITY_JOBS=$PARITY_JOBS exceeds 1024"; return 1; }
  LEGS="$(mktemp -d "${TMPDIR:-/tmp}/parity.XXXXXX")" \
    || { echo "FAIL: cannot create the directory the legs run in"; return 1; }
  mkfifo "$LEGS/slots" || { echo "FAIL: cannot create the leg slot queue in $LEGS"; return 1; }
  exec 9<>"$LEGS/slots"
  rm -f "$LEGS/slots"
  local i=0
  while [ "$i" -lt "$PARITY_JOBS" ]; do printf . >&9; i=$((i + 1)); done
  legs_n=0
  legs_printed=0
}

# Parent side: open the next output slot, in file order, and wait for a free token.
leg() {
  legs_n=$((legs_n + 1))
  LEG_NAME[$legs_n]=$1
  LEG_DIR="$LEGS/$legs_n"
  mkdir -p "$LEG_DIR/tmp"
  LEG_OUT="$LEG_DIR/out"
  : >"$LEG_OUT"
  read -r -n 1 -u 9 _leg_token
}

# Job side, first command of the leg: its own verdict, its own TMPDIR, and the token back on exit.
# The token returns from an EXIT trap, which runs on `exit` — every leg ends in `exit "$fail"`.
leg_enter() {
  fail=0
  TMPDIR="$LEG_DIR/tmp"
  export TMPDIR
  trap 'printf . >&9' EXIT
}

# Parent side, right after the `&`.
started() { LEG_PID[$legs_n]=$1; }

# Print every leg not yet printed, in file order, waiting for each; fold its status into fail.
legs_report() {
  local i rc pid
  while [ "$legs_printed" -lt "$legs_n" ]; do
    legs_printed=$((legs_printed + 1))
    i=$legs_printed
    pid="${LEG_PID[$i]:-}"
    if [ -z "$pid" ]; then
      echo "FAIL: leg '${LEG_NAME[$i]}' was opened but never started"
      fail=1
      continue
    fi
    wait "$pid"
    rc=$?
    cat "$LEGS/$i/out"
    if [ "$rc" -ne 0 ]; then
      echo "FAIL: leg '${LEG_NAME[$i]}' exited $rc"
      fail=1
    fi
  done
}

legs_finish() {
  legs_report
  exec 9>&-
  if [ "$fail" -eq 0 ]; then
    rm -rf "$LEGS"
  else
    echo "leg outputs and temporary directories kept at $LEGS"
  fi
}

self_test() {
  local lib work failures=0 pid dog rc case_out
  lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  work="$(mktemp -d "${TMPDIR:-/tmp}/parallel-legs-test.XXXXXX")" || return 1

  # One planted umbrella: a header, the legs read from stdin, and the finish.
  plant() {
    { printf '#!/usr/bin/env bash\nset -u\nfail=0\n. "%s"\nlegs_init || exit 1\n' "$lib"
      cat
      printf 'legs_finish\nexit "$fail"\n'; } >"$work/$1.sh"
  }
  # Run it with a cap and a watchdog: a leg that never returns its token hangs the umbrella,
  # and a hang must fail this control by name rather than hang it.
  run() {
    local name=$1 jobs=$2
    PARITY_JOBS=$jobs bash "$work/$name.sh" >"$work/$name.out" 2>&1 &
    pid=$!
    ( sleep 30; kill -9 "$pid" 2>/dev/null ) &
    dog=$!
    wait "$pid"
    rc=$?
    kill "$dog" 2>/dev/null
    wait "$dog" 2>/dev/null
    case_out="$work/$name.out"
    [ "$rc" -ne 137 ] || { echo "FAIL: parallel-legs self-test: '$name' hung past 30 s"; failures=$((failures + 1)); }
  }
  expect() {   # name, condition description, test result
    [ "$3" = 0 ] || { echo "FAIL: parallel-legs self-test: '$1' — $2"; failures=$((failures + 1)); }
  }

  # Positive control first: two passing legs, the slower one first, print in file order.
  plant order <<'LEGS'
leg "slow"; { leg_enter
sleep 0.5; echo "first leg"
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
leg "fast"; { leg_enter
echo "second leg"
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
LEGS
  run order 4
  expect order "exit 0 with two passing legs (got $rc)" "$([ "$rc" = 0 ]; echo $?)"
  expect order "output in file order, not finishing order" \
    "$([ "$(grep -E '^(first|second) leg$' "$case_out" | tr '\n' ,)" = "first leg,second leg," ]; echo $?)"
  if [ "$failures" -ne 0 ]; then
    echo "FAIL: parallel-legs self-test: the positive control failed, so the mutations below would prove nothing"
    cat "$case_out"
    rm -rf "$work"
    return 1
  fi

  # Concurrency is real: the first leg waits for a file only the second leg writes.
  plant meet <<'LEGS'
leg "waiter"; { leg_enter
n=0; while [ ! -e "$MEET" ] && [ "$n" -lt 20 ]; do sleep 0.1; n=$((n + 1)); done
[ -e "$MEET" ] || { echo "FAIL: waiter never saw the other leg"; fail=1; }
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
leg "writer"; { leg_enter
: >"$MEET"
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
LEGS
  MEET="$work/meet.flag" run meet 2
  expect meet "two legs with two slots ran at once (got $rc)" "$([ "$rc" = 0 ]; echo $?)"
  # ...and the cap holds: with one slot the writer cannot start until the waiter gives up.
  rm -f "$work/meet.flag"
  cp "$work/meet.sh" "$work/meet-capped.sh"
  MEET="$work/meet.flag" run meet-capped 1
  expect meet-capped "PARITY_JOBS=1 ran the legs one at a time (got $rc)" "$([ "$rc" != 0 ]; echo $?)"

  # More legs than slots: every token comes back, or this hangs into the watchdog.
  { i=1; while [ "$i" -le 6 ]; do
      printf 'leg "l%s"; { leg_enter\nsleep 0.2; echo "leg %s"\nexit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!\n' "$i" "$i"
      i=$((i + 1)); done; } | plant tokens
  run tokens 2
  expect tokens "six legs through two slots all finished (got $rc)" "$([ "$rc" = 0 ]; echo $?)"
  expect tokens "all six outputs printed" "$([ "$(grep -c '^leg [1-6]$' "$case_out")" = 6 ]; echo $?)"

  # Failure by name, three ways: loudly, silently, and killed mid-run.
  plant loud <<'LEGS'
leg "passing"; { leg_enter
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
leg "planted-loud"; { leg_enter
false || { echo "FAIL: planted check"; fail=1; }
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
LEGS
  run loud 4
  expect loud "a failing leg fails the umbrella (got $rc)" "$([ "$rc" != 0 ]; echo $?)"
  expect loud "the failing leg is named" "$(grep -qx "FAIL: leg 'planted-loud' exited 1" "$case_out"; echo $?)"
  expect loud "the leg's own message is kept" "$(grep -qx 'FAIL: planted check' "$case_out"; echo $?)"

  plant silent <<'LEGS'
leg "planted-silent"; { leg_enter
false || fail=1
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
leg "passing"; { leg_enter
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
LEGS
  run silent 4
  expect silent "a leg that fails printing nothing fails the umbrella (got $rc)" "$([ "$rc" != 0 ]; echo $?)"
  expect silent "and is named" "$(grep -qx "FAIL: leg 'planted-silent' exited 1" "$case_out"; echo $?)"

  plant killed <<'LEGS'
leg "planted-killed"; { leg_enter
kill -9 "$(exec sh -c 'echo $PPID')"
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
leg "after"; { leg_enter
echo "after ran"
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
LEGS
  run killed 2
  expect killed "a killed leg fails the umbrella (got $rc)" "$([ "$rc" != 0 ] && [ "$rc" != 137 ]; echo $?)"
  expect killed "and is named with its signal status" "$(grep -qx "FAIL: leg 'planted-killed' exited 137" "$case_out"; echo $?)"
  expect killed "the legs after it still ran" "$(grep -qx 'after ran' "$case_out"; echo $?)"

  # Each leg has its own TMPDIR, inside the run's directory, removed when everything passed.
  plant tmp <<'LEGS'
leg "t1"; { leg_enter
echo "tmp $TMPDIR"; : >"$TMPDIR/same-name"
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
leg "t2"; { leg_enter
echo "tmp $TMPDIR"; [ ! -e "$TMPDIR/same-name" ] || { echo "FAIL: shared TMPDIR"; fail=1; }
exit "$fail"; } >"$LEG_OUT" 2>&1 </dev/null & started $!
LEGS
  TMPDIR="$work" run tmp 1
  expect tmp "separate TMPDIRs (got $rc)" "$([ "$rc" = 0 ]; echo $?)"
  expect tmp "two distinct TMPDIRs" "$([ "$(grep -c '^tmp ' "$case_out")" = 2 ] && [ "$(grep '^tmp ' "$case_out" | sort -u | wc -l | tr -d ' ')" = 2 ]; echo $?)"
  expect tmp "the run's directory is removed after a pass" \
    "$(! ls -d "$work"/parity.* >/dev/null 2>&1; echo $?)"

  # A cap that is not a positive integer is refused by name.
  plant badcap </dev/null
  run badcap abc
  expect badcap "PARITY_JOBS=abc refused (got $rc)" "$([ "$rc" != 0 ]; echo $?)"
  expect badcap "and named" "$(grep -q "PARITY_JOBS must be a positive integer" "$case_out"; echo $?)"

  rm -rf "$work"
  if [ "$failures" -ne 0 ]; then
    echo "parallel-legs --self-test: $failures control(s) failed"
    return 1
  fi
  echo "parallel-legs --self-test: OK (positive order control, concurrency, cap, tokens, loud/silent/killed failures, TMPDIR isolation, cap refusal)"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  case "${1:-}" in
    --self-test) set -u; self_test; exit $? ;;
    *) echo "usage: bash gates/parallel-legs.sh --self-test  (the umbrella sources this file)"; exit 2 ;;
  esac
fi
