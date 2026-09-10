#!/usr/bin/env bash
# Provision the managed virtualenv that backs the agent-launch Textual preflight.
#
# The interactive launcher re-execs into this venv (launch/agent-launch.py ->
# maybe_reexec_into_venv). It is an enhancement, not a hard dependency: when the
# venv is missing or broken, the launcher falls back to numbered prompts, and
# every direct / non-TTY / --no-tui path keeps running under the system
# interpreter untouched. Re-run this after upgrading Python or the pin below.
#
#   AGENT_LAUNCH_VENV   override the venv location (default below)
#   AGENT_LAUNCH_PYTHON python used to create the venv (default: python3)
set -eu

TEXTUAL_PIN="textual==8.2.8"
VENV="${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}"
PYTHON="${AGENT_LAUNCH_PYTHON:-python3}"

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import textual' 2>/dev/null; then
  printf 'agent-launch venv already provisioned: %s\n' "$VENV"
  "$VENV/bin/python" -c 'import textual, sys; print("  textual", textual.__version__, "| python", sys.version.split()[0])'
  exit 0
fi

printf 'Provisioning agent-launch venv at %s ...\n' "$VENV"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet "$TEXTUAL_PIN"
"$VENV/bin/python" -c 'import textual, sys; print("Ready: textual", textual.__version__, "| python", sys.version.split()[0])'
