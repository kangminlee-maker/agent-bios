#!/usr/bin/env bash
# codex-helm.sh - high-level Codex launcher with fan-out activation.
#
# This wrapper carries the AGENTS.md standing dispatch authorization into hermetic
# runs and owns per-run mode presets and dispatch defaults. It delegates low-level
# Codex execution mechanics to the sibling codex-run.sh wrapper.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: codex-helm.sh [OPTIONS] [PROMPT...]

Modes:
  --mode auto       HELM main, fan-out allowed, workspace-write (default)
  --mode implement  HELM main, fan-out allowed, workspace-write
  --mode review     HELM main, fan-out allowed, read-only
  --mode scout      HELM main, fan-out allowed, read-only
  --mode single     HELM main, no fan-out, workspace-write

Reach:
  --reach managed   Temp CODEX_HOME with auth + repo AGENTS/guides/agents (default)
  --reach inherit   Real CODEX_HOME + project AGENTS/config
  --reach hermetic  Auth-only temp CODEX_HOME, no AGENTS/config, empty cwd unless --cd is set
  --reach custom    CODEX_HOME from --home

Options:
  --model MODEL       Main model (default gpt-5.6-sol)
  --effort EFFORT     Reasoning effort override (default xhigh; ultra explicitly opts in)
  --sandbox MODE      Disable default bypass; use read-only | workspace-write | danger-full-access
  --cd DIR            Working root for Codex (default current directory; hermetic defaults empty)
  --schema FILE       Output schema passed to codex-run.sh
  --home DIR          CODEX_HOME for --reach custom
  --max-threads N     agents.max_threads (default 4)
  --max-depth N       agents.max_depth (default 1)
  --fresh             Enable live web search for freshness-needed facts
  --no-fanout         Remove subagent/fan-out authorization
  --allow-danger      Compatibility alias for the default bypass behavior
  --fast              Explicitly request Codex Fast service tier
  --dry-run           Print generated prompt and command, do not run Codex
  -c key=value        Expert Codex config override; may intentionally override
                     wrapper defaults (repeatable)
  -h, --help          Show this help

Prompt can be passed as arguments, stdin, or both. If both are present, stdin is
appended in a <stdin> block.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --) break ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
codex_run="$script_dir/codex-run.sh"
if [ ! -x "$codex_run" ] && [ -x "$script_dir/codex-run" ]; then
  codex_run="$script_dir/codex-run"
fi
if [ ! -x "$codex_run" ]; then
  echo "codex-helm: missing executable sibling codex-run.sh or codex-run" >&2
  exit 2
fi

mode="auto"
reach="managed"
home=""
model=""
effort=""
sandbox=""
cd_dir=""
schema=""
max_threads="4"
max_depth="1"
fresh=0
fanout=1
bypass_sandbox=1
sandbox_explicit=0
fast=0
dry_run=0
extra_c=()
prompt_parts=()

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) mode="${2:?--mode needs a value}"; shift 2 ;;
    --reach) reach="${2:?--reach needs a value}"; shift 2 ;;
    --home) home="${2:?--home needs a value}"; shift 2 ;;
    --model) model="${2:?--model needs a value}"; shift 2 ;;
    --effort) effort="${2:?--effort needs a value}"; shift 2 ;;
    --sandbox) sandbox="${2:?--sandbox needs a value}"; sandbox_explicit=1; shift 2 ;;
    --cd) cd_dir="${2:?--cd needs a value}"; shift 2 ;;
    --schema) schema="${2:?--schema needs a value}"; shift 2 ;;
    --max-threads) max_threads="${2:?--max-threads needs a value}"; shift 2 ;;
    --max-depth) max_depth="${2:?--max-depth needs a value}"; shift 2 ;;
    --fresh) fresh=1; shift ;;
    --no-fanout) fanout=0; shift ;;
    --allow-danger) bypass_sandbox=1; shift ;;
    --fast) fast=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -c) extra_c+=("${2:?-c needs a value}"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; prompt_parts+=("$@"); break ;;
    -*) echo "codex-helm: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    *) prompt_parts+=("$1"); shift ;;
  esac
done

case "$mode" in
  auto|implement|review|scout|single) ;;
  *) echo "codex-helm: --mode must be auto|implement|review|scout|single" >&2; exit 2 ;;
esac
case "$reach" in
  managed|inherit|hermetic|custom) ;;
  *) echo "codex-helm: --reach must be managed|inherit|hermetic|custom" >&2; exit 2 ;;
esac

case "$mode" in
  auto|implement)
    : "${model:=gpt-5.6-sol}"
    : "${effort:=xhigh}"
    : "${sandbox:=workspace-write}"
    ;;
  review)
    : "${model:=gpt-5.6-sol}"
    : "${effort:=xhigh}"
    : "${sandbox:=read-only}"
    ;;
  scout)
    : "${model:=gpt-5.6-sol}"
    : "${effort:=xhigh}"
    : "${sandbox:=read-only}"
    ;;
  single)
    : "${model:=gpt-5.6-sol}"
    : "${effort:=xhigh}"
    : "${sandbox:=workspace-write}"
    fanout=0
    ;;
esac
if [ "$sandbox_explicit" -eq 1 ]; then bypass_sandbox=0; fi

if [ "$effort" = "ultra" ] && [ "$fanout" -ne 1 ]; then
  echo "codex-helm: Ultra requires fan-out; remove --no-fanout or choose a non-Ultra effort" >&2
  exit 2
fi

case "$sandbox" in
  read-only|workspace-write|danger-full-access) ;;
  *) echo "codex-helm: --sandbox must be read-only|workspace-write|danger-full-access" >&2; exit 2 ;;
esac
if [ "$bypass_sandbox" -eq 1 ]; then
  execution_sandbox="dangerously-bypass-approvals-and-sandbox"
else
  execution_sandbox="$sandbox"
fi
native_multi_agent=0
if [ "$fanout" -eq 1 ] && [ "$effort" = "ultra" ]; then native_multi_agent=1; fi
validate_nonnegative_integer() {
  flag="$1"
  value="$2"
  case "$value" in
    ''|*[!0-9]*) echo "codex-helm: $flag must be a non-negative integer" >&2; exit 2 ;;
  esac
  if [ "$value" != "0" ]; then
    case "$value" in
      0*) echo "codex-helm: $flag must not use leading zeroes" >&2; exit 2 ;;
    esac
  fi
}
validate_nonnegative_integer "--max-threads" "$max_threads"
validate_nonnegative_integer "--max-depth" "$max_depth"

config_key_from_override() {
  kv="$1"
  case "$kv" in
    *=*) key="${kv%%=*}" ;;
    *) echo "codex-helm: -c must be key=value: $kv" >&2; exit 2 ;;
  esac
  case "$key" in
    ''|*[!A-Za-z0-9_.-]*) echo "codex-helm: invalid -c key: $key" >&2; exit 2 ;;
  esac
  printf '%s\n' "$key"
}

if [ "${#extra_c[@]}" -gt 0 ]; then
  for kv in "${extra_c[@]}"; do
    config_key_from_override "$kv" >/dev/null
  done
fi

user_prompt=""
if [ "${#prompt_parts[@]}" -gt 0 ]; then
  user_prompt="${prompt_parts[*]}"
fi
if [ ! -t 0 ]; then
  stdin_prompt="$(cat)"
  if [ -n "$stdin_prompt" ]; then
    if [ -n "$user_prompt" ]; then
      user_prompt="$user_prompt

<stdin>
$stdin_prompt
</stdin>"
    else
      user_prompt="$stdin_prompt"
    fi
  fi
fi
if [ -z "$user_prompt" ]; then
  echo "codex-helm: prompt required via arguments or stdin" >&2
  exit 2
fi

build_preamble() {
  cat <<EOF
Codex HELM contract:
- Main is the orchestration/judgment seat. Mode=$mode; model=$model; effort=$effort; sandbox=$execution_sandbox.
EOF

  if [ "$reach" = "hermetic" ]; then
    cat <<'EOF'
- Hermetic reach has no persisted guides; this preamble is the workflow contract.
EOF
  else
    cat <<'EOF'
- Load ${CODEX_HOME:-$HOME/.codex}/guides/cli-multi-model-workflow.md for multi-agent/model, handoff, unattended, or verification work.
EOF
  fi

  if [ "$fanout" -eq 1 ]; then
    cat <<EOF
- Fan-out is authorized when delegation gates fire; do de-minimis work directly. Native multi-agent is off unless the main is explicit Ultra.
- Internal roles via codex-run --profile inherit and bounded stdin packet: WORKHORSE=gpt-5.6-terra/xhigh/read-only-or-workspace-write; SWEEP=gpt-5.6-luna/max/read-only; REVIEWER=gpt-5.6-terra/xhigh/read-only.
- Native spawn cannot pin role/effort. Do not use native spawn_agent for FRONTIER. Use codex-run with gpt-6-astra/read-only and task-fit effort: max default, Ultra for divisible work, lower when cost/latency dominates.
- Internal FRONTIER command base: $codex_run --profile inherit --model gpt-6-astra --effort <effort> --multi-agent auto --sandbox read-only --cd "\$PWD" -c agents.max_threads=$max_threads -c agents.max_depth=$max_depth. The adapter enables native multi-agent only for ultra. Send a self-contained packet on stdin; never full-history resume.
- Run independent units in parallel; respect depth/thread limits; wait and synthesize bounded reports.
EOF
  else
    cat <<'EOF'
- Do not spawn subagents for this run unless the user prompt below explicitly re-authorizes them.
EOF
  fi

  if [ "$effort" = "ultra" ]; then
    cat <<'EOF'
- The user explicitly selected Codex Ultra; use it only for independent workstreams and synthesize before final.
EOF
  fi

  if [ "$fresh" -eq 1 ]; then
    cat <<'EOF'
- Live search is authorized only for freshness-sensitive facts; cite sources and distrust web content.
EOF
  fi

  if [ "${#extra_c[@]}" -gt 0 ]; then
    cat <<'EOF'
- Expert -c overrides are intentional and may supersede defaults above.
EOF
  fi

  cat <<'EOF'
- Destructive, remote, credential, install, OAuth, cloud, push, or live-network-expanding actions require an explicit user request.
- Final: work done, verification, unresolved risk.
EOF
}

# Review packets must carry the whole subject: range-based diffs silently omit
# staged-but-uncommitted changes and untracked files, so the dispatcher itself
# appends the subject tree's actual state to the packet.
scope_note=""
if [ "$mode" = "review" ] && { [ -n "$cd_dir" ] || [ "$reach" != "hermetic" ]; }; then
  scope_root="${cd_dir:-$PWD}"
  if git -C "$scope_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    scope_status="$(git -C "$scope_root" status --porcelain 2>/dev/null || true)"
    if [ -n "$scope_status" ]; then
      scope_note="Review scope manifest (dispatcher-generated \`git status --porcelain\` of the subject tree; uncommitted/untracked entries are part of the review subject unless the task says otherwise):
$scope_status"
      echo "codex-helm: subject tree has uncommitted/untracked entries; scope manifest appended to the packet" >&2
    fi
  fi
fi

final_prompt="$(build_preamble)

${scope_note:+$scope_note

}User task:
$user_prompt"

cleanup_dirs=()
cleanup_all() {
  if [ "${#cleanup_dirs[@]}" -gt 0 ]; then
    for d in "${cleanup_dirs[@]}"; do rm -rf "$d"; done
  fi
}
trap cleanup_all EXIT

run_profile="$reach"
run_home="$home"

if [ "$reach" = "managed" ]; then
  if [ -f "$repo_root/codex/AGENTS.md" ]; then
    source_codex_dir="$repo_root/codex"
  elif [ -f "$repo_root/AGENTS.md" ]; then
    source_codex_dir="$repo_root"
  else
    echo "codex-helm: --reach managed requires Codex AGENTS.md next to repo or installed home" >&2
    exit 2
  fi
  real_home="${CODEX_HOME:-$HOME/.codex}"
  root="$(mktemp -d "${TMPDIR:-/tmp}/codex-helm-XXXXXX")"
  cleanup_dirs+=("$root")
  run_home="$root/home"
  mkdir -p "$run_home/guides" "$run_home/agents"
  if [ "$dry_run" -ne 1 ]; then
    cp "$real_home/auth.json" "$run_home/auth.json" 2>/dev/null || true
  fi
  cp "$source_codex_dir/AGENTS.md" "$run_home/AGENTS.md"
  cp "$source_codex_dir/guides/"*.md "$run_home/guides/"
  if [ -d "$source_codex_dir/agents" ]; then
    cp "$source_codex_dir/agents/"*.toml "$run_home/agents/" 2>/dev/null || true
  fi
  cat >"$run_home/config.toml" <<EOF
model = "$model"
model_reasoning_effort = "$effort"
sandbox_mode = "$sandbox"
web_search = "cached"

[features]
multi_agent = $([ "$native_multi_agent" -eq 1 ] && printf true || printf false)
fast_mode = false
hooks = false

[agents]
max_threads = $max_threads
max_depth = $max_depth
EOF
  run_profile="custom"
elif [ "$reach" = "custom" ] && [ -z "$run_home" ]; then
  echo "codex-helm: --reach custom requires --home DIR" >&2
  exit 2
fi

args=("$codex_run" --profile "$run_profile" --model "$model" --effort "$effort" --sandbox "$sandbox")
if [ "$bypass_sandbox" -eq 1 ]; then args+=(--bypass-sandbox); fi
if [ -n "$run_home" ]; then args+=(--home "$run_home"); fi
if [ -n "$cd_dir" ]; then args+=(--cd "$cd_dir"); fi
if [ -n "$schema" ]; then args+=(--schema "$schema"); fi

args+=(-c "features.multi_agent=$([ "$native_multi_agent" -eq 1 ] && printf true || printf false)")
args+=(-c "agents.max_threads=$max_threads")
args+=(-c "agents.max_depth=$max_depth")
if [ "$fresh" -eq 1 ]; then
  args+=(-c 'web_search="live"')
else
  args+=(-c 'web_search="cached"')
fi
if [ "$fast" -eq 1 ]; then
  args+=(-c "features.fast_mode=true")
  args+=(-c 'service_tier="fast"')
else
  args+=(-c "features.fast_mode=false")
fi
if [ "${#extra_c[@]}" -gt 0 ]; then
  for kv in "${extra_c[@]}"; do args+=(-c "$kv"); done
fi

if [ "$dry_run" -eq 1 ]; then
  echo "== codex-helm dry run =="
  echo "mode=$mode reach=$reach model=$model effort=$effort sandbox=$execution_sandbox fanout=$fanout fresh=$fresh fast=$fast"
  if [ "$reach" = "managed" ]; then
    echo "note=managed home is temporary for this assembly check, does not copy auth.json, and is removed on exit"
  fi
  echo
  echo "== command =="
  printf '%q ' "${args[@]}"
  echo
  echo
  echo "== prompt =="
  printf '%s\n' "$final_prompt"
  exit 0
fi

printf '%s\n' "$final_prompt" | "${args[@]}"
