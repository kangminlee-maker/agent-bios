#!/usr/bin/env bash
# claude-run.sh — thin, controllable raw adapter around `claude -p`.
#
# The claude-side twin of codex-run. Both exist for the same reason: a review
# dispatch has to name the seat it actually ran on, and a raw CLI call does not.
# Until this file existed the asymmetry was silent — the codex host dispatched
# reviews through our adapter while the claude host dispatched the bare binary,
# so half of every cross-family review had no place to report from.
#
# It is an adapter, not a policy boundary. Callers passing expert overrides after
# `--` are making expert decisions, exactly as with codex-run.
#
#   (1) seat            --model + --effort, both REQUIRED (see below)
#   (2) mutation reach  --permission-mode, defaulting to a no-edit posture
#   (3) prompt          read from stdin; the final message goes to stdout
#
# --model and --effort are required rather than optional, which is the one place
# this diverges from codex-run. codex-run tolerates an unpinned dispatch and warns,
# and that warning goes to a channel nobody reads; an unpinned review is the exact
# failure the receipt contract exists to catch, so here it is refused up front.
#
# NOT A SANDBOX. codex-run's `--sandbox read-only` is enforced by the OS; Claude Code
# has no equivalent, so the default here denies the mutating TOOLS and nothing more.
# A reviewer reading a self-contained packet on stdin needs no more reach than that,
# but do not read the two adapters' defaults as equivalent guarantees.
#
# Receipts: when REVIEW_RECEIPT_DIR is set, this adapter records what it observed —
# argv-independent facts only: exit status, a hash of the packet it fed the tool, a
# hash of the bytes the tool returned, and the seat it actually sent. Unset, it
# behaves exactly as it would without this block and writes nothing.
#
# Verified against claude 2.1.221.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: claude-run.sh --model M --effort E [--permission-mode MODE] [--cd DIR]
                     [-- ARG ...]  < packet
  --model M    model to pin (required)
  --effort E   reasoning effort to pin (required)
  --permission-mode MODE
               claude permission mode (default: the no-edit posture below)
  --cd DIR     working root
  --           everything after is passed to claude verbatim (expert override)

Environment (the adapter calling convention; all optional):
  REVIEW_RECEIPT_DIR   directory to write one ReviewReceipt/v1 into
  REVIEW_METHOD_ID     the review method this dispatch serves
  REVIEW_ORDERING_SEED, REVIEW_SWAP_GROUP
                       the orchestrator's panel controls, copied into the receipt
USAGE
}

model=""
effort=""
permission_mode=""
cd_dir=""
passthrough=()

while [ $# -gt 0 ]; do
  case "$1" in
    --model)  model="${2:?--model needs a value}"; shift 2 ;;
    --effort) effort="${2:?--effort needs a value}"; shift 2 ;;
    --permission-mode) permission_mode="${2:?--permission-mode needs a value}"; shift 2 ;;
    --cd)     cd_dir="${2:?--cd needs a value}"; shift 2 ;;
    --)       shift; while [ $# -gt 0 ]; do passthrough+=("$1"); shift; done ;;
    -p|--print) shift ;;   # already implied; a caller carrying it over is not an error
    -)        shift ;;
    -h|--help) usage; exit 0 ;;
    # Forwarded rather than refused. This adapter is on the dispatch path now, and a
    # caller that reached for one of claude's own flags should get claude's behaviour
    # and claude's error message — not exit 2 from the wrapper, which reads as "the
    # reviewer is broken" and takes the review down with it.
    *) passthrough+=("$1"); shift ;;
  esac
done

if [ -z "$model" ] || [ -z "$effort" ]; then
  # Warn and dispatch, matching codex-run. Refusing outright was right while nothing
  # called this file; on the live path it converts "the review ran unpinned" into "the
  # review did not run", and the honest signal already exists — an unpinned dispatch
  # can name no seat, so no receipt is emitted and the method adjudicates to UNKNOWN.
  echo "claude-run: WARNING: no --model/--effort pin; the seat cannot be named and this" >&2
  echo "            dispatch will produce no receipt." >&2
fi

# Built conditionally: an empty pin must be ABSENT, not passed as `--model ""`, which
# claude rejects — that would turn the warning above back into the hard failure it
# deliberately stopped being.
args=(-p)
if [ -n "$model" ];  then args+=(--model "$model"); fi
if [ -n "$effort" ]; then args+=(--effort "$effort"); fi
if [ -n "$permission_mode" ]; then
  args+=(--permission-mode "$permission_mode")
else
  # Deny the mutating tools rather than picking a permission mode: `plan` would also
  # reframe the task as planning, and a reviewer asked for a plan writes one.
  args+=(--disallowed-tools Edit Write NotebookEdit)
fi
if [ -n "$cd_dir" ]; then args+=(--add-dir "$cd_dir"); fi
if [ "${#passthrough[@]}" -gt 0 ]; then args+=("${passthrough[@]}"); fi

# `--cd` names the working root, exactly as codex-run's does, and claude has no flag
# that carries that meaning — `--add-dir` widens what the tool may reach and moves the
# working root nowhere. So the directory is entered for the dispatch itself. The old
# `--add-dir`-only form is kept above rather than replaced: after the cd the root is
# reachable anyway, but a caller reading the argv sees the reach it asked for named.
if [ -n "$cd_dir" ]; then
  if [ ! -d "$cd_dir" ]; then
    echo "claude-run: --cd: not a directory: $cd_dir" >&2
    exit 2
  fi
fi

# The seat the tool ACTUALLY ran on, read back out of the assembled argv rather than
# taken from this wrapper's own pins. Claude takes the LAST --model/--effort on its
# command line (verified against 2.1.232 with a reversed-order control), and this
# adapter forwards expert overrides verbatim by design — so `--model A -- --model B`
# dispatches B. Reporting `$model` there would put a seat in the receipt that nothing
# ran on, which is the single failure the receipt exists to make impossible.
last_flag_value() {
  local flag="$1"; shift
  local found="" i=0 argc=$#
  local -a scan=("$@")
  while [ "$i" -lt "$argc" ]; do
    case "${scan[$i]}" in
      "$flag") if [ $((i + 1)) -lt "$argc" ]; then found="${scan[$((i + 1))]}"; fi ;;
      "$flag"=*) found="${scan[$i]#*=}" ;;
    esac
    i=$((i + 1))
  done
  printf '%s' "$found"
}
sent_model="$(last_flag_value --model "${args[@]}")"
sent_effort="$(last_flag_value --effort "${args[@]}")"

# Dispatching in a subshell keeps the cd off every path that runs afterwards: the
# receipt's own temp dir, the launcher lookup and a relative REVIEW_RECEIPT_DIR all
# resolve against the caller's cwd exactly as they did before this flag worked.
dispatch_claude() {
  if [ -n "$cd_dir" ]; then
    ( cd "$cd_dir" && exec claude "${args[@]}" )
  else
    claude "${args[@]}"
  fi
}

cleanup_paths=()
cleanup_all() {
  if [ "${#cleanup_paths[@]}" -gt 0 ]; then
    for p in "${cleanup_paths[@]}"; do rm -rf "$p"; done
  fi
}
trap cleanup_all EXIT

# Dispatch audit, mirroring codex-run: the line goes to the log file only, because
# stdout carries the review result and stderr carries claude's own progress.
log_home="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
mkdir -p "$log_home/log" 2>/dev/null || true
printf '%s dispatch model=%s effort=%s permission=%s\n' \
  "$(date +%Y-%m-%dT%H:%M:%S%z)" "${sent_model:-UNPINNED}" "${sent_effort:-UNPINNED}" \
  "${permission_mode:-no-edit-tools}" \
  >> "$log_home/log/claude-run-dispatch.log" 2>/dev/null || true

emit_receipt() {
  # Recording never breaks dispatch: every failure here is a warning and the tool's
  # own exit status is what this script returns. A missing receipt adjudicates to
  # UNKNOWN, which is the honest outcome — silence is not evidence of failure.
  local status="$1" packet="$2" result="$3" launcher
  launcher="${AGENT_LAUNCH_BIN:-$HOME/.local/bin/agent-launch}"
  if [ ! -x "$launcher" ]; then
    launcher="$(command -v agent-launch 2>/dev/null || true)"
  fi
  if [ -z "$launcher" ]; then
    echo "claude-run: WARNING: agent-launch not found; no receipt emitted" >&2
    return 0
  fi
  if [ -z "${REVIEW_METHOD_ID:-}" ]; then
    echo "claude-run: WARNING: REVIEW_METHOD_ID unset; the receipt will name no method" >&2
  fi
  # The provider is core knowledge and not a flag: this adapter reaches exactly one
  # family, so letting a caller name a different one would only ever be a false claim.
  "$launcher" --emit-receipt "${REVIEW_METHOD_ID:-}" "anthropic:$sent_model/$sent_effort" \
    "$status" "$packet" "$result" >/dev/null \
    || echo "claude-run: WARNING: receipt not emitted" >&2
}

if [ -n "${REVIEW_RECEIPT_DIR:-}" ]; then
  work="$(mktemp -d "${TMPDIR:-/tmp}/claude-run-XXXXXX")"
  cleanup_paths+=("$work")
  # stdin is captured rather than inherited ONLY on this branch: hashing the packet
  # requires holding it, and teeing stdout requires a pipe. Both change the channel
  # shape, so neither is reached unless a receipt was actually asked for.
  cat > "$work/packet"
  set +e
  dispatch_claude < "$work/packet" | tee "$work/result"
  status=${PIPESTATUS[0]}
  set -e
  emit_receipt "$status" "$work/packet" "$work/result"
else
  set +e
  dispatch_claude
  status=$?
  set -e
fi

exit "$status"
