#!/usr/bin/env bash
# Provision selected dependencies in the managed agent-bios virtualenv.
# No argument installs Textual for terminal interfaces. --learning-only installs
# the JSON Schema validator used by learn. Existing other packages are preserved.
#
#   AGENT_LAUNCH_VENV   override the venv location (default below)
#   AGENT_LAUNCH_PYTHON python used to create the venv (default: python3)
set -eu

TEXTUAL_PIN="textual==8.2.8"
JSONSCHEMA_PIN="jsonschema==4.26.0"
VENV="${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}"
PYTHON="${AGENT_LAUNCH_PYTHON:-python3}"
PACKAGES=("$TEXTUAL_PIN")
case "${1:-}" in
  "") [ "$#" -eq 0 ] || { printf 'usage: provision-venv.sh [--learning-only]\n' >&2; exit 2; } ;;
  --learning-only) [ "$#" -eq 1 ] || { printf 'usage: provision-venv.sh [--learning-only]\n' >&2; exit 2; }; PACKAGES=("$JSONSCHEMA_PIN") ;;
  *) printf 'usage: provision-venv.sh [--learning-only]\n' >&2; exit 2 ;;
esac

runtime_python_ready() {
  "$1" -c 'import sys; sys.exit("agent-bios requires Python 3.11+; select it with AGENT_LAUNCH_PYTHON and use a new AGENT_LAUNCH_VENV path for an incompatible existing environment" if sys.version_info < (3, 11) else 0)'
}

pinned_ready() {
  "$VENV/bin/python" - "${PACKAGES[@]}" <<'PY'
import importlib
import importlib.metadata
import sys
for spec in sys.argv[1:]:
    name, expected = spec.split("==", 1)
    importlib.import_module(name)
    if name == "jsonschema":
        from jsonschema import Draft202012Validator
    actual = importlib.metadata.version(name)
    if actual != expected:
        raise SystemExit(f"{name}: expected {expected}, found {actual}")
    print(f"  {name} {actual} | python {sys.version.split()[0]}")
PY
}

if [ -x "$VENV/bin/python" ]; then
  runtime_python_ready "$VENV/bin/python"
else
  runtime_python_ready "$PYTHON"
fi

if [ -x "$VENV/bin/python" ] && pinned_ready >/dev/null 2>&1; then
  printf 'agent-launch venv already provisioned: %s\n' "$VENV"
  pinned_ready
  exit 0
fi

printf 'Provisioning agent-launch venv at %s ...\n' "$VENV"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --force-reinstall "${PACKAGES[@]}"
pinned_ready
