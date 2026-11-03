#!/usr/bin/env bash
# claude-run.sh — thin, controllable raw adapter around `claude -p`.
#
# Records the selected review seat and observed dispatch result when both seat
# pins and receipt configuration are present.
#
# It is an adapter, not a policy boundary. Callers passing expert overrides after
# `--` are making expert decisions, exactly as with codex-run.
#
#   (1) seat            --model + --effort, both needed for a receipt
#   (2) mutation reach  --permission-mode, defaulting to a no-edit posture
#   (3) prompt          read from stdin; the final message goes to stdout
#
# If either pin is missing, warn on stderr and dispatch without a receipt.
# An unpinned invocation cannot provide a named-seat review claim.
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
# Profiles (instruction/config reach), the vocabulary codex-run uses:
#   inherit  (default)  the caller's HOME and CLAUDE_CONFIG_DIR: the owner's CLAUDE.md files,
#                       skills, settings and memory all load. The argv is the one this adapter
#                       has always sent.
#   hermetic            one call in a cell — a fresh HOME, CLAUDE_CONFIG_DIR and working
#                       directory, under a root outside the caller's HOME — with an environment
#                       built from scratch, the subscription token in the child environment only,
#                       and `--safe-mode --setting-sources "" --strict-mcp-config
#                       --disable-slash-commands --tools ""`: no CLAUDE.md from the working
#                       directory, its ancestors or the configuration home, no skill, no memory,
#                       no MCP server, no hook. The session is persisted, because its transcript
#                       is the only record of what the host loaded, and
#                       claude_hermetic_evidence.py (beside this file, never looked up anywhere
#                       else) renders it into REVIEW_CAPTURE_DIR/host.json. Declared instructions
#                       reach the call only through --append-system-prompt-file with the sha256
#                       they were declared at. `--use producing` grants Read alone, confined to
#                       the --manifest directory by a path-scoped allow rule.
#
# Verified against claude 2.1.221 (inherit). The hermetic flag set is verified per host version by
# the author-side re-pin, on the version session-distill/seats.json pins.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: claude-run.sh [--profile inherit|hermetic] [--model M --effort E]
                     [--permission-mode MODE] [--cd DIR] [--schema FILE]
                     [--max-output-tokens N] [-- ARG ...]  < packet
       claude-run.sh --profile hermetic --call-id ID (--cell-root DIR | DISTILL_CELL)
                     --claude-bin PATH --host-version V
                     [--use judge|producing|authoring] [--tools Read --manifest DIR]
                     [--append-system-prompt-file F --declared-sha256 H]... ...  < packet
  --profile    instruction/config reach (default: inherit)
                 inherit  the caller's HOME and CLAUDE_CONFIG_DIR, everything they load
                 hermetic a fresh cell per call: no CLAUDE.md, skill, memory, MCP server or
                          hook of the caller's, the token in the child environment only
  --model M    model to pin (required for a receipt)
  --effort E   reasoning effort to pin (required for a receipt)
  --permission-mode MODE
               claude permission mode (default: the no-edit posture below; inherit only)
  --cd DIR     working root (hermetic default: the cell's own empty working directory)
  --schema F   --json-schema: the final result carries structured_output for this schema
  --max-output-tokens N
               CLAUDE_CODE_MAX_OUTPUT_TOKENS for the call; a longer answer ends max_tokens
  --claude-bin PATH --host-version V
               the versioned claude executable (never a symlink) and the version it must
               report; a mismatch is refused as HOST_VERSION_MISMATCH (required by hermetic)
  --call-id ID the call this dispatch serves; names the cell (hermetic)
  --cell-root DIR
               where the cell <DIR>/<ID>/{home,config,cwd} is made and, after the call,
               deleted. It may not lie under the operator's home, must be the operator's
               own with mode 700, and neither it nor an ancestor may hold CLAUDE.md,
               CLAUDE.local.md, AGENTS.md, .claude/, .codex/, .mcp.json or a settings file
  --use U      judge (default) or authoring: no tools at all; producing: Read only
  --tools Read --manifest DIR
               the producing profile's one tool, allowed inside DIR and refused elsewhere
  --append-system-prompt-file F --declared-sha256 H
               a declared instruction file and the sha256 it was declared at (repeatable);
               the capture records the sha256 of what was sent, so an edit after the
               declaration is visible to the gate
  --server-policy FILE
               the run's server-policy record (what --server-policy-probe printed), stated in
               the capture's and the receipt's hermeticity; without it the server-delivered
               policy is recorded as unknown, never as clean (hermetic)
  --server-policy-probe
               make no call: run `claude doctor` once in the cell, with the call's environment
               and stdin closed, and print as one JSON line the status of its "Managed
               settings (remote):" line and the verdict (clean, not confirmed, unknown);
               nothing else of its output is kept (hermetic)
  --           everything after is passed to claude verbatim (expert override); under
               hermetic it changes the recorded flag-set hash

If either seat pin is missing, dispatch continues with a warning and no receipt.

Environment (the adapter calling convention; all optional):
  REVIEW_RECEIPT_DIR   directory to write one ReviewReceipt/v1 into
  REVIEW_METHOD_ID     the review method this dispatch serves
  REVIEW_ORDERING_SEED, REVIEW_SWAP_GROUP
                       the orchestrator's panel controls, copied into the receipt
  REVIEW_CAPTURE_DIR   directory for the call's capture: stream.jsonl (hermetic, appended as
                       it arrives), host.json and actions.jsonl
  DISTILL_CELL         a cell {home,config,cwd} the caller made and deletes itself
  DISTILL_CALL_ID      the call id when --call-id is not given
  CLAUDE_RUN_TOKEN_FILE
                       a file holding CLAUDE_CODE_OAUTH_TOKEN=...; read into the child
                       environment only (hermetic; otherwise CLAUDE_CODE_OAUTH_TOKEN is used)

A dispatcher calls one hermetic Claude call as (the arguments in brackets per call):
  claude-run.sh --profile hermetic --model M --effort E --cell-root ROOT --call-id ID --cd CWD
                --claude-bin VERSIONED_PATH --host-version V --max-output-tokens N [--schema F]
                [--use producing --tools Read --manifest DIR] [--server-policy FILE]
  with DISTILL_CELL (the cell it made under ROOT), REVIEW_CAPTURE_DIR and the token in the
  environment; the packet on stdin; the result object on stdout; exit status mirrored.
  Once per run, before the first such call, it asks for the server-policy record as
  claude-run.sh --profile hermetic --server-policy-probe --cell-root ROOT --call-id ID
                --claude-bin VERSIONED_PATH --host-version V
  with DISTILL_CELL and the token in the environment, and hands the record to every call.
USAGE
}

# The profile decides what several claude flags mean here, so it is read before the rest.
profile=inherit
scan=("$@")
i=0
while [ "$i" -lt "${#scan[@]}" ]; do
  case "${scan[$i]}" in
    --) break ;;
    --profile) profile="${scan[$((i + 1))]:-}"; i=$((i + 1)) ;;
    --profile=*) profile="${scan[$i]#*=}" ;;
  esac
  i=$((i + 1))
done
case "$profile" in
  inherit|hermetic) ;;
  *) echo "claude-run: --profile must be inherit|hermetic" >&2; exit 2 ;;
esac

model=""
effort=""
permission_mode=""
cd_dir=""
passthrough=()
call_id="${DISTILL_CALL_ID:-}"
cell_root=""
claude_bin=""
host_version=""
schema=""
max_output=""
use=""
tools=""
manifest=""
server_policy=""
server_policy_probe=0
append_files=()
append_declared=()

while [ $# -gt 0 ]; do
  case "$1" in
    --profile) shift 2 ;;
    --profile=*) shift ;;
    --model)  model="${2:?--model needs a value}"; shift 2 ;;
    --effort) effort="${2:?--effort needs a value}"; shift 2 ;;
    --permission-mode) permission_mode="${2:?--permission-mode needs a value}"; shift 2 ;;
    --cd)     cd_dir="${2:?--cd needs a value}"; shift 2 ;;
    # Not claude flags: before this adapter knew them they reached claude and failed there.
    --call-id) call_id="${2:?--call-id needs a value}"; shift 2 ;;
    --cell-root) cell_root="${2:?--cell-root needs a value}"; shift 2 ;;
    --claude-bin) claude_bin="${2:?--claude-bin needs a value}"; shift 2 ;;
    --host-version) host_version="${2:?--host-version needs a value}"; shift 2 ;;
    --schema) schema="${2:?--schema needs a value}"; shift 2 ;;
    --max-output-tokens) max_output="${2:?--max-output-tokens needs a value}"; shift 2 ;;
    --use|--manifest|--declared-sha256|--server-policy)
      if [ "$profile" != hermetic ]; then
        echo "claude-run: $1 applies only to --profile hermetic" >&2; exit 2
      fi
      case "$1" in
        --use) use="${2:?--use needs a value}" ;;
        --manifest) manifest="${2:?--manifest needs a value}" ;;
        --declared-sha256) append_declared+=("${2:?--declared-sha256 needs a value}") ;;
        --server-policy) server_policy="${2:?--server-policy needs a value}" ;;
      esac
      shift 2 ;;
    --server-policy-probe)
      if [ "$profile" != hermetic ]; then
        echo "claude-run: $1 applies only to --profile hermetic" >&2; exit 2
      fi
      server_policy_probe=1; shift ;;
    # claude's own flags, which the hermetic profile owns: under inherit they are forwarded
    # one token at a time, exactly as before the profile existed.
    --tools|--append-system-prompt-file)
      if [ "$profile" = hermetic ]; then
        if [ "$1" = --tools ]; then tools="${2?--tools needs a value}"
        else append_files+=("${2:?--append-system-prompt-file needs a value}"); fi
        shift 2
      else
        passthrough+=("$1"); shift
      fi ;;
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

case "$max_output" in
  ''|*[!0-9]*) [ -z "$max_output" ] || { echo "claude-run: --max-output-tokens must be a whole number" >&2; exit 2; } ;;
esac
if [ -n "$schema" ] && [ ! -f "$schema" ]; then
  echo "claude-run: --schema: not a file: $schema" >&2
  exit 2
fi
if [ "$profile" = hermetic ]; then
  use="${use:-judge}"
  case "$use" in
    judge|authoring)
      if [ -n "$tools" ] || [ -n "$manifest" ]; then
        echo "claude-run: --use $use grants no tool; --tools and --manifest are the producing profile's" >&2; exit 2
      fi ;;
    producing)
      # Read is the one tool the host path-scopes; Grep, Glob and Bash it does not, so search
      # is done before dispatch and a request for any of them is refused as ungranted.
      if [ "$tools" != Read ] || [ -z "$manifest" ]; then
        echo "claude-run: --use producing needs --tools Read and --manifest DIR" >&2; exit 2
      fi
      if [ ! -d "$manifest" ]; then
        echo "claude-run: --manifest: not a directory: $manifest" >&2; exit 2
      fi
      manifest="$(cd -P "$manifest" && pwd)" ;;
    *) echo "claude-run: --use must be judge|producing|authoring" >&2; exit 2 ;;
  esac
  if [ -n "$permission_mode" ]; then
    echo "claude-run: --permission-mode is fixed by --profile hermetic" >&2; exit 2
  fi
  if [ "${#append_files[@]}" -ne "${#append_declared[@]}" ]; then
    echo "claude-run: every --append-system-prompt-file needs its --declared-sha256" >&2; exit 2
  fi
  if [ "${#append_files[@]}" -gt 0 ]; then
    for f in "${append_files[@]}"; do
      [ -f "$f" ] || { echo "claude-run: --append-system-prompt-file: not a file: $f" >&2; exit 2; }
    done
  fi
  case "$call_id" in
    ''|.|..|*/*) echo "claude-run: --profile hermetic needs a --call-id (a plain name)" >&2; exit 2 ;;
  esac
  if [ -z "$claude_bin" ] || [ -z "$host_version" ]; then
    echo "claude-run: --profile hermetic needs --claude-bin PATH and --host-version V (the pinned host)" >&2; exit 2
  fi
fi
if [ -n "$claude_bin" ]; then
  # The versioned file itself: a symlink is what an auto-update moves between two calls of one run.
  if [ -z "$host_version" ]; then
    echo "claude-run: --claude-bin needs the --host-version it is pinned at" >&2; exit 2
  fi
  if [ -L "$claude_bin" ] || [ ! -f "$claude_bin" ] || [ ! -x "$claude_bin" ]; then
    echo "claude-run: HOST_BINARY_UNPINNED --claude-bin must be the versioned executable, not a symlink: $claude_bin" >&2
    exit 2
  fi
  claude_bin="$(cd -P "$(dirname "$claude_bin")" && pwd)/$(basename "$claude_bin")"
fi

if [ "$server_policy_probe" = 0 ] && { [ -z "$model" ] || [ -z "$effort" ]; }; then
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
profile_flags=()
if [ "$profile" = hermetic ]; then
  # The flag set seats.json pins per host version (session-distill/seats.json, author-side):
  # --bare is not usable, because it never reads the subscription token.
  profile_flags=(--safe-mode --setting-sources "" --strict-mcp-config --disable-slash-commands)
  if [ "$use" = producing ]; then
    # `//` anchors the rule at the filesystem root; under -p a request no allow rule covers
    # is refused without a prompt (dontAsk), and the refusal is recorded in the transcript.
    profile_flags+=(--tools Read --allowedTools "Read(/$manifest/**)" --permission-mode dontAsk)
  else
    profile_flags+=(--tools "")
  fi
  args+=(--output-format stream-json --verbose --include-partial-messages "${profile_flags[@]}")
elif [ -n "$permission_mode" ]; then
  profile_flags=(--permission-mode "$permission_mode")
  args+=("${profile_flags[@]}")
else
  # Deny the mutating tools rather than picking a permission mode: `plan` would also
  # reframe the task as planning, and a reviewer asked for a plan writes one.
  profile_flags=(--disallowed-tools Edit Write NotebookEdit)
  args+=("${profile_flags[@]}")
fi
if [ -n "$cd_dir" ] && [ "$profile" = inherit ]; then
  args+=(--add-dir "$cd_dir")
  profile_flags+=(--add-dir "$cd_dir")
fi
if [ -n "$schema" ]; then args+=(--json-schema "$(cat "$schema")"); fi

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

cleanup_paths=()
cleanup_all() {
  if [ "${#cleanup_paths[@]}" -gt 0 ]; then
    for p in "${cleanup_paths[@]}"; do rm -rf "$p"; done
  fi
}
trap cleanup_all EXIT

# The evidence helper travels beside this file and is never looked up anywhere else: a
# copy found in a checkout or on PATH would render a capture with code the release did
# not ship. Symlinks are resolved first, so a linked adapter still finds its own sibling.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  LINKDIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  case "$SOURCE" in
    /*) ;;
    *) SOURCE="$LINKDIR/$SOURCE" ;;
  esac
done
helper="$(cd -P "$(dirname "$SOURCE")" && pwd)/claude_hermetic_evidence.py"

cell="${DISTILL_CELL:-}"
capture="${REVIEW_CAPTURE_DIR:-}"
run_token=""
session_id=""
# The inherit profile renders evidence only inside a cell: outside one, its configuration
# home is the owner's, and nothing of the owner's is copied into a capture.
needs_evidence=0
if [ "$profile" = hermetic ] || { [ -n "$cell" ] && [ -n "$capture" ]; }; then needs_evidence=1; fi
if [ "$needs_evidence" = 1 ]; then
  if [ ! -f "$helper" ]; then
    echo "claude-run: the evidence helper is missing beside the adapter: $helper" >&2
    exit 2
  fi
  command -v python3 >/dev/null 2>&1 || { echo "claude-run: python3 is required by $helper" >&2; exit 2; }
fi

# Builtins only: the token never reaches an argv (where any process listing shows it), a
# file or a log. It goes to the child's environment and nowhere else.
read_token() {
  local line
  if [ -n "${CLAUDE_RUN_TOKEN_FILE:-}" ]; then
    [ -r "$CLAUDE_RUN_TOKEN_FILE" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line#export }"
      case "$line" in CLAUDE_CODE_OAUTH_TOKEN=*) run_token="${line#*=}" ;; esac
    done < "$CLAUDE_RUN_TOKEN_FILE"
    run_token="${run_token%\"}"; run_token="${run_token#\"}"
    run_token="${run_token%\'}"; run_token="${run_token#\'}"
  else
    run_token="${CLAUDE_CODE_OAUTH_TOKEN:-}"
  fi
  [ -n "$run_token" ]
}

# Plan P5, before anything is made: the cell root outside the operator's home (from the account
# database, so a HOME pointed elsewhere changes nothing), the operator's own, mode 700, and no
# instruction surface in it or any ancestor.
if [ "$profile" = hermetic ]; then
  python3 "$helper" check-root --root "${cell_root:-$(dirname "$cell")}" --home "$HOME" || exit 2
fi
if [ -n "$cell" ]; then
  for part in home config cwd; do
    [ -d "$cell/$part" ] || { echo "claude-run: DISTILL_CELL has no $part/ directory: $cell" >&2; exit 2; }
  done
elif [ "$profile" = hermetic ]; then
  if [ -z "$cell_root" ]; then
    echo "claude-run: --profile hermetic needs --cell-root DIR (or a DISTILL_CELL)" >&2
    exit 2
  fi
  [ -d "$cell_root" ] || mkdir -p -m 700 "$cell_root"
  cell="$cell_root/$call_id"
  if [ -e "$cell" ]; then
    echo "claude-run: the cell already exists: $cell" >&2
    exit 2
  fi
  mkdir -m 700 "$cell"
  cleanup_paths+=("$cell")   # this adapter made it, so it goes when the call is done
  mkdir "$cell/home" "$cell/config" "$cell/cwd"
fi

# Inside a cell the working directory is the cell's unless the caller names another.
if [ -n "$cell" ] && [ -z "$cd_dir" ]; then cd_dir="$cell/cwd"; fi
if [ "$profile" = hermetic ]; then
  mkdir -p "$cell/tmp"
  if ! read_token; then
    echo "claude-run: --profile hermetic needs the subscription token: CLAUDE_CODE_OAUTH_TOKEN," >&2
    echo "            or CLAUDE_RUN_TOKEN_FILE naming a file that holds CLAUDE_CODE_OAUTH_TOKEN=..." >&2
    exit 2
  fi
elif [ -n "$cell" ] && [ -n "${CLAUDE_RUN_TOKEN_FILE:-}" ]; then
  read_token || { echo "claude-run: CLAUDE_RUN_TOKEN_FILE holds no CLAUDE_CODE_OAUTH_TOKEN" >&2; exit 2; }
fi

# The cell used is the cell validated: it and its homes resolve beneath the checked root, and the
# producing profile reads only the working directory the manifest declares.
if [ "$profile" = hermetic ]; then
  python3 "$helper" bind --root "${cell_root:-$(dirname "$cell")}" --cell "$cell" --cwd "$cd_dir" \
    ${manifest:+--manifest "$manifest"} || exit 2
fi

# The pinned host must report the version its flag set was measured on (plan P2). Asked in an
# environment as bare as the call's, from inside the cell, so the question reads nothing of the
# caller's and writes nothing the call will see.
if [ -n "$claude_bin" ]; then
  version_dir="${cell:+$cell/tmp}"
  [ -z "$version_dir" ] || mkdir -p "$version_dir"
  reported="$(
    for name in $(compgen -e); do unset "$name" 2>/dev/null || true; done
    export PATH=/usr/bin:/bin:/usr/sbin:/sbin DISABLE_AUTOUPDATER=1
    if [ -n "$cell" ]; then export HOME="$cell/home" CLAUDE_CONFIG_DIR="$cell/config"; cd "$version_dir" || exit 1; fi
    exec "$claude_bin" --version </dev/null 2>/dev/null
  )" || true
  reported="${reported%%
*}"
  case "$reported" in
    "$host_version"|"$host_version "*) ;;
    *) echo "claude-run: HOST_VERSION_MISMATCH $claude_bin reports '${reported}', the call is pinned at $host_version" >&2
       exit 2 ;;
  esac
fi

# The server-delivered policy (D-20261102-252c92), asked once per run in a cell of its own with exactly
# the environment the call gets, so the organisation the token belongs to is the one reported. The
# helper runs `claude doctor` with stdin closed and a bound, and prints only the status of its one line.
if [ "$server_policy_probe" = 1 ]; then
  py="$(command -v python3)"
  (
    for name in $(compgen -e); do unset "$name" 2>/dev/null || true; done
    export PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$cell/home" CLAUDE_CONFIG_DIR="$cell/config" \
           TMPDIR="$cell/tmp" LANG=en_US.UTF-8 DISABLE_AUTOUPDATER=1
    export CLAUDE_CODE_OAUTH_TOKEN="$run_token"
    cd "$cd_dir" && exec "$py" "$helper" server-policy --claude-bin "$claude_bin"
  )
  exit $?
fi

work=""
if [ "$needs_evidence" = 1 ] || [ -n "${REVIEW_RECEIPT_DIR:-}" ]; then
  work="$(mktemp -d "${TMPDIR:-/tmp}/claude-run-XXXXXX")"
  cleanup_paths+=("$work")
fi
appended_names=()
appended_snaps=()
if [ "$needs_evidence" = 1 ]; then
  strict=()
  if [ "$profile" = hermetic ]; then strict=(--strict); fi
  session_id="$(python3 "$helper" prepare --cell "$cell" --cwd "${cd_dir:-$PWD}" --home "$HOME" \
                --out "$work/pre.json" ${strict[@]+"${strict[@]}"})" || exit 2
fi
if [ "$profile" = hermetic ]; then
  args+=(--session-id "$session_id")
  # Each declared file is read once, here, into the cell, and the call is given that copy:
  # what the host appends and what the capture hashes are then the same bytes, and an edit
  # made after the declaration shows as a different sha256 rather than racing the host.
  if [ "${#append_files[@]}" -gt 0 ]; then
    mkdir -p "$cell/declared"
    n=0
    for f in "${append_files[@]}"; do
      n=$((n + 1))
      snap="$cell/declared/$n-$(basename "$f")"
      cp "$f" "$snap"
      appended_names+=("$(basename "$f")")
      appended_snaps+=("$snap")
      args+=(--append-system-prompt-file "$snap")
    done
  fi
fi
if [ "${#passthrough[@]}" -gt 0 ]; then args+=("${passthrough[@]}"); fi

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

# Exactly these names reach the hermetic child; everything the caller exported is dropped.
child_env_names=(PATH HOME CLAUDE_CONFIG_DIR TMPDIR LANG DISABLE_AUTOUPDATER CLAUDE_CODE_OAUTH_TOKEN)
if [ -n "$max_output" ]; then child_env_names+=(CLAUDE_CODE_MAX_OUTPUT_TOKENS); fi

# Dispatching in a subshell keeps the cd off every path that runs afterwards: the
# receipt's own temp dir, the launcher lookup and a relative REVIEW_RECEIPT_DIR all
# resolve against the caller's cwd exactly as they did before this flag worked.
dispatch_claude() {
  if [ "$profile" = hermetic ]; then
    (
      for name in $(compgen -e); do unset "$name" 2>/dev/null || true; done
      export PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$cell/home" CLAUDE_CONFIG_DIR="$cell/config" \
             TMPDIR="$cell/tmp" LANG=en_US.UTF-8 DISABLE_AUTOUPDATER=1
      export CLAUDE_CODE_OAUTH_TOKEN="$run_token"
      if [ -n "$max_output" ]; then export CLAUDE_CODE_MAX_OUTPUT_TOKENS="$max_output"; fi
      cd "$cd_dir" && exec "$claude_bin" "${args[@]}"
    )
    return
  fi
  (
    # Inside a cell the inherit profile still loads whatever the cell holds — which is what
    # makes it the loading counterpart of hermetic — but never the owner's own homes.
    if [ -n "$cell" ]; then export HOME="$cell/home" CLAUDE_CONFIG_DIR="$cell/config"; fi
    if [ -n "$run_token" ]; then export CLAUDE_CODE_OAUTH_TOKEN="$run_token"; fi
    if [ -n "$max_output" ]; then export CLAUDE_CODE_MAX_OUTPUT_TOKENS="$max_output"; fi
    if [ -n "$cd_dir" ]; then cd "$cd_dir" || exit 1; fi
    exec "${claude_bin:-claude}" "${args[@]}"
  )
}

# Dispatch audit, mirroring codex-run: the line goes to the log file only, because
# stdout carries the review result and stderr carries claude's own progress.
log_home="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
mkdir -p "$log_home/log" 2>/dev/null || true
printf '%s dispatch model=%s effort=%s permission=%s profile=%s%s\n' \
  "$(date +%Y-%m-%dT%H:%M:%S%z)" "${sent_model:-UNPINNED}" "${sent_effort:-UNPINNED}" \
  "${permission_mode:-no-edit-tools}" "$profile" "${call_id:+ call=$call_id}" \
  >> "$log_home/log/claude-run-dispatch.log" 2>/dev/null || true

emit_receipt() {
  # Recording never breaks dispatch: every failure here is a warning and the tool's
  # own exit status is what this script returns. A missing receipt adjudicates to
  # UNKNOWN, which is the honest outcome — silence is not evidence of failure.
  local status="$1" packet="$2" result="$3" launcher
  shift 3
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
    "$status" "$packet" "$result" "$@" >/dev/null \
    || echo "claude-run: WARNING: receipt not emitted" >&2
}

stream=""
if [ "$profile" = hermetic ]; then
  # The stream is appended as it arrives, so a supervisor can follow the call live; stdout
  # carries only the closing result object, once the evidence is rendered.
  stream="${capture:-$work}/stream.jsonl"
  mkdir -p "$(dirname "$stream")"
  cat > "$work/packet"
  set +e
  dispatch_claude < "$work/packet" >> "$stream"
  status=$?
  set -e
elif [ -n "$work" ]; then
  # stdin is captured rather than inherited ONLY on this branch: hashing the packet
  # requires holding it, and teeing stdout requires a pipe. Both change the channel
  # shape, so neither is reached unless a receipt or a capture was actually asked for.
  cat > "$work/packet"
  set +e
  dispatch_claude < "$work/packet" | tee "$work/result"
  status=${PIPESTATUS[0]}
  set -e
  stream="$work/result"
else
  set +e
  dispatch_claude
  status=$?
  set -e
fi

if [ "$needs_evidence" = 1 ]; then
  render=(render --capture "${capture:-$work/capture}" --config "$cell/config" --listing "$work/pre.json"
          --stream "$stream" --call-id "$call_id" --profile "$profile" --binary "${claude_bin:-claude}"
          --evidence-out "$work/evidence")
  for f in ${profile_flags[@]+"${profile_flags[@]}"}; do render+=("--flag=$f"); done
  for f in ${passthrough[@]+"${passthrough[@]}"}; do render+=("--extra=$f"); done
  if [ -n "$schema" ]; then render+=(--schema "$schema"); fi
  if [ "$profile" = hermetic ]; then
    render+=(--session-id "$session_id" --use "$use" --print-result)
    if [ -n "$manifest" ]; then render+=(--manifest "$manifest"); fi
    if [ -n "$server_policy" ]; then render+=(--server-policy "$server_policy"); fi
    for n in "${child_env_names[@]}"; do render+=(--env-name "$n"); done
    i=0
    while [ "$i" -lt "${#appended_snaps[@]}" ]; do
      render+=(--appended-name "${appended_names[$i]}" --appended-file "${appended_snaps[$i]}"
               --appended-declared "${append_declared[$i]}")
      i=$((i + 1))
    done
    if python3 "$helper" "${render[@]}" > "$work/result"; then
      cat "$work/result"
    else
      # A hermetic call without its evidence is not a completed call, whatever claude said.
      echo "claude-run: the evidence of call $call_id could not be rendered" >&2
      [ "$status" -ne 0 ] || status=70
    fi
  elif ! python3 "$helper" "${render[@]}" >/dev/null; then
    echo "claude-run: WARNING: the evidence of call $call_id could not be rendered" >&2
  fi
  # A cell this adapter made is deleted on exit; its transcripts are evidence, kept first.
  if [ -n "$capture" ] && [ -z "${DISTILL_CELL:-}" ] && [ -d "$cell/config/projects" ]; then
    cp -R "$cell/config/projects" "$capture/transcripts"
  fi
fi

if [ -n "${REVIEW_RECEIPT_DIR:-}" ]; then
  evidence=()
  if [ -f "$work/evidence" ]; then
    while IFS= read -r line; do evidence+=(--evidence "$line"); done < "$work/evidence"
  fi
  emit_receipt "$status" "$work/packet" "$work/result" ${evidence[@]+"${evidence[@]}"}
fi

exit "$status"
