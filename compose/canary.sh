#!/usr/bin/env bash
# Activation canary: proves the central bundle actually LOADS in a live
# session — file presence cannot detect a declined @import approval or a
# broken entry import line, so this asks a headless session to echo the
# bundle's rev marker back.
#
# Exit: 0 loading | 1 NOT loading | 3 nothing to probe / cannot probe.
#
# The 1-vs-3 split is the point. A canary that answers "not loading" when it
# never ran a probe sends you to debug imports while the real cause is that
# there is no packaged bundle here, or that the CLI is not authenticated. Only
# a real probe that really replied may return 1.
set -u
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BUNDLE="$CLAUDE_DIR/central/bundle.md"

# Every install assembles a central bundle now — the shape that had none, where the entry file
# WAS the corpus, is gone. So a missing bundle is a real failure again rather than the N/A it
# used to be, and an entry file with no bundle beside it is a pre-convergence layout that a
# re-install fixes.
if [ ! -f "$BUNDLE" ]; then
  if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
    echo "CANARY FAIL: entry file present but no central bundle at $BUNDLE — this is the old"
    echo "             whole-file layout; re-run: agent-bios install"
    exit 1
  fi
  echo "CANARY FAIL: no corpus deployed at $CLAUDE_DIR (run: agent-bios install)"
  exit 1
fi

expected="$(grep -m1 '^agent-bios-bundle-rev: ' "$BUNDLE")"
[ -n "$expected" ] || { echo "CANARY FAIL: bundle has no rev marker (reassemble with a current assemble.py)"; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "CANARY SKIP: claude CLI not found — cannot probe activation"; exit 3; }

probe="Somewhere in your loaded instruction context there may be a line that starts with 'agent-bios-bundle-rev:'. Reply with ONLY that line, verbatim. If no such line is in your context, reply with exactly: BUNDLE-NOT-LOADED"
out="$(cd "$HOME" && claude -p "$probe" 2>/dev/null)"
probe_status=$?

if printf '%s' "$out" | grep -qF "$expected"; then
  # Record WHICH bundle was proven to load. This is the only evidence in the system that
  # distinguishes a corpus that landed from one that is read, so the irreversible act that
  # depends on that distinction — pruning a user's personal copy of a promoted learning — reads
  # this file rather than re-deriving a weaker answer from file contents. The rev is part of the
  # proof: a later reassembly invalidates it instead of inheriting it.
  STATE_DIR="${AGENT_BIOS_STATE_DIR:-$HOME/.local/share/agent-bios}"
  mkdir -p "$STATE_DIR" 2>/dev/null && printf '%s\n' "$expected" > "$STATE_DIR/activation.txt" 2>/dev/null || true
  echo "CANARY PASS: central bundle is loading ($expected)"
  exit 0
fi

# A pre-dispatch refusal produces no model output at all, so the reply carries
# nothing about activation. Attributing it to a declined import would blame the
# corpus for an auth or quota problem.
case "$out" in
  *"Not logged in"*|*"/login"*|*"Invalid API key"*|*"authentication"*|*"Authentication"*)
    echo "CANARY SKIP: claude CLI is not authenticated for this config dir — cannot probe activation"
    echo "  probe replied:   $(printf '%s' "$out" | head -c 200)"
    exit 3 ;;
  *"usage limit"*|*"rate limit"*|*"quota"*)
    echo "CANARY SKIP: provider refused the probe (limit) — cannot probe activation"
    echo "  probe replied:   $(printf '%s' "$out" | head -c 200)"
    exit 3 ;;
esac
if [ -z "$out" ]; then
  echo "CANARY SKIP: probe produced no output — cannot tell activation from a failed dispatch"
  exit 3
fi
# The 1-vs-3 rule this file opens with, applied to the one signal it was not reading:
# the probe's own exit status. An empty reply was already treated as unprobed, but a
# FAILED dispatch that printed anything at all — a network error, an unrecognised flag,
# a CLI upgrade changing its error text — fell through to FAIL and sent the reader off
# to re-approve imports for a bundle that was never asked about. stderr is discarded
# above, so the message is quoted for whatever it is worth and the status decides.
if [ "$probe_status" -ne 0 ]; then
  echo "CANARY SKIP: the probe command failed (exit $probe_status) — cannot tell activation"
  echo "             from a failed dispatch"
  echo "  probe replied:   $(printf '%s' "$out" | head -c 200)"
  exit 3
fi

echo "CANARY FAIL: central bundle is NOT loading in live sessions."
echo "  expected marker: $expected"
echo "  probe replied:   $(printf '%s' "$out" | head -c 200)"
echo "  Likely causes: the CLAUDE.md import approval was declined (open a session and re-approve imports),"
echo "  or the entry file lost its '@central/bundle.md' line. Diagnose with: agent-bios verify"
exit 1
