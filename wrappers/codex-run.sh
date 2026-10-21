#!/usr/bin/env bash
# codex-run.sh — thin, controllable raw adapter around `codex exec`.
#
# Purpose: let a caller (e.g. Claude driving Codex CLI) control, per invocation,
# the three levers that otherwise silently vary by consumer — raw Codex CLI and
# codex-plugin-cc inherit the real ~/.codex (AGENTS.md + full config.toml), while
# a hermetic reviewer must see none of it (no AGENTS.md, minimal config). This
# raw adapter makes that choice explicit instead of implicit. It is not a policy
# boundary; callers that pass -c are making expert overrides:
#   (1) AGENTS.md / global instructions   — via CODEX_HOME (the --profile)
#   (2) config.toml                        — via --profile + Codex config profile + -c overrides
#   (3) per-task prompt + output schema    — via stdin + --schema
#
# Profiles (instruction/config reach):
#   inherit  (default)  real CODEX_HOME → global + project AGENTS.md + full config.toml
#   hermetic            fresh temp CODEX_HOME (auth copied only) + --ignore-user-config,
#                       an empty temp HOME, project_doc_max_bytes=0, cwd defaulting to an
#                       empty temp workspace → NO AGENTS.md (global or project, even with
#                       --cd inside a repository), NO user skills, NO user config: an
#                       independent, uncontaminated lens
#   custom  --home DIR  CODEX_HOME=DIR → exactly the AGENTS.md/config you place in DIR
#
# The prompt is read from stdin. `codex exec` writes the final message to stdout
# (with --schema, JSON conforming to the schema) and progress to stderr directly.
# Exit status mirrors `codex exec`.
#
# Receipts: when REVIEW_RECEIPT_DIR is set, this adapter records what it observed —
# exit status, a hash of the packet it fed codex, a hash of the bytes codex returned,
# and the seat it actually sent. Unset, it behaves exactly as it did before that block
# existed and writes nothing. The dispatch-audit line below predates receipts and stays:
# it is a human-readable trail, not an adjudicable record.
#
# Capture: with --capture DIR (or REVIEW_CAPTURE_DIR) and a call id (REVIEW_CALL_ID), the
# adapter records what this one call showed about itself into DIR, through
# codex_frame_filter.py beside the adapter: the effective context rendered beforehand with the
# call's own homes and overrides (prompt-input.txt, instruction-sources.json), codex's --json
# thread and turn events, the server's frames and otel rows reduced to an allow-list (no prompt
# or output text is kept), host.json and usage.json; the receipt carries the evidence keys.
# The frames come only from the caller's RUST_LOG (tungstenite::protocol=trace,
# codex_otel.log_only=info, codex_core::responses_retry=warn): without it the capture is
# silent and the call cannot be attested. stderr still carries codex's whole stream.
#
# Verified against codex-cli 0.144.1; capture against 0.163.0.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: codex-run.sh [--profile inherit|hermetic|custom] [--home DIR]
                    [--model M] [--effort E] [--sandbox MODE] [--cd DIR]
                    [--bypass-sandbox]
                    [--multi-agent auto|on|off]
                    [--schema FILE] [--codex-profile NAME] [-p NAME]
                    [--capture DIR] [-c key=value ...] [-]  < prompt
  --profile   instruction/config reach (default: inherit)
                inherit  real CODEX_HOME  -> global+project AGENTS.md + full config.toml
                hermetic temp CODEX_HOME + empty HOME -> NO AGENTS.md, NO user
                         skills, NO user config (auth only), even with --cd
                custom   CODEX_HOME=--home -> exactly what you place in that dir
  --home DIR  CODEX_HOME for --profile custom (required for custom)
  --model M   -m: model to use
  --effort E  reasoning effort (none|low|medium|high|xhigh|max|ultra); provider-enforced
  --sandbox   read-only (default) | workspace-write | danger-full-access
  --bypass-sandbox
              pass --dangerously-bypass-approvals-and-sandbox instead of --sandbox
  --multi-agent
              auto: on only at Ultra; on/off: explicit native multi-agent state
  --cd DIR    working root (-C): decides which project AGENTS.md is seen
  --schema F  --output-schema: force the final message to this JSON Schema
  -p NAME
  --codex-profile NAME
              Codex config profile: layer $CODEX_HOME/<name>.config.toml
  -c k=v      expert pass-through config override (repeatable); may override
              wrapper defaults, e.g. -c model_verbosity="low"
  --capture DIR
              record this call's evidence into DIR (empty or new); needs REVIEW_CALL_ID
  -           optional explicit stdin marker

Environment (the adapter calling convention; all optional):
  REVIEW_RECEIPT_DIR   directory to write one ReviewReceipt/v1 into
  REVIEW_METHOD_ID     the review method this dispatch serves
  REVIEW_ORDERING_SEED, REVIEW_SWAP_GROUP
                       the orchestrator's panel controls, copied into the receipt
  REVIEW_CAPTURE_DIR   as --capture DIR
  REVIEW_CALL_ID       the call a capture belongs to (DISTILL_CALL_ID is read when unset)
  REVIEW_CONTEXT_MANIFEST
                       the call's declared context manifest (JSON), hashed into the receipt
  CODEX_RUN_BIN        the codex executable a capture runs (default: codex on PATH, links
                       resolved to the versioned file)
  CODEX_RUN_VERSION    the codex-cli version a capture is pinned to; required, checked first
  RUST_LOG             the trace channels a capture reads; passed to codex unchanged
USAGE
}

profile=inherit
home=""
model=""
effort=""
sandbox="read-only"
bypass_sandbox=0
multi_agent=""
cd_dir=""
schema=""
codex_profile=""
extra_c=()
capture_dir="${REVIEW_CAPTURE_DIR:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --profile) profile="${2:?--profile needs a value}"; shift 2 ;;
    --home)    home="${2:?--home needs a value}"; shift 2 ;;
    --model)   model="${2:?--model needs a value}"; shift 2 ;;
    --effort)  effort="${2:?--effort needs a value}"; shift 2 ;;
    --sandbox) sandbox="${2:?--sandbox needs a value}"; shift 2 ;;
    --bypass-sandbox|--dangerously-bypass-approvals-and-sandbox) bypass_sandbox=1; shift ;;
    --multi-agent) multi_agent="${2:?--multi-agent needs auto|on|off}"; shift 2 ;;
    --cd)      cd_dir="${2:?--cd needs a value}"; shift 2 ;;
    --schema)  schema="${2:?--schema needs a value}"; shift 2 ;;
    --codex-profile|-p) codex_profile="${2:?--codex-profile needs a value}"; shift 2 ;;
    -c)        extra_c+=("${2:?-c needs a value}"); shift 2 ;;
    --capture) capture_dir="${2:?--capture needs a value}"; shift 2 ;;
    -)         shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "codex-run: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$profile" in
  inherit|hermetic|custom) ;;
  *) echo "codex-run: --profile must be inherit|hermetic|custom" >&2; exit 2 ;;
esac
case "$multi_agent" in
  ""|auto|on|off) ;;
  *) echo "codex-run: --multi-agent must be auto|on|off" >&2; exit 2 ;;
esac

config_key_from_override() {
  kv="$1"
  case "$kv" in
    *=*) key="${kv%%=*}" ;;
    *) echo "codex-run: -c must be key=value: $kv" >&2; exit 2 ;;
  esac
  case "$key" in
    ''|*[!A-Za-z0-9_.-]*) echo "codex-run: invalid -c key: $key" >&2; exit 2 ;;
  esac
  printf '%s\n' "$key"
}

if [ "${#extra_c[@]}" -gt 0 ]; then
  for kv in "${extra_c[@]}"; do
    config_key_from_override "$kv" >/dev/null
  done
fi

real_home="${CODEX_HOME:-$HOME/.codex}"
run_home="$real_home"
child_home="$HOME"
run_env=()
cleanup_paths=()
cleanup_all() {
  if [ "${#cleanup_paths[@]}" -gt 0 ]; then
    for p in "${cleanup_paths[@]}"; do rm -rf "$p"; done
  fi
}
trap cleanup_all EXIT

if [ "$profile" = "hermetic" ]; then
  root="$(mktemp -d "${TMPDIR:-/tmp}/codex-run-XXXXXX")"
  cleanup_paths+=("$root")
  run_home="$root/home"
  mkdir -p "$run_home"
  # Auth still resolves from CODEX_HOME even with --ignore-user-config, so carry
  # only auth.json across; leave AGENTS.md and config.toml behind.
  cp "$real_home/auth.json" "$run_home/auth.json" 2>/dev/null || true
  # Codex also reads user skills from HOME, so the child gets an empty one. Only the
  # child: receipts below still resolve the launcher from the caller's HOME.
  mkdir -p "$root/user-home"
  child_home="$root/user-home"
  run_env+=(HOME="$child_home")
  # Default cwd to an empty workspace; project_doc_max_bytes=0 (added below) keeps a
  # caller's --cd inside a repository from loading its AGENTS.md files.
  if [ -z "$cd_dir" ]; then
    cd_dir="$root/workspace"
    mkdir -p "$cd_dir"
  fi
elif [ "$profile" = "custom" ]; then
  if [ -z "$home" ]; then echo "codex-run: --profile custom requires --home DIR" >&2; exit 2; fi
  if [ ! -d "$home" ]; then echo "codex-run: --home not a directory: $home" >&2; exit 2; fi
  run_home="$home"
fi

args=(exec --skip-git-repo-check)
if [ "$bypass_sandbox" -eq 1 ]; then
  args+=(--dangerously-bypass-approvals-and-sandbox)
else
  args+=(--sandbox "$sandbox")
fi
# The profile's flag set, one list: what codex receives and what a capture hashes.
profile_flags=()
if [ "$profile" = "hermetic" ]; then profile_flags=(--ignore-user-config --ephemeral -c project_doc_max_bytes=0); fi
if [ "${#profile_flags[@]}" -gt 0 ]; then args+=("${profile_flags[@]}"); fi
if [ -n "$model" ];  then args+=(--model "$model"); fi
if [ -n "$cd_dir" ]; then args+=(--cd "$cd_dir"); fi
if [ -n "$schema" ]; then args+=(--output-schema "$schema"); fi
if [ -n "$codex_profile" ]; then args+=(--profile "$codex_profile"); fi
if [ -n "$effort" ]; then args+=(-c "model_reasoning_effort=\"$effort\""); fi
if [ -n "$multi_agent" ]; then
  if [ "$multi_agent" = "auto" ]; then
    [ "$effort" = "ultra" ] && multi_agent_value=true || multi_agent_value=false
  else
    [ "$multi_agent" = "on" ] && multi_agent_value=true || multi_agent_value=false
  fi
  args+=(-c "features.multi_agent=$multi_agent_value")
fi
if [ "${#extra_c[@]}" -gt 0 ]; then
  for kv in "${extra_c[@]}"; do args+=(-c "$kv"); done
fi

# Dispatch audit: verifier diversity is only as real as the pinned backing
# model — an unpinned dispatch inherits config defaults and can silently
# collapse two "different" reviewers onto one backend. The audit line goes to
# the log file only; stdout/stderr stay reserved for the codex channels.
sandbox_label="$sandbox"
if [ "$bypass_sandbox" -eq 1 ]; then sandbox_label="bypass"; fi
cmodel=""
ceffort=""
if [ "${#extra_c[@]}" -gt 0 ]; then
  for kv in "${extra_c[@]}"; do
    case "$kv" in
      model=*) cmodel="${kv#model=}" ;;
      # An expert -c may override the effort too, and the seat a receipt reports has to
      # be the one actually SENT — reading only --effort would report the requested seat
      # while the dispatch ran on another, which is the drift the receipt exists to catch.
      model_reasoning_effort=*)
        ceffort="${kv#model_reasoning_effort=}"
        ceffort="${ceffort%\"}"; ceffort="${ceffort#\"}" ;;
    esac
  done
fi
dispatch_note="dispatch profile=$profile model=${model:-INHERITED_DEFAULT}${cmodel:+ c-model-override=$cmodel} effort=${effort:-config-default} sandbox=$sandbox_label"
if [ -z "$model" ] && [ -z "$cmodel" ]; then
  echo "codex-run: WARNING: no --model pin; the backing model inherits the active config default" >&2
fi
mkdir -p "$real_home/log" 2>/dev/null || true
printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$dispatch_note" >> "$real_home/log/codex-run-dispatch.log" 2>/dev/null || true

emit_receipt() {
  # Recording never breaks dispatch: every failure here is a warning and codex's own
  # exit status is what this script returns. A missing receipt adjudicates to UNKNOWN,
  # which is the honest outcome — silence is not evidence of failure.
  status="$1"; packet="$2"; result="$3"; shift 3
  launcher="${AGENT_LAUNCH_BIN:-$HOME/.local/bin/agent-launch}"
  if [ ! -x "$launcher" ]; then
    launcher="$(command -v agent-launch 2>/dev/null || true)"
  fi
  if [ -z "$launcher" ]; then
    echo "codex-run: WARNING: agent-launch not found; no receipt emitted" >&2
    return 0
  fi
  # The seat as SENT: an expert -c override beats the flag it overrode, and an
  # unpinned dispatch names no seat at all, so the receipt is refused rather than
  # invented — which is the same failure the warning above already reports.
  "$launcher" --emit-receipt "${REVIEW_METHOD_ID:-}" \
    "openai:${cmodel:-$model}/${ceffort:-$effort}" "$status" "$packet" "$result" "$@" >/dev/null \
    || echo "codex-run: WARNING: receipt not emitted" >&2
}

if [ -n "$capture_dir" ]; then
  # The helper travels with the adapter (the release and the compatibility bin both put it
  # beside this file); resolving it anywhere else would let a checkout stand in for a release.
  self="${BASH_SOURCE[0]}"
  while [ -L "$self" ]; do
    link="$(readlink "$self")"
    case "$link" in /*) self="$link" ;; *) self="$(dirname "$self")/$link" ;; esac
  done
  helper="$(cd "$(dirname "$self")" && pwd)/codex_frame_filter.py"
  if [ ! -f "$helper" ]; then
    echo "codex-run: capture helper missing beside the adapter: $helper" >&2; exit 3
  fi
  # A named Codex configuration profile layers settings and instructions the rendering below
  # cannot reproduce, so a capture refuses one rather than record evidence of another call.
  named_profile="$codex_profile"
  if [ "${#extra_c[@]}" -gt 0 ]; then
    for kv in "${extra_c[@]}"; do
      case "$kv" in profile=*) named_profile="${kv#profile=}" ;; esac
    done
  fi
  if [ -n "$named_profile" ]; then
    echo "codex-run: CODEX_PROFILE_UNSUPPORTED capture cannot render Codex profile '$named_profile'; drop -p/--codex-profile or -c profile=" >&2
    exit 2
  fi
  call_id="${REVIEW_CALL_ID:-${DISTILL_CALL_ID:-}}"
  if [ -z "$call_id" ]; then
    echo "codex-run: capture needs REVIEW_CALL_ID, the call this capture belongs to" >&2; exit 2
  fi
  mkdir -p "$capture_dir"
  if [ -n "$(ls -A "$capture_dir")" ]; then
    echo "codex-run: capture directory is not empty (one capture per call): $capture_dir" >&2; exit 2
  fi
  case ",${RUST_LOG:-}," in
    *,tungstenite::protocol=trace,*) ;;
    *) echo "codex-run: WARNING: RUST_LOG does not open tungstenite::protocol=trace; no frame will name the model that answered" >&2 ;;
  esac
  # One executable for the rendering, the host record, the version check and the call: the
  # versioned file the caller pins (CODEX_RUN_BIN, else codex on PATH with its links resolved),
  # at the version the caller pins (CODEX_RUN_VERSION), checked before anything is sent.
  codex_bin="${CODEX_RUN_BIN:-$(command -v codex 2>/dev/null || true)}"
  if [ -z "$codex_bin" ] || [ ! -x "$codex_bin" ]; then
    echo "codex-run: capture needs a codex executable: set CODEX_RUN_BIN or put codex on PATH" >&2; exit 2
  fi
  while [ -L "$codex_bin" ]; do
    link="$(readlink "$codex_bin")"
    case "$link" in /*) codex_bin="$link" ;; *) codex_bin="$(dirname "$codex_bin")/$link" ;; esac
  done
  codex_bin="$(cd -P "$(dirname "$codex_bin")" && pwd)/$(basename "$codex_bin")"
  if [ -z "${CODEX_RUN_VERSION:-}" ]; then
    echo "codex-run: capture needs CODEX_RUN_VERSION, the codex-cli version the call is pinned to" >&2; exit 2
  fi
  codex_version="$(env CODEX_HOME="$run_home" HOME="$child_home" DISABLE_AUTOUPDATER=1 "$codex_bin" --version 2>/dev/null || true)"
  if [ "$codex_version" != "codex-cli $CODEX_RUN_VERSION" ]; then
    echo "codex-run: HOST_VERSION_MISMATCH $codex_bin reports '$codex_version', the call is pinned to codex-cli $CODEX_RUN_VERSION" >&2
    exit 3
  fi
  [ -n "$cd_dir" ] || cd_dir="$PWD"
  work="$(mktemp -d "${TMPDIR:-/tmp}/codex-run-capture-XXXXXX")"
  cleanup_paths+=("$work")
  cat > "$work/packet"
  # The rendering sees what the call will: the same homes and working directory, every -c
  # the call passes, and the model, approval and sandbox exec sets from its own flags.
  render_c=(-c 'approval_policy="never"')
  if [ "$bypass_sandbox" -eq 1 ]; then render_c+=(-c 'sandbox_mode="danger-full-access"')
  else render_c+=(-c "sandbox_mode=\"$sandbox\""); fi
  if [ -n "$model" ]; then render_c+=(-c "model=\"$model\""); fi
  prev=""
  for a in "${args[@]}"; do
    if [ "$prev" = "-c" ]; then render_c+=(-c "$a"); fi
    prev="$a"
  done
  env ${run_env[@]+"${run_env[@]}"} DISABLE_AUTOUPDATER=1 python3 "$helper" context --codex "$codex_bin" \
    --version "$CODEX_RUN_VERSION" --codex-home "$run_home" --child-home "$child_home" \
    --cwd "$cd_dir" --capture "$capture_dir" --work "$work" "${render_c[@]}" \
    || { echo "codex-run: effective-context evidence failed; refusing to dispatch" >&2; exit 3; }
  t0="$(python3 -c 'import time; print(int(time.time() * 1000))')"
  set +e
  # codex's stdout (the --json events) goes to fd 9, its stderr through the filter, which
  # passes every line on to this script's stderr and keeps the reduced records.
  exec 9> "$work/events.raw"
  env ${run_env[@]+"${run_env[@]}"} CODEX_HOME="$run_home" DISABLE_AUTOUPDATER=1 "$codex_bin" "${args[@]}" --json -o "$work/result" \
    < "$work/packet" 2>&1 >&9 9>&- \
    | python3 "$helper" filter --frames "$capture_dir/frames.jsonl" --rust-log "${RUST_LOG:-}" 9>&-
  status=${PIPESTATUS[0]}
  exec 9>&-
  set -e
  t1="$(python3 -c 'import time; print(int(time.time() * 1000))')"
  python3 "$helper" events --out "$capture_dir/events.jsonl" < "$work/events.raw" \
    || echo "codex-run: WARNING: events not captured" >&2
  # the bytes delivered on stdout are the final message and one newline, as without capture
  if [ -s "$work/result" ]; then { cat "$work/result"; printf '\n'; } > "$work/stdout"; else : > "$work/stdout"; fi
  flag_args=()
  if [ "${#profile_flags[@]}" -gt 0 ]; then
    for f in "${profile_flags[@]}"; do flag_args+=("--flag=$f"); done
  fi
  evidence=()
  while IFS= read -r line; do evidence+=(--evidence "$line"); done < <(
    python3 "$helper" finish --capture "$capture_dir" --work "$work" --call-id "$call_id" --profile "$profile" \
      --cwd "$cd_dir" --packet "$work/packet" --model "${cmodel:-$model}" --effort "${ceffort:-$effort}" \
      --exit-status "$status" --wall-ms "$((t1 - t0))" ${schema:+--schema "$schema"} \
      ${REVIEW_CONTEXT_MANIFEST:+--manifest "$REVIEW_CONTEXT_MANIFEST"} ${flag_args[@]+"${flag_args[@]}"} \
      || echo "codex-run: WARNING: capture not finished" >&2)
  cat "$work/stdout"
  if [ -n "${REVIEW_RECEIPT_DIR:-}" ]; then
    emit_receipt "$status" "$work/packet" "$work/stdout" ${evidence[@]+"${evidence[@]}"}
  fi
elif [ -n "${REVIEW_RECEIPT_DIR:-}" ]; then
  # stdin is captured rather than inherited ONLY on this branch: hashing the packet
  # requires holding it, and teeing stdout requires a pipe. Both change the channel
  # shape, so neither is reached unless a receipt was actually asked for.
  work="$(mktemp -d "${TMPDIR:-/tmp}/codex-run-receipt-XXXXXX")"
  cleanup_paths+=("$work")
  cat > "$work/packet"
  set +e
  env ${run_env[@]+"${run_env[@]}"} CODEX_HOME="$run_home" codex "${args[@]}" < "$work/packet" | tee "$work/result"
  status=${PIPESTATUS[0]}
  set -e
  emit_receipt "$status" "$work/packet" "$work/result"
else
  # stdin, stdout, and stderr already match this adapter's channel contract.
  set +e
  env ${run_env[@]+"${run_env[@]}"} CODEX_HOME="$run_home" codex "${args[@]}"
  status=$?
  set -e
fi

exit "$status"
