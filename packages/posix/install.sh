#!/usr/bin/env bash
# agent-bios installation bootstrap for macOS and Linux.
#
# It installs the current published npm release and stops. npm resolves the
# version and checks the tarball's integrity, so nothing is pinned here: a pin
# would have to be re-promoted on this site after every publish, and a forgotten
# promotion serves an old version silently. The installed version is printed
# instead, which is what a stale registry packument would show.
#
# It does not edit shell profiles, install a package manager, or deploy the work
# environment: deployment is `agent-bios install`, which opens an interactive
# chooser this bootstrap has no terminal for -- `curl | bash` gives the shell a
# pipe, not a tty.
set -eu

fail() { printf 'agent-bios: %s\n' "$1" >&2; exit 1; }
note() { printf 'agent-bios: %s\n' "$1"; }

case "$(uname -s)" in
  Darwin | Linux) ;;
  *) fail "this bootstrap installs on macOS and Linux. Windows has its own PowerShell command." ;;
esac

command -v npm >/dev/null 2>&1 ||
  fail "npm is required and was not found. Install Node.js 18 or newer (https://nodejs.org, or 'brew install node' on macOS), then run this command again."
command -v python3 >/dev/null 2>&1 ||
  fail "python3 3.11 or newer is required and was not found."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null ||
  fail "python3 3.11 or newer is required; found $(python3 --version 2>&1). Install a newer python3 and run this command again."

note "installing the current published release"
npm install --global agent-bios@latest

# npm exits 0 after writing a command the caller's PATH may not carry. Saying so
# here is the difference between a working installation and one that looks broken.
if ! command -v agent-bios >/dev/null 2>&1; then
  fail "agent-bios was installed, but 'agent-bios' is not on PATH. Add npm's global bin directory ($(npm prefix --global 2>/dev/null || echo '<npm prefix>')/bin) to PATH, then run: agent-bios install"
fi

# agent-bios has no --version command, and calling one printed its whole help text
# here. Read the version npm just installed instead.
version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' \
  "$(npm root --global 2>/dev/null)/agent-bios/package.json" 2>/dev/null)" || version=""
note "installed agent-bios ${version:-(its version was not reported)}"
note "next, deploy the work environment in a terminal:  agent-bios install"
