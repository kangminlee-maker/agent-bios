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
#                       cwd defaults to an empty temp workspace → NO AGENTS.md, NO user
#                       config: an independent, uncontaminated lens
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
# Verified against codex-cli 0.144.1.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: codex-run.sh [--profile inherit|hermetic|custom] [--home DIR]
                    [--model M] [--effort E] [--sandbox MODE] [--cd DIR]
                    [--bypass-sandbox]
                    [--multi-agent auto|on|off]
                    [--schema FILE] [--codex-profile NAME] [-p NAME]
                    [-c key=value ...] [-]  < prompt
  --profile   instruction/config reach (default: inherit)
                inherit  real CODEX_HOME  -> global+project AGENTS.md + full config.toml
                hermetic temp CODEX_HOME  -> NO AGENTS.md, NO user config (auth only)
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
  -           optional explicit stdin marker

Environment (the adapter calling convention; all optional):
  REVIEW_RECEIPT_DIR   directory to write one ReviewReceipt/v1 into
  REVIEW_METHOD_ID     the review method this dispatch serves
  REVIEW_ORDERING_SEED, REVIEW_SWAP_GROUP
                       the orchestrator's panel controls, copied into the receipt
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
  # Default cwd to an empty workspace so no project AGENTS.md is picked up.
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
if [ "$profile" = "hermetic" ]; then args+=(--ignore-user-config --ephemeral); fi
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
  status="$1"; packet="$2"; result="$3"
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
    "openai:${cmodel:-$model}/${ceffort:-$effort}" "$status" "$packet" "$result" >/dev/null \
    || echo "codex-run: WARNING: receipt not emitted" >&2
}

if [ -n "${REVIEW_RECEIPT_DIR:-}" ]; then
  # stdin is captured rather than inherited ONLY on this branch: hashing the packet
  # requires holding it, and teeing stdout requires a pipe. Both change the channel
  # shape, so neither is reached unless a receipt was actually asked for.
  work="$(mktemp -d "${TMPDIR:-/tmp}/codex-run-receipt-XXXXXX")"
  cleanup_paths+=("$work")
  cat > "$work/packet"
  set +e
  CODEX_HOME="$run_home" codex "${args[@]}" < "$work/packet" | tee "$work/result"
  status=${PIPESTATUS[0]}
  set -e
  emit_receipt "$status" "$work/packet" "$work/result"
else
  # stdin, stdout, and stderr already match this adapter's channel contract.
  set +e
  CODEX_HOME="$run_home" codex "${args[@]}"
  status=$?
  set -e
fi

exit "$status"
