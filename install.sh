#!/usr/bin/env bash
# agent-bios installer.
#
# Deploys the single-source-of-truth (globals, scoped guides, Codex agent
# templates, Codex wrappers, the launch profile/shell/bin, a managed Textual
# venv, and the zsh hook) into $HOME by COPY — idempotent, backed up before
# overwrite, and reversible. Distributed as an npm bin; the actual $HOME
# deployment is this explicit command (never a postinstall side effect).
#
# Usage:
#   agent-bios install     deploy into this environment (backs up + verifies)
#   agent-bios verify      check the deployed state matches the source
#   agent-bios status      show what is installed and where
#   agent-bios cost        the session cost / context meter, from any directory
#   agent-bios update      git pull + reinstall (clone), or print the npm update line
#   agent-bios update --check   cache the registry's latest version for the TUI badge
#   agent-bios uninstall   remove deployed files and the zsh hook
#   agent-bios help
#
# Flags: --dry-run (print actions, change nothing).
# Env overrides: CLAUDE_CONFIG_DIR, CODEX_HOME, AGENT_LAUNCH_VENV, ZDOTDIR.
set -euo pipefail

# This installer is non-interactive: every input arrives as a subcommand, flag,
# or env var. Detach stdin so no child (the codex-helm dry-run, pip, git) can
# block forever on an inherited idle stdin — that is what hangs an install under
# CI, pipes, and background runs, where stdin stays open but never delivers.
# `learn` is the one subcommand whose payload IS stdin, so keep the caller's on
# fd 3 first and hand it back only there; every other path still sees /dev/null.
# The braces matter. `exec` with redirections and no command applies them to the
# SHELL, permanently — so the bare `exec 3<&0 2>/dev/null` this used to be sent
# every later error message on this script's stderr to /dev/null: bash's own
# set -e diagnostics, python tracebacks from deployed steps, and any `>&2` an
# author writes. Only stdout survived, which is why a failing install could stop
# with no reason on screen. The group scopes the suppression to the one command
# whose error is expected when a caller closed fd 0.
{ exec 3<&0; } 2>/dev/null || exec 3</dev/null   # tolerate a caller that closed fd 0
exec </dev/null

# Resolve this script through symlinks before locating the package: npm links the
# bin into node_modules/.bin and the global bin dir, so $0 is a link and its
# dirname is the link's directory, not the package. Without this the source tree
# resolves to the bin dir's parent (e.g. /opt/homebrew) and every deploy fails.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  LINKDIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  case "$SOURCE" in
    /*) ;;
    *) SOURCE="$LINKDIR/$SOURCE" ;;
  esac
done
SELF="$(cd -P "$(dirname "$SOURCE")" && pwd)"
REPO="$SELF"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
LAUNCH_DIR="$HOME/.config/agent-launch"
USER_PRESETS_NAME="presets.local.toml"  # user-owned; never deployed or verified
BIN_DIR="$HOME/.local/bin"
STATE_DIR="$HOME/.local/share/agent-bios"
LEGACY_STATE_DIR="$HOME/.local/share/agent-dotfiles"  # pre-rename state; migrated on first run
MANIFEST="$STATE_DIR/manifest.txt"
# The manifest is truncated at the start of every install, so what the PREVIOUS one deployed
# must be preserved before that happens. It is the only record that a file now on disk was
# written by us rather than authored by the user, and seed_entry needs exactly that to tell a
# previous release's deployed entry from someone's own CLAUDE.md.
PRIOR_MANIFEST="$STATE_DIR/manifest.prev.txt"
ZSHRC="${ZDOTDIR:-$HOME}/.zshrc"
ZSH_HOOK='[ -r "$HOME/.config/agent-launch/shell.zsh" ] && source "$HOME/.config/agent-launch/shell.zsh"'
HOOK_MARK='agent-launch/shell.zsh'
# .zshrc is the only file this installer WRITES, but it is not the only file zsh reads, and a
# user who moves the line to .zshenv (where non-interactive shells see it too) had every
# question about it answered wrongly: `status` said "zsh hook absent" while the integration was
# demonstrably running, `uninstall` said there was nothing to remove, and the next `install`
# appended a second copy to .zshrc. Detection therefore looks everywhere zsh would; ownership
# stays with .zshrc alone.
ZSH_HOOK_FILES="${ZDOTDIR:-$HOME}/.zshrc ${ZDOTDIR:-$HOME}/.zshenv ${ZDOTDIR:-$HOME}/.zprofile"

# Echo every startup file that carries the hook line, one per line, or nothing.
zsh_hook_locations() {
  local f
  for f in $ZSH_HOOK_FILES; do
    if [ -f "$f" ] && grep -qF "$HOOK_MARK" "$f"; then printf '%s\n' "$f"; fi
  done
}

DRY_RUN=0
BACKUP_DIR=""
# Set when uninstall could not undo the spans the assembler merged into files we do not own.
# Global for the same reason UNBACKED is: the closing summary must not claim a clean removal
# that did not happen.
CLEANUP_FAILED=0
# Set when the assembler reported the user-owned entry file needs a line added by hand. That
# is an outstanding ACTION, not a failed deployment: everything else really did land, and
# treating it as a failure made cmd_install exit 1 and the EXIT trap restore the previous
# manifest — leaving the new corpus on disk with the record saying the old one was deployed.
ENTRY_NEEDS_ACTION=0
# Set when the required corpus-status projection could not be written. Deferred rather than
# returned on the spot: the projection runs AFTER the corpus is deployed, and returning
# there would fire the EXIT trap and restore the PREVIOUS manifest — leaving the new corpus
# on disk with the record naming the old one, which is the split state above. The manifest
# is completed first so it describes what is really there, and the command then exits
# non-zero. The files, the record, and the exit code then each say something true.
PROJECTION_FAILED=0
# Deployed files uninstall could not back up, so did not delete. Global rather than local
# because the closing summary must not claim a clean removal that did not happen.
UNBACKED=0

log()  { printf '%s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
run()  { if [ "$DRY_RUN" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else "$@"; fi; }

# ---- prerequisites -------------------------------------------------------
check_prereqs() {
  local ok=0
  command -v git >/dev/null 2>&1 || { log "missing prerequisite: git"; ok=1; }
  command -v python3 >/dev/null 2>&1 || { log "missing prerequisite: python3"; ok=1; }
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null \
      || { log "python3 >= 3.11 required (tomllib)"; ok=1; }
  fi
  command -v zsh >/dev/null 2>&1 || log "note: zsh not found; the shell hook targets zsh"
  command -v codex >/dev/null 2>&1 || log "note: codex CLI not found; Codex-side steps will be skipped"
  command -v claude >/dev/null 2>&1 || log "note: claude CLI not found"
  return $ok
}

# ---- copy with backup + manifest ----------------------------------------
deploy_file() {
  local src="$1" dst="$2" mode="${3:-}"
  [ -f "$src" ] || { log "source missing: $src"; return 1; }
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
    info "unchanged  $dst"
  else
    if [ -f "$dst" ] && [ -n "$BACKUP_DIR" ]; then
      run mkdir -p "$(dirname "$BACKUP_DIR$dst")"
      run cp "$dst" "$BACKUP_DIR$dst"
    fi
    run mkdir -p "$(dirname "$dst")"
    run cp "$src" "$dst"
    if [ -n "$mode" ]; then run chmod "$mode" "$dst"; fi
    [ "$DRY_RUN" = 1 ] || info "installed  $dst"
  fi
  [ "$DRY_RUN" = 1 ] || printf '%s\n' "$dst" >> "$MANIFEST"
}

deploy_glob() {
  local srcdir="$1" pat="$2" dstdir="$3" mode="${4:-}" f
  for f in "$srcdir"/$pat; do
    [ -f "$f" ] || continue
    deploy_file "$f" "$dstdir/$(basename "$f")" "$mode"
  done
}

# A subtree, file by file, so every file lands in the manifest by its own name — the
# ownership rule the hooks fix settled on. Skills need this: a skill is a directory
# (SKILL.md plus free subdirectories) that lands in a directory the host scans and other
# tools populate, so nothing may claim it by path prefix, and uninstall removes exactly
# the names we wrote. `find -type f`, not a glob: subdirectories are the format.
deploy_tree() {
  local srcdir="$1" dstdir="$2" f rel
  [ -d "$srcdir" ] || { log "source tree missing: $srcdir"; return 1; }
  while IFS= read -r f; do
    rel="${f#"$srcdir"/}"
    deploy_file "$f" "$dstdir/$rel"
  done < <(find "$srcdir" -type f | LC_ALL=C sort)
}

# The skills we ship: every subdirectory of the repo's claude/skills/. One tree serves both
# hosts — the format is identical (SKILL.md + name/description frontmatter + free
# subdirectories) and the body names no host path — so the same files land under each
# host's skills directory. Iterated here rather than listed, so a second skill ships by
# being added to the tree. This is the SHIPPED set — what the tree carries; what a given
# machine RECEIVES is the selected set below.
shipped_skills() {
  local d
  for d in "$REPO/claude/skills"/*/; do
    [ -f "$d/SKILL.md" ] || continue
    basename "$d"
  done
}

# The selection, as the assembler receives it: an explicit --domains, else the saved
# selection.json, else every domain (what "full" means). One function so the corpus and
# the skills are always answered from the same selection — a skill decided from a
# different reading than the bundle would ship a package the bundle disagrees with.
selection_args() {   # -> SEL_ARGS
  SEL_ARGS=()
  if [ "${DOMAINS_SET:-0}" = 1 ]; then
    SEL_ARGS=(--domains "$DOMAINS_ARG")
  elif [ ! -f "$STATE_DIR/selection.json" ]; then
    SEL_ARGS=(--domains "$(all_domains_csv)")
  fi
}

# The skills this selection delivers, by name. Skills are classified in
# compose/domains.json like guides, hooks and agents, and the assembler owns the rule
# that turns a classification and a selection into a delivered set; this asks it rather
# than reading domains.json here, so there is one owner of "who gets what". Deploy,
# prune and verify all iterate THIS list; a skill the tree ships but the selection does
# not cover is treated exactly like a file a later release withdrew.
selected_skills() {
  selection_args
  python3 "$REPO/compose/assemble.py" --selected-skills --state-dir "$STATE_DIR" \
    ${SEL_ARGS[@]+"${SEL_ARGS[@]}"}
}

# Membership in the selected set, for the loops that iterate the shipped one. Refuses to
# answer before the set is resolved: an unset variable read as "nothing selected" would
# make prune remove every skill and verify demand every absence — the fail-open shape.
skill_selected() {   # $1: skill name; reads SELECTED_SKILLS
  [ -n "${SELECTED_SKILLS+x}" ] || { log "BUG: skill selection read before it was resolved"; exit 1; }
  case " $(printf '%s' "$SELECTED_SKILLS" | tr '\n' ' ') " in *" $1 "*) return 0 ;; esac
  return 1
}

# Our skill directories, and only ours: `$CLAUDE_DIR/skills` and `$CODEX_DIR/skills` are
# the hosts' shared scan directories, holding other tools' skills, and are never touched.
# Deepest first, so a skill's subdirectories go before the skill itself; rmdir throughout,
# so a directory holding anything we did not write is left, visibly.
rmdir_skill_dirs() {
  local skill="$1" sd d
  for sd in "$CLAUDE_DIR/skills/$skill" "$CODEX_DIR/skills/$skill"; do
    [ -d "$sd" ] || continue
    while IFS= read -r d; do
      rmdir "$d" 2>/dev/null && info "removed empty  $d" || true
    done < <(find "$sd" -depth -type d)
  done
}

# A skill file the PREVIOUS install wrote and this release no longer ships is ours by the
# prior manifest and would otherwise stay on disk unowned: the rebuilt manifest stops
# naming it, verify enumerates only current files, and the host keeps loading it. So the
# prior manifest is read for paths under either host's skills root that no shipped file
# maps to, and those are removed — backed up like any overwrite — before the deploy.
# Only skill paths: every other deploy target is a fixed name a later release overwrites
# in place. Only names the manifest proves we wrote.
prune_stale_skills() {
  local prior="$PRIOR_MANIFEST" f skill rel touched=""
  [ "$DRY_RUN" = 1 ] && prior="$MANIFEST"
  [ -f "$prior" ] || return 0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in
      "$CLAUDE_DIR/skills/"*) rel="${f#"$CLAUDE_DIR/skills/"}" ;;
      "$CODEX_DIR/skills/"*)  rel="${f#"$CODEX_DIR/skills/"}" ;;
      *) continue ;;
    esac
    skill="${rel%%/*}"; rel="${rel#*/}"
    # Still shipped AND still selected: only that combination keeps a prior file. A
    # deselected skill's files are stale exactly like a withdrawn release's — the host
    # would go on loading them for a package the user no longer takes.
    [ -f "$REPO/claude/skills/$skill/$rel" ] && skill_selected "$skill" && continue
    [ -f "$f" ] || continue
    if [ -n "$BACKUP_DIR" ] && [ "$DRY_RUN" != 1 ]; then
      mkdir -p "$(dirname "$BACKUP_DIR$f")" && cp "$f" "$BACKUP_DIR$f"
    fi
    run rm -f "$f"; [ "$DRY_RUN" = 1 ] || info "removed stale skill file  $f"
    case " $touched " in *" $skill "*) ;; *) touched="$touched $skill" ;; esac
  done < "$prior"
  for skill in $touched; do rmdir_skill_dirs "$skill"; done
}

# Backups are made on every install and every uninstall, and nothing used to remove them — 23
# directories in two weeks on the first machine measured, plus loose `.bak-*` files sitting in
# the user's own config dirs. Pruning runs AFTER the new copy exists, never before, so a failed
# run cannot leave the user with neither the change nor its backup.
prune_backups() {
  [ -f "$REPO/compose/prune-backups.py" ] || return 0
  python3 "$REPO/compose/prune-backups.py" --state-dir "$STATE_DIR" \
    --claude-dir "$CLAUDE_DIR" --codex-dir "$CODEX_DIR" \
    $([ "$DRY_RUN" = 1 ] && echo --dry-run) || log "note: backup pruning skipped"
}

# Guides whose frontmatter declares `audience: author`. They document steps only
# the corpus author can perform and name paths that exist in a checkout and
# nowhere else, so they are never installed. compose/assemble.py owns the
# declaration and withholds them from the destinations it writes; this asks it
# rather than keeping a second parser. Both callers below need that same answer
# for ground the assembler never writes — the sweep of the pre-unification
# $CLAUDE_DIR/guides, and verify's check that the absence holds in all three
# directories. Absence of the assembler degrades to withholding nothing.
# Fails LOUD, never open. An empty answer here means "withhold nothing", so
# swallowing an unreadable declaration would deploy exactly the guides this rule
# exists to hold back — the fail-open shape of every other degrade-on-absence
# fallback in this file, but inverted. compose/assemble.py ships, so its absence
# is a broken payload rather than a configuration a user might have.
author_only_guides() {
  local out
  if ! out=$(python3 - "$REPO" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / "compose"))
try:
    from assemble import author_only
except ImportError as exc:
    raise SystemExit(f"compose/assemble.py owns the audience declaration and "
                     f"could not be imported ({exc})")
guides = root / "claude" / "guides"
if not guides.is_dir():
    raise SystemExit(f"{guides} is missing; the payload is incomplete")
for p in sorted(guides.glob("*.md")):
    if author_only(p):
        print(p.name)
PY
  ); then
    # stderr, not stdout: every caller reads this function through a command
    # substitution, so anything printed normally would be captured INTO the
    # variable instead of reaching the operator — and `exit` here would leave
    # only the subshell, letting the caller proceed with the error text as its
    # list of withheld guides. The caller checks the status and exits itself.
    log "cannot read which guides are author-only — refusing to deploy rather than" >&2
    log "  shipping them by default. compose/assemble.py owns that declaration and" >&2
    log "  must be present; reinstall the package." >&2
    return 1
  fi
  printf '%s\n' "$out"
}

# Remove a withheld guide from a directory this installer deploys into, backing it
# up first exactly as deploy_file backs up a file it is about to overwrite. An
# unconditional rm would delete a same-named file this installer never wrote, and
# a shared or symlinked guides directory makes that somebody's own file.
prune_withheld() {
  local dstdir="$1" base
  printf '%s\n' "$WITHHELD_GUIDES" | while IFS= read -r base; do
    [ -n "$base" ] || continue
    [ -f "$dstdir/$base" ] || continue
    if [ -n "$BACKUP_DIR" ]; then
      run mkdir -p "$(dirname "$BACKUP_DIR$dstdir/$base")"
      run cp "$dstdir/$base" "$BACKUP_DIR$dstdir/$base"
    fi
    run rm -f "$dstdir/$base"
    [ "$DRY_RUN" = 1 ] || info "withheld (audience: author), removed stale copy: $dstdir/$base"
  done
}

# ---- corpus deploy -------------------------------------------------------
# assemble.py owns the corpus surfaces (central tree, entry seeding, codex marker region,
# settings merge). The entry CLAUDE.md and AGENTS.md are NOT manifested — the entry is
# user-owned after seeding and AGENTS.md holds a personal region — so uninstall removes our
# central tree and marked regions and leaves the user's file itself alone.
# There is ONE install shape. There used to be two: a "full" deploy that wrote the corpus into
# the entry file, and a packaged one that assembled selected domains under `central/` and left the
# entry file to the user. They differed in the thing that matters most — who owns the entry file —
# so the same path was ours in one mode and theirs in the other, and no rule about user-owned
# content could be true of both. Full mode is now "every domain selected": the same assembly, the
# same ownership, one set of answers.
#
# What this buys, in the order the questions were asked: the user's own additions live in a file
# we never rewrite, so they are separately versioned by construction; a package can be added or
# dropped later by re-assembling, with no need to know which bytes came from where; and uninstall
# can take everything of ours because nothing of theirs is mixed into it.
all_domains_csv() {
  python3 -c "import json,sys;print(','.join(sorted(json.load(open(sys.argv[1]))['domains'])))" \
    "$REPO/compose/domains.json"
}

assemble_corpus() {
  local args=(--claude-dir "$CLAUDE_DIR" --codex-dir "$CODEX_DIR" --state-dir "$STATE_DIR") rc=0
  # No flag and no saved selection: install everything. This is what "full" meant, expressed as
  # a selection so it goes down the same path as every other one (selection_args).
  selection_args
  args+=(${SEL_ARGS[@]+"${SEL_ARGS[@]}"})
  [ "$DRY_RUN" = 1 ] && args+=(--dry-run)
  # A dry run never truncated the manifest, so the live one still describes the last install.
  local prior="$PRIOR_MANIFEST"
  [ "$DRY_RUN" = 1 ] && prior="$MANIFEST"
  [ -f "$prior" ] && args+=(--prior-manifest "$prior")
  python3 "$REPO/compose/assemble.py" "${args[@]}" || rc=$?
  if [ "$rc" = 2 ]; then
    ENTRY_NEEDS_ACTION=1
    log "entry file needs user action (import line missing); central content will not load until it is added"
  elif [ "$rc" != 0 ]; then
    return 1
  fi
  if [ "$DRY_RUN" != 1 ]; then
    # The ownership rule is the assembler's, and it is one rule for every destination: the
    # name exists in our source tree (compose/assemble.py copy_filtered — "it is not in
    # src_dir, so it is never a candidate"). `central/` was exempted as "ours whole" and
    # scanned, which claimed whatever a user had put there — and uninstall removes whatever
    # the manifest names, so the assembler's care was undone one step later. That is the
    # same defect this comment records having fixed for the SHARED $CODEX_DIR/guides; the
    # directory being ours by convention did not make the scan a different mistake.
    # bundle.md is generated rather than copied, so it has no source name and is ours
    # unconditionally.
    local g dst sub s
    if [ -f "$CLAUDE_DIR/central/bundle.md" ]; then
      printf '%s\n' "$CLAUDE_DIR/central/bundle.md" >> "$MANIFEST"
    fi
    # A guide can carry a same-stem companion tree.  The assembler owns that structure, so
    # manifest it through its resolver rather than flattening `guides/*.md`: uninstall needs
    # every deployed script/asset by its exact path, and must not claim a user-created sibling
    # merely because it sits below one of our guide directories.
    local source_guides="$REPO/claude/guides" codex_guides="$REPO/codex/guides"
    manifest_guide_members() {
      # Pin the installed resolver file independently of the selected content tree.
      python3 - "$REPO/compose/assemble.py" "$1" "$2" <<'PY'
import pathlib
import sys

assembler, source, dest = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(assembler.parent))
from assemble import GuideMemberError, guide_member_map

try:
    members = guide_member_map(source)
except GuideMemberError as exc:
    raise SystemExit(f"invalid guide bundle source: {exc}")
for paths in members.values():
    for rel in paths:
        target = dest / rel
        if target.is_file():
            print(target)
PY
    }
    if ! manifest_guide_members "$source_guides" "$CLAUDE_DIR/central/guides" >> "$MANIFEST"; then
      log "could not enumerate assembled Claude guide members for the manifest"
      return 1
    fi
    for sub in hooks agents; do
      for s in "$REPO"/claude/"$sub"/*; do
        [ -f "$s" ] || continue
        dst="$CLAUDE_DIR/central/$sub/$(basename "$s")"
        # if-form for the reason spelled out below: a trailing false status becomes the
        # loop's, then the function's, and the install dies silently after ASSEMBLED.
        if [ -f "$dst" ]; then printf '%s\n' "$dst" >> "$MANIFEST"; fi
      done
    done
    if ! manifest_guide_members "$codex_guides" "$CODEX_DIR/guides" >> "$MANIFEST"; then
      log "could not enumerate assembled Codex guide members for the manifest"
      return 1
    fi
  fi
  return 0
}

add_zsh_hook() {
  local found
  found="$(zsh_hook_locations)"
  if [ -n "$found" ]; then
    # Appending beside an existing copy would source the integration twice per shell.
    info "zsh hook present  $(printf '%s' "$found" | tr '\n' ' ')"
    return
  fi
  if [ "$DRY_RUN" = 1 ]; then info "[dry-run] append zsh hook to $ZSHRC"; return; fi
  printf '%s\n' "$ZSH_HOOK" >> "$ZSHRC"
  info "added zsh hook  $ZSHRC"
}

# Carry state written under the pre-rename directory so an existing install keeps
# its manifest and backups instead of stranding them.
migrate_state() {
  if [ -d "$STATE_DIR" ] || [ ! -d "$LEGACY_STATE_DIR" ]; then
    return
  fi
  if [ "$DRY_RUN" = 1 ]; then
    info "[dry-run] migrate state $LEGACY_STATE_DIR -> $STATE_DIR"
    return
  fi
  mkdir -p "$(dirname "$STATE_DIR")"
  mv "$LEGACY_STATE_DIR" "$STATE_DIR" && info "migrated state  $LEGACY_STATE_DIR -> $STATE_DIR"
}

# ---- codex live-config additions -----------------------------------------
# The live ~/.codex/config.toml is user/runtime-owned; agent-bios never
# deploys or overwrites it. codex/config-additions.toml declares the only
# content agent-bios manages there — one marked [agents.*] block plus a tagged
# features.multi_agent line — and this helper merges (install), checks
# (verify), or removes (uninstall) exactly that content, backed up and
# tomllib-validated before any write. Modes: merge | check | remove.
codex_config_additions() {
  AB_MODE="$1" AB_CODEX_DIR="$CODEX_DIR" AB_FRAGMENT="$REPO/codex/config-additions.toml" \
  AB_BACKUP="${BACKUP_DIR:-}" AB_DRY="$DRY_RUN" python3 - <<'PY'
import os, pathlib, sys, tomllib

mode = os.environ["AB_MODE"]
codex_dir = pathlib.Path(os.environ["AB_CODEX_DIR"])
fragment_path = pathlib.Path(os.environ["AB_FRAGMENT"])
backup_root = os.environ.get("AB_BACKUP", "")
dry = os.environ.get("AB_DRY") == "1"
target = codex_dir / "config.toml"
BEGIN = "# >>> agent-bios additions >>>"
END = "# <<< agent-bios additions <<<"
TAG = "# agent-bios"

def info(msg): print(f"  {msg}")
def fail(msg): print(msg); sys.exit(1)

frag_text = fragment_path.read_text().replace("${CODEX_HOME}", str(codex_dir))
want_agents = tomllib.loads(frag_text)["agents"]
live_text = target.read_text() if target.is_file() else ""
try:
    live = tomllib.loads(live_text) if live_text else {}
except Exception as exc:
    fail(f"live codex config does not parse; not touching it: {target} ({exc})")

def state_ok():
    if live.get("features", {}).get("multi_agent") is not True:
        return False
    return all(
        live.get("agents", {}).get(name, {}).get(key) == spec[key]
        for name, spec in want_agents.items()
        for key in ("description", "config_file")
    )

if mode == "check":
    problems = []
    if live.get("features", {}).get("multi_agent") is not True:
        problems.append("features.multi_agent is not true")
    for name, spec in want_agents.items():
        if live.get("agents", {}).get(name, {}).get("config_file") != spec["config_file"]:
            problems.append(f"agents.{name}.config_file drifted or missing")
        elif not pathlib.Path(spec["config_file"]).is_file():
            problems.append(f"agents.{name} template missing: {spec['config_file']}")
    if problems:
        fail(f"codex config additions: {'; '.join(problems)} ({target})")
    info("codex config additions OK")
    sys.exit(0)

def strip_managed(text):
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s == BEGIN: skipping = True; continue
        if s == END: skipping = False; continue
        if skipping or s.endswith(TAG): continue
        out.append(line)
    return "".join(out)

if mode == "remove":
    if not target.is_file():
        sys.exit(0)
    stripped = strip_managed(live_text)
    if stripped == live_text:
        info(f"no agent-bios additions in {target}")
        sys.exit(0)
    try:
        tomllib.loads(stripped)
    except Exception as exc:
        fail(f"refusing removal; result would not parse: {exc}")
    if dry:
        info(f"[dry-run] remove agent-bios additions from {target}")
        sys.exit(0)
    backup = target.with_name(target.name + ".bak-agent-bios-uninstall")
    backup.write_text(live_text)
    target.write_text(stripped)
    info(f"removed additions  {target} (backup: {backup.name})")
    sys.exit(0)

# mode == merge
if state_ok():
    info(f"unchanged  {target} (additions present)")
    sys.exit(0)

# A drifted [agents.<tier>] outside our markers would become a duplicate
# table if we appended ours; that conflict needs the user, not a clobber.
base = strip_managed(live_text)
base_data = tomllib.loads(base) if base.strip() else {}
clash = [name for name in want_agents if name in base_data.get("agents", {})]
if clash:
    fail(
        f"unmanaged [agents.{'/'.join(clash)}] with drifted content in {target}; "
        "align or remove them, then rerun install"
    )

block_lines = [BEGIN]
if "features" not in base_data:
    block_lines += ["[features]", f"multi_agent = true  {TAG}"]
for name, spec in want_agents.items():
    block_lines += [
        f"[agents.{name}]",
        f'description = "{spec["description"]}"',
        f'config_file = "{spec["config_file"]}"',
    ]
block_lines.append(END)
block = "\n".join(block_lines) + "\n"

new_text = base
if "features" in base_data:
    if base_data["features"].get("multi_agent") is None:
        lines = new_text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip() == "[features]":
                lines.insert(i + 1, f"multi_agent = true  {TAG}\n")
                break
        new_text = "".join(lines)
    elif base_data["features"].get("multi_agent") is not True:
        info(f"note: features.multi_agent explicitly set in {target}; leaving it")
if new_text and not new_text.endswith("\n"):
    new_text += "\n"
new_text += ("\n" if new_text else "") + block

try:
    tomllib.loads(new_text)
except Exception as exc:
    fail(f"merge result would not parse; live config untouched ({exc})")
if dry:
    info(f"[dry-run] merge agent-bios additions into {target}")
    sys.exit(0)
if live_text and backup_root:
    bpath = pathlib.Path(backup_root + str(target))
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(live_text)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(new_text)
info(f"merged additions  {target}")
PY
}

# ---- optional dependencies -----------------------------------------------
# Capabilities are optional: a missing one only degrades the review routes that
# need it. launch/agent-launch.toml is the single source for both the command
# that gates a route and the install line offered here.
capability_table() {
  python3 - "$REPO/launch/agent-launch.toml" <<'PY'
import sys, tomllib
# `${backend}` means "the CLI of the host this capability offers on". Resolved HERE because
# the probe below runs `command -v` on whatever this prints, and the literal sentinel is not
# a command: the built-in workflow capability reported as unavailable while the launcher ran
# it perfectly well.
data = tomllib.load(open(sys.argv[1], "rb"))
backends = data.get("backends", {})
for name, cap in data.get("capabilities", {}).items():
    command = cap.get("command", "")
    if command == "${backend}":
        hosts = sorted({h for offer in cap.get("offers", []) for h in offer.get("hosts", [])})
        command = next(
            (backends[h]["command"] for h in hosts if backends.get(h, {}).get("command")), ""
        )
    print("\t".join((name, command, cap.get("install", ""))))
PY
}

install_capability() {
  local name="$1" line="$2"
  log "Installing optional dependency $name: $line"
  if [ "$DRY_RUN" = 1 ]; then info "[dry-run] $line"; return 0; fi
  if sh -c "$line"; then info "installed  $name"; else log "warning: installing $name failed; routes needing it stay degraded"; fi
}

handle_capabilities() {
  local requested="$1" name command line
  # Fail on a typo rather than silently installing nothing.
  local known; known=$(capability_table | cut -f1)
  local want
  for want in ${requested//,/ }; do
    printf '%s\n' "$known" | grep -qx "$want" || {
      log "unknown --with capability: $want (known: $(printf '%s' "$known" | tr '\n' ' '))"; return 1; }
  done
  while IFS=$'\t' read -r name command line; do
    [ -n "$name" ] || continue
    if command -v "$command" >/dev/null 2>&1; then
      info "capability present  $name ($command)"
      # Explicitly requested, already there, and nothing to install: say so, because after
      # the rename `--with ultracode` names the claude-backed reviewer — which needs no
      # install — while the tool the user probably meant stays missing and is only hinted
      # at further down. The request silently no-opped and install still exited 0.
      if [ -z "$line" ] && printf '%s\n' "${requested//,/ }" | tr ' ' '\n' | grep -qx "$name"; then
        log "note: $name needs no install (it is the host CLI); nothing was installed for it"
        local installable
        installable=$(capability_table | awk -F'\t' -v me="$name" '$1 != me && $3 != "" { print $1 }' | tr '\n' ' ')
        [ -n "$installable" ] && log "      capabilities that DO install: ${installable% }"
      fi
      continue
    fi
    if printf '%s\n' "${requested//,/ }" | tr ' ' '\n' | grep -qx "$name"; then
      [ -n "$line" ] && install_capability "$name" "$line" \
        || log "note: $name has no configured install line"
    elif [ -n "$line" ] && [ -t 0 ] && [ "$DRY_RUN" != 1 ]; then
      printf '  Install optional dependency %s? (%s) [y/N] ' "$name" "$line"
      local answer=""; read -r answer </dev/tty || answer=""
      case "$answer" in
        [yY]*) install_capability "$name" "$line" ;;
        *) info "skipped  $name — install later: $line" ;;
      esac
    else
      info "optional  $name unavailable; routes needing it degrade${line:+ — install: $line}"
    fi
  done <<EOF
$(capability_table)
EOF
}

# Presets the launcher saved into the deployed profiles.toml (pre-split, or by hand)
# would be lost to the cp below; move them into the user-owned presets file first.
migrate_user_presets() {
  local src="$REPO/launch/agent-launch.toml"
  local dst="$LAUNCH_DIR/profiles.toml"
  local user="$LAUNCH_DIR/$USER_PRESETS_NAME"
  [ -f "$dst" ] || return 0
  python3 - "$src" "$dst" "$user" "$DRY_RUN" <<'PY' || { log "user preset migration failed; not overwriting $LAUNCH_DIR/profiles.toml"; return 1; }
import os, pathlib, re, sys, tomllib

src, dst, user, dry_run = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), sys.argv[4] == "1"
dst_text = dst.read_text()
shipped = set(tomllib.loads(src.read_text()).get("presets", {}))
extra = set(tomllib.loads(dst_text).get("presets", {})) - shipped
if not extra:
    sys.exit(0)
existing_text = user.read_text() if user.is_file() else ""
already = set(tomllib.loads(existing_text).get("presets", {})) if existing_text else set()
move = sorted(extra - already)
for name in sorted(extra & already):
    print(f"  kept in {user.name}  {name} (already saved there)")
if not move:
    sys.exit(0)

header = re.compile(r'^\[presets\.(?:"([^"]+)"|([A-Za-z0-9][A-Za-z0-9_-]*))(?:[.\]])')
blocks, current = {}, None
for line in dst_text.splitlines(keepends=True):
    stripped = line.strip()
    if stripped.startswith("["):
        found = header.match(stripped)
        current = (found.group(1) or found.group(2)) if found else None
    if current in move:
        blocks.setdefault(current, []).append(line)
# Refuse to deploy over a preset we could not carry across, rather than drop it.
missing = [name for name in move if name not in blocks]
if missing:
    sys.exit(f"cannot extract preset block(s) from {dst}: {', '.join(missing)}")

out = existing_text.rstrip("\n") or (
    "# agent-launch user presets, moved out of profiles.toml by agent-bios install.\n"
    "# The installer never deploys or verifies this file, so presets here survive upgrades."
)
for name in move:
    out += "\n\n" + "".join(blocks[name]).strip("\n")
for name in move:
    print(f"  {'[dry-run] ' if dry_run else ''}moved preset  {name} -> {user}")
if dry_run:
    sys.exit(0)
user.parent.mkdir(parents=True, exist_ok=True)
temporary = user.with_name(f".{user.name}.{os.getpid()}.tmp")
temporary.write_text(out + "\n")
os.replace(temporary, user)
PY
}

remove_zsh_hook() {
  local other
  # Named, never edited: a line this installer did not write is the user's, and uninstall
  # removing it would be editing a file it does not own.
  other="$(zsh_hook_locations | grep -vF "$ZSHRC" || true)"
  [ -n "$other" ] && info "zsh hook also in $(printf '%s' "$other" | tr '\n' ' ') — left in place (not written by this installer)"
  if [ ! -f "$ZSHRC" ] || ! grep -qF "$HOOK_MARK" "$ZSHRC"; then
    info "no zsh hook to remove  $ZSHRC"
    return
  fi
  if [ "$DRY_RUN" = 1 ]; then info "[dry-run] remove zsh hook from $ZSHRC"; return; fi
  grep -vF "$HOOK_MARK" "$ZSHRC" > "$ZSHRC.agent-tmp" && mv "$ZSHRC.agent-tmp" "$ZSHRC"
  info "removed zsh hook  $ZSHRC"
}

# Promote -> migrate (collection loop, Phase 4): after the corpus is deployed,
# clear personal copies of learnings that have been promoted into the shared
# corpus AND are in this user's assembled bundle. Best-effort: a prune failure
# (or an absent manifest/script) never fails the install. Runs per host.
migrate_learnings() {
  local script="$REPO/learn/migrate-learnings.py"
  { [ -f "$script" ] && [ -f "$REPO/learn/promotions.json" ]; } || return 0
  local -a sel dry
  # The SAME three-way assemble_corpus resolves, because these two must be answering one
  # question. Naming only the selection file made a fresh `--dry-run` preview migration as
  # "skipped" — a dry run deliberately does not write selection.json, while the real run
  # writes it moments earlier and then migrates for real. A preview that reports the
  # opposite of what the run does is worse than no preview.
  if [ "${DOMAINS_SET:-0}" = 1 ]; then
    sel=(--domains "$DOMAINS_ARG")
  elif [ -f "$STATE_DIR/selection.json" ]; then
    sel=(--selection-file "$STATE_DIR/selection.json")
  else
    sel=(--domains "$(all_domains_csv)")
  fi
  [ "$DRY_RUN" = 1 ] && dry=(--dry-run) || dry=()
  # ${dry[@]+...}: expanding an empty array as "${dry[@]}" is an unbound-variable
  # error under `set -u` on bash 3.2 (macOS default) and would abort the install.
  python3 "$script" --host claude --config-dir "$CLAUDE_DIR" "${sel[@]}" ${dry[@]+"${dry[@]}"} \
    || info "learnings migrate (claude) skipped"
  python3 "$script" --host codex --config-dir "$CODEX_DIR" "${sel[@]}" ${dry[@]+"${dry[@]}"} \
    || info "learnings migrate (codex) skipped"
}

# ---- subcommands ---------------------------------------------------------
cmd_install() {
  check_prereqs || { log "resolve the prerequisites above and retry"; exit 1; }
  migrate_state
  if [ "$DRY_RUN" != 1 ]; then
    mkdir -p "$STATE_DIR"
    BACKUP_DIR="$STATE_DIR/backups/$(date +%Y%m%d-%H%M%S)"
    [ -f "$MANIFEST" ] && cp "$MANIFEST" "$PRIOR_MANIFEST"
    : > "$MANIFEST"
    # The manifest is emptied here and refilled as files are deployed, so between this
    # line and a completed install it does not describe what is on disk. An install that
    # fails in between — `--domains no-such-domain` is enough — left it EMPTY, and
    # `uninstall` consumes it: it removed nothing, exited 0, and told the user the
    # uninstall had succeeded while all fifty deployed files were still there. A
    # destructive command reporting success for doing nothing is the worst reading in
    # this file, so the prior manifest goes back unless the install reaches the end.
    INSTALL_COMPLETED=0
    trap 'if [ "${INSTALL_COMPLETED:-0}" != 1 ] && [ -f "$PRIOR_MANIFEST" ]; then
            cp "$PRIOR_MANIFEST" "$MANIFEST"
            log "install did not complete; restored the previous manifest so uninstall still knows what was deployed"
          fi' EXIT
  fi
  log "Deploying agent-bios from $REPO"
  # Refuse loudly before doing any work: an unreadable declaration must not degrade
  # into withholding nothing, which is the fail-open shape this rule exists to avoid.
  WITHHELD_GUIDES="$(author_only_guides)" || exit 1
  assemble_corpus || exit 1
  # assemble.py withholds author-only guides and prunes the destinations it writes.
  # $CLAUDE_DIR/guides is not one of them — it is where the pre-unification full
  # install put guides, so a machine that installed then would keep its copy for good.
  prune_withheld "$CLAUDE_DIR/guides"
  migrate_learnings   # Phase 4: clear personal copies now absorbed by the corpus
  deploy_glob "$REPO/codex/agents" "*.toml" "$CODEX_DIR/agents"
  # Resolved once, before the prune that reads it: an assembler that cannot answer must
  # stop the install here, not let `for skill in $(...)` iterate an empty answer and
  # deploy nothing while reporting success.
  SELECTED_SKILLS="$(selected_skills)" || { log "could not resolve the selected skills"; exit 1; }
  prune_stale_skills
  local skill
  for skill in $SELECTED_SKILLS; do
    deploy_tree "$REPO/claude/skills/$skill" "$CLAUDE_DIR/skills/$skill" || exit 1
    deploy_tree "$REPO/claude/skills/$skill" "$CODEX_DIR/skills/$skill" || exit 1
  done
  codex_config_additions merge || exit 1
  deploy_file "$REPO/wrappers/codex-run.sh"  "$CODEX_DIR/bin/codex-run"  "+x"
  deploy_file "$REPO/wrappers/codex-helm.sh" "$CODEX_DIR/bin/codex-helm" "+x"
  # The claude-side adapter lands under CLAUDE_DIR for the same reason its codex twin
  # lands under CODEX_DIR: each is that host's, and a single shared bin would make the
  # two families' review routes indistinguishable from their install paths.
  deploy_file "$REPO/wrappers/claude-run.sh" "$CLAUDE_DIR/bin/claude-run" "+x"
  migrate_user_presets || exit 1   # must precede the deploy below, which overwrites profiles.toml
  deploy_file "$REPO/launch/agent-launch.toml" "$LAUNCH_DIR/profiles.toml"
  deploy_file "$REPO/launch/agent-launch.zsh"   "$LAUNCH_DIR/shell.zsh"
  # UI text catalogs: deploy-managed siblings of the config, one per language.
  # The launcher resolves them from the config path, so the deployed home is
  # $LAUNCH_DIR/i18n exactly as the checkout's is launch/i18n.
  #
  # The launcher goes FIRST, and the order is chosen for how an interrupted
  # install FAILS rather than for how much it breaks. The deployed launcher keeps
  # no catalog beside itself -- it lives in $BIN_DIR while the catalogs live under
  # $LAUNCH_DIR -- so it renders whatever is deployed, and the two orders leave
  # opposite states:
  #
  #   launcher first  -> new launcher, old catalogs: keys it added render as their
  #                      own names AND t() prints "the deployed catalogs are older
  #                      than this launcher; run: agent-bios install". Loud, and
  #                      the message is the fix.
  #   catalogs first  -> old launcher, new catalogs: a value whose SHAPE changed
  #                      renders its template. Measured on the 1ba2d82 launcher
  #                      against these catalogs, the checklist drew
  #                      "선택 적용{pending}" with no diagnostic at all.
  #
  # The second is less broken and entirely silent, which is the worse trade: a
  # user cannot act on what does not announce itself. This ordering was briefly
  # the other way round on the claim that spare keys are harmless; they are, but
  # changed values are not, and four keys in this change altered shape.
  #
  # The loudness is contingent, not structural, and narrower than an earlier version
  # of this comment claimed: the notice fires only for a key the FIRST SCREEN itself
  # requests and the old catalogs lack. Adding keys anywhere is not enough. This
  # release adds four and the root screen requests none of them — they are reached
  # from the registration wizard and the corpus screens — so for this release the
  # ordering buys no diagnostic at all, only the smaller blast radius of a launcher
  # that is newer than its catalogs rather than older. The shape-changed keys are
  # silent in that direction too: an old value with no slot formats to itself and the
  # argument simply vanishes. Keep the order for the blast radius; do not rely on the
  # diagnostic unless a release actually adds a root-screen key.
  deploy_file "$REPO/launch/agent-launch.py"  "$BIN_DIR/agent-launch" "+x"
  local lang
  for lang in en ko ja; do
    deploy_file "$REPO/launch/i18n/$lang.toml" "$LAUNCH_DIR/i18n/$lang.toml"
  done
  log ""
  log "Optional dependencies (missing ones only degrade the routes that need them)..."
  handle_capabilities "$WITH" || exit 1
  log ""
  if [ "$DRY_RUN" = 1 ]; then
    info "[dry-run] provision managed Textual venv"
  else
    bash "$REPO/launch/provision-venv.sh" && info "managed venv OK" \
      || log "warning: venv provisioning failed (numbered-prompt fallback applies)"
  fi
  add_zsh_hook
  # Guarded, because this WRITES. The projection takes a lock and rewrites
  # corpus-status.json, and it sat outside the dry-run branch above — so
  # `install --dry-run` changed the file whose whole purpose is to describe what is
  # deployed, against this script's own `--dry-run  print actions without changing
  # anything` and README's identical sentence. A dry run that edits state is worse than
  # no dry run: it is consulted precisely when the user is unwilling to touch anything.
  #
  # The projection is REQUIRED, not best-effort. It used to be neither: stderr and the
  # exit status were both discarded and every failure printed one guess of a note —
  # "versions.json/ledger missing?" — which was wrong for the failure that actually
  # happened. `compose/corpus-state.py` was not in the npm package at all, so a real
  # npm install rewrote the corpus, updated selection.json and version.json, passed
  # verification, exited 0, and left corpus-status.json stale from a previous
  # deployment. The launcher's corpus panel reads that file, so the machine reported a
  # selection the successful run had not recorded. A command that deploys the launcher
  # and advertises its panel cannot call that a success.
  #
  # The script now ships and degrades honestly in an npm layout (domains real,
  # version/ledger reported unavailable), so the remaining failures are real ones:
  # an unwritable destination, an invalid status, a missing interpreter. Those fail
  # the install, and the reason reaches the operator instead of /dev/null.
  if [ "$DRY_RUN" = 1 ]; then
    info "[dry-run] project corpus-status"
  else
    local projection_log
    projection_log="$(mktemp -t corpus-projection)"
    if python3 "$REPO/compose/corpus-state.py" project --repo "$REPO" >"$projection_log" 2>&1; then
      info "corpus-status projected"
      rm -f "$projection_log"
    else
      log "corpus-status projection FAILED — the launcher's corpus panel would report a"
      log "selection this run did not record. Its own output:"
      sed 's/^/    /' "$projection_log"
      log "    full output: $projection_log"
      PROJECTION_FAILED=1
    fi
  fi
  # Deploy/system version marker for the launcher's TUI version line, read from
  # package.json (version + releaseDate) — distinct from the corpus content
  # version. Best-effort: a failure here never fails the install.
  if [ "$DRY_RUN" != 1 ]; then
    if python3 - "$REPO/package.json" "$STATE_DIR/version.json" "$REPO/provenance.json" \
         "$([ -e "$REPO/.git" ] && echo clone || echo package)" <<'PY' 2>/dev/null
import json, os, sys
pkg = json.load(open(sys.argv[1]))
out = {"version": pkg.get("version"), "releaseDate": pkg.get("releaseDate"),
       "source": sys.argv[4]}
# Publication provenance rides along ONLY for a package-layout source: in a
# clone, git itself is the live provenance and a provenance.json on disk is by
# definition residue (a failed pack's leftover stamp) — ingesting it once let a
# clone deployment of commit B carry a stale label A into the state marker.
if sys.argv[4] == "package" and os.path.isfile(sys.argv[3]):
    try:
        prov = json.load(open(sys.argv[3]))
        if prov.get("commit"):
            out["commit"] = prov["commit"]
        if prov.get("dirty"):
            out["dirty"] = True
    except Exception:
        pass
with open(sys.argv[2], "w") as f:
    json.dump(out, f)
    f.write("\n")
PY
    then
      printf '%s\n' "$STATE_DIR/version.json" >> "$MANIFEST"
      info "version marker written ($STATE_DIR/version.json)"
    else
      log "note: version marker not written (package.json unreadable)"
    fi
  fi
  log ""
  if [ "$DRY_RUN" = 1 ]; then
    # A dry run wrote nothing, so there is nothing of THIS plan to verify. Running the live
    # verifier anyway made a valid preview exit 1 on any machine where the planned files are
    # not already present — which is every fresh one, the case a preview is most for. On an
    # installed machine it is no better: it would be reporting on the previous install while
    # standing where a verdict on the plan just printed belongs.
    INSTALL_COMPLETED=1
    log "[dry-run] nothing was written, so nothing is verified — re-run without --dry-run to install."
    return 0
  fi
  log "Verifying deployment..."
  if cmd_verify; then
    # Reached the end: the manifest now describes what is actually deployed, so the
    # restore armed above must not fire.
    INSTALL_COMPLETED=1
    log ""
    # Withheld when the projection failed: the run below reports INSTALL INCOMPLETE and
    # exits non-zero, and printing "Done." first told the operator both things in the
    # same breath. The manifest is already complete by here, which is the point — the
    # files really are deployed; what failed is the record of WHICH selection they are.
    if [ "$PROJECTION_FAILED" != 1 ]; then
      log "Done. Open a new shell (or: source \"$ZSHRC\") to activate the zero-arg launcher."
    fi
    if [ "${ENTRY_NEEDS_ACTION:-0}" = 1 ]; then
      log ""
      log "ONE STEP LEFT: add this line to $CLAUDE_DIR/CLAUDE.md (yours; we never rewrite it):"
      log "  @central/bundle.md"
      log "Until then the deployed corpus will not load."
    fi
    # An untouched backup dir means nothing was replaced; that healthy state
    # must not become a nonzero exit under set -e.
    { [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ] && log "Replaced files were backed up under $BACKUP_DIR"; } || true
    prune_backups
    if [ "$PROJECTION_FAILED" = 1 ]; then
      log ""
      log "INSTALL INCOMPLETE: the corpus is deployed and the manifest records it, but the"
      log "corpus-status projection failed above — the launcher's panel would describe a"
      log "state this run did not record. Fix the cause and re-run: agent-bios install"
      exit 1
    fi
  else
    log "VERIFY FAILED after install — see messages above"
    exit 1
  fi
}

verify_match()   { if cmp -s "$1" "$2"; then info "match    $2"; else log "MISMATCH/absent  $2"; return 1; fi; }
verify_present() { if [ -f "$1" ]; then return 0; else log "missing  $1"; return 1; fi; }

cmd_verify() {
  local fail=0 gp gb
  if [ ! -e "$REPO/.git" ] && [ "$(drift_state)" = "drift" ]; then
    log "deploy drift: $(drift_detail) — run: agent-bios install"
    fail=1
  fi
  # Not mode-specific: an author-only guide must be absent from EVERY directory any
  # install writes, including the one the pre-unification full install owned.
  local verify_withheld
  verify_withheld="$(author_only_guides)" || return 1
  for gb in $verify_withheld; do
    for gp in "$CLAUDE_DIR/guides/$gb" "$CLAUDE_DIR/central/guides/$gb" "$CODEX_DIR/guides/$gb"; do
      if [ -f "$gp" ]; then
        log "author-only guide is still installed: $gp"; fail=1
      fi
    done
  done
  [ -n "$verify_withheld" ] && info "author-only guides withheld: $(printf '%s' "$verify_withheld" | tr '\n' ' ')"
  # Corpus surfaces are selection-derived, not repo-identical, so verify reads the assembled
  # shape rather than byte-comparing against the repo. The entry file is user-owned — READ-check
  # the import line, never rewrite it.
  python3 "$REPO/compose/check-domains.py" >/dev/null 2>&1 && info "domains gate OK" || { log "domains gate FAILED"; fail=1; }
  verify_present "$CLAUDE_DIR/central/bundle.md" || fail=1
  if grep -qF '@central/bundle.md' "$CLAUDE_DIR/CLAUDE.md" 2>/dev/null; then
    info "entry import line present"
  elif [ "${ENTRY_NEEDS_ACTION:-0}" = 1 ]; then
    # The install that just ran said this, and said it because the file is the user's and is
    # never rewritten. Failing on it a second time turned a deployment that fully succeeded
    # into one whose record was rolled back. Standalone `agent-bios verify` has this unset,
    # so it still reports a corpus that is not loading as the failure it is.
    log "ACTION NEEDED: add '@central/bundle.md' to $CLAUDE_DIR/CLAUDE.md — everything else deployed"
  else
    log "entry $CLAUDE_DIR/CLAUDE.md lacks '@central/bundle.md' — central corpus is NOT loading"; fail=1
  fi
  if grep -qF 'agent-bios:central:start' "$CODEX_DIR/AGENTS.md" 2>/dev/null; then
    info "codex central region present"
  else
    log "codex AGENTS.md central region missing"; fail=1
  fi
  # Every capability must probe as a real command. `${backend}` reaching this table means
  # the sentinel was not resolved, and the probe below would then report a capability the
  # launcher can run perfectly well as unavailable.
  if capability_table | awk -F'\t' '$2 == "" || $2 == "${backend}" { print; found=1 } END { exit !found }' >/dev/null 2>&1; then
    log "capability table has an unresolved or empty command — the installer would misreport it"; fail=1
  else
    info "capability commands resolve"
  fi
  # The help's --with list must BE the capability table, not a copy of it: the copy went
  # stale on the first rename and advertised a name that selects a different capability
  # than the one carrying the install line.
  local advertised table
  advertised=$(usage 2>/dev/null | sed -n 's/^ *--with names: //p')
  table=$(capability_table 2>/dev/null | cut -f1 | tr '\n' ' ')
  if [ "$advertised" = "${table% }" ]; then
    info "--with help matches the capability table"
  else
    log "--with help advertises '$advertised' but the capabilities are '${table% }'"; fail=1
  fi
  verify_match "$REPO/launch/agent-launch.py" "$BIN_DIR/agent-launch"        || fail=1
  verify_match "$REPO/launch/agent-launch.toml" "$LAUNCH_DIR/profiles.toml"   || fail=1
  verify_match "$REPO/launch/agent-launch.zsh"  "$LAUNCH_DIR/shell.zsh"        || fail=1
  # Evidence, never a verdict: a shadow that was repaired is the mechanism working.
  shell_shadow_summary
  # Not `whence -v`: a function redefined at preexec carries no "from FILE" annotation,
  # so in exactly the shell the reassert repaired, whence reads as "not ours". And not a
  # substring of the body either — a foreign body can quote it. Byte-equality with the
  # body the interception captured when it was sourced is the same test the reassert runs.
  info "live check (run in the terminal you use): [[ \"\$functions[claude]\" == \"\$_agent_launch_body[claude]\" ]] && print OURS   → expect OURS"
  # The catalogs were the one deploy-managed artifact nothing verified, which is
  # the state that renders key names on screen: the deployed launcher keeps no
  # catalog beside itself, so whatever is here IS the UI text. Byte-identity, the
  # same bar as its siblings above.
  local lang
  for lang in en ko ja; do
    verify_match "$REPO/launch/i18n/$lang.toml" "$LAUNCH_DIR/i18n/$lang.toml" || fail=1
  done
  python3 - "$CODEX_DIR/agents" <<'PY' && info "agent TOMLs OK" || fail=1
import sys, pathlib, tomllib
root = pathlib.Path(sys.argv[1])
required = {"frontier.toml", "workhorse.toml", "sweep.toml", "reviewer.toml"}
missing = required - {p.name for p in root.glob("*.toml")}
assert not missing, f"missing agent TOMLs in {root}: {sorted(missing)}"
for p in sorted(root.glob("*.toml")):
    tomllib.loads(p.read_text())
PY
  codex_config_additions check || fail=1
  # Every file of every SELECTED skill, byte-identical on both hosts — the same bar as the
  # launcher and its catalogs, because a skill's SKILL.md IS what the host reads. A skill
  # the selection does not deliver must be absent on both hosts, or the host is loading a
  # package the user did not take.
  local skill sf rel
  SELECTED_SKILLS="$(selected_skills)" || { log "could not resolve the selected skills"; fail=1; }
  for skill in $(shipped_skills); do
    if skill_selected "$skill"; then
      while IFS= read -r sf; do
        rel="${sf#"$REPO/claude/skills/$skill"/}"
        verify_match "$sf" "$CLAUDE_DIR/skills/$skill/$rel" || fail=1
        verify_match "$sf" "$CODEX_DIR/skills/$skill/$rel"  || fail=1
      done < <(find "$REPO/claude/skills/$skill" -type f | LC_ALL=C sort)
    else
      for sf in "$CLAUDE_DIR/skills/$skill/SKILL.md" "$CODEX_DIR/skills/$skill/SKILL.md"; do
        if [ -f "$sf" ]; then log "deselected skill still deployed  $sf"; fail=1
        else info "absent (deselected)  $sf"; fi
      done
    fi
  done
  if command -v codex >/dev/null 2>&1 && [ -x "$CODEX_DIR/bin/codex-helm" ]; then
    if "$CODEX_DIR/bin/codex-helm" --dry-run --mode review "probe" >/dev/null 2>&1; then
      info "codex-helm dry-run OK"
    else
      log "codex-helm dry-run FAILED"; fail=1
    fi
  fi
  # Existence first, because the guard below is written as `if executable` and a MISSING
  # adapter would satisfy it by never running — a deploy target whose only check skips
  # itself when the deploy failed is not checked at all.
  verify_present "$CLAUDE_DIR/bin/claude-run" || fail=1
  # Then WHICH version landed, because this file is on the panel's dispatch path now and
  # an older copy would dispatch reviews that quietly emit nothing. The earlier check
  # here asserted that an unpinned dispatch is refused; that guard was deliberately
  # removed when the adapter went live — refusing turned "the review ran unpinned" into
  # "the review did not run" — so asserting it would now fail against correct behaviour.
  # `--help` is the only probe that reaches no network: an unpinned run warns and then
  # dispatches for real.
  if [ -x "$CLAUDE_DIR/bin/claude-run" ]; then
    if "$CLAUDE_DIR/bin/claude-run" --help 2>/dev/null | grep -q 'REVIEW_RECEIPT_DIR'; then
      info "claude-run is receipt-aware"
    else
      log "claude-run predates the receipt contract — reviews through it emit nothing"; fail=1
    fi
  fi
  local vpy="${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}/bin/python"
  if [ -x "$vpy" ] && "$vpy" -c 'import textual' 2>/dev/null; then
    info "managed venv (textual) OK"
  else
    log "note: managed venv/textual unavailable (numbered-prompt fallback applies)"
  fi
  # A file this installer executes but never ships is invisible from a clone and
  # fatal on npm, so the payload gate runs wherever it exists (maintainer-side).
  if [ -x "$REPO/gates/check-package.sh" ]; then
    if "$REPO/gates/check-package.sh" >/dev/null 2>&1; then
      info "npm payload OK"
    else
      log "npm payload incomplete; run gates/check-package.sh"
      fail=1
    fi
  fi
  # Repo-internal mirror parity is a maintainer gate; only meaningful from a clone.
  #
  # Not from inside the install-scenario suite, though. That suite points REPO at its own
  # checkout and writes only into a sandbox HOME, so the tree this gate would judge is the
  # very tree the umbrella that launched the suite already judged — and the suite performs
  # twelve verifies. Measured 2026-08-31: 3m37s each, 43m22s of a 50m26s commit, 86% of it,
  # for twelve re-derivations of one unchanged answer that no assertion in
  # gates/test-install-guides.sh reads. The skip announces itself, because a leg that goes
  # quiet is how a suite reports clean over something it never ran. The payload and
  # prompting-target gates above are deliberately NOT skipped: at 0.16s together they buy
  # back no time, and running them keeps proving that verify still wires its gates up.
  if [ "${AGENT_BIOS_IN_INSTALL_TEST:-0}" = 1 ]; then
    info "SKIP: repo mirror parity — the umbrella running this suite already judged this tree"
  elif [ -d "$REPO/ko" ] && [ -x "$REPO/gates/check-parity.sh" ]; then
    # Output kept, not discarded — the third place in this repo where a gate's own
    # explanation went to /dev/null and left "it failed" as the entire report. The umbrella
    # and the install-scenario harness each learned this after a failure cost an eleven-
    # minute re-run that came back green; verify is where a USER meets it, with no clone to
    # re-run from.
    parity_log="$(mktemp -t verify-parity)"
    if "$REPO/gates/check-parity.sh" >"$parity_log" 2>&1; then
      info "repo mirror parity OK"; rm -f "$parity_log"
    else
      log "repo mirror parity FAILED"
      grep -a 'FAIL' "$parity_log" | head -10 | sed 's/^/    /'
      log "    full output: $parity_log"
      fail=1
    fi
  fi
  # Prompting guides name concrete models, so they go stale on a model change
  # rather than degrading quietly; this checks them against the launch config.
  if [ -x "$REPO/launch/check-prompting-targets.sh" ]; then
    if "$REPO/launch/check-prompting-targets.sh" >/dev/null 2>&1; then
      info "prompting targets OK"
    else
      log "prompting guides do not cover a configured model; run launch/check-prompting-targets.sh"
      fail=1
    fi
  fi
  return $fail
}

cmd_uninstall() {
  migrate_state
  codex_config_additions remove || log "warning: could not remove codex config additions"
  # The assembler's two spans in files we do not own — settings registrations and the AGENTS.md
  # central region — are merged in and were never removed here, so uninstall used to leave hooks
  # invoking deleted files and instructions pointing at deleted guides. It reads ownership the
  # same way the merge wrote it, so it cannot reach past what we put there.
  if [ -f "$REPO/compose/assemble.py" ]; then
    # The failure is recorded, not only printed. A warning scrolls past and the summary at
    # the end went on saying "nothing of ours is left on this machine" — while the spans this
    # step exists to remove were still in the user's settings.json, now pointing at hook files
    # the next step deletes. A warning nobody reads is how the two came to disagree.
    python3 "$REPO/compose/assemble.py" --remove-owned --claude-dir "$CLAUDE_DIR" \
      --codex-dir "$CODEX_DIR" --state-dir "$STATE_DIR" ${DRY_RUN:+} \
      $([ "$DRY_RUN" = 1 ] && echo --dry-run) \
      || { CLEANUP_FAILED=1; log "warning: could not remove assembler-owned regions"; }
  fi
  if [ -f "$MANIFEST" ]; then
    # Back up before deleting, the way install backs up before overwriting. Full mode deploys the
    # entry CLAUDE.md/AGENTS.md as ordinary targets, so they are manifested and removed here —
    # correct, since in that mode the entry file IS the corpus. What was wrong is that anything a
    # user added to it disappeared with no copy, while the same file overwritten during install
    # would have been backed up. Removal is symmetric with deployment; recoverability now is too.
    [ "$DRY_RUN" = 1 ] || { mkdir -p "$STATE_DIR"; BACKUP_DIR="$STATE_DIR/backups/uninstall-$(date +%Y%m%d-%H%M%S)"; }
    local f
    UNBACKED=0
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      [ -f "$f" ] || continue
      if [ -n "$BACKUP_DIR" ] && [ "$DRY_RUN" != 1 ]; then
        # The rule archive_and_purge applies below, applied here too: only what verifiably
        # reached a copy may be deleted. The mkdir and the cp both fail silently — a full
        # disk, a name already taken by a file — and the `&&` chain's result was never read,
        # so the deployed file was removed anyway and reached neither the backup nor the
        # archive built from it. Size equality, not cp's status, because the question is
        # whether it can be restored.
        if ! { mkdir -p "$(dirname "$BACKUP_DIR$f")" 2>/dev/null \
               && cp "$f" "$BACKUP_DIR$f" 2>/dev/null \
               && [ "$(wc -c <"$f" 2>/dev/null)" = "$(wc -c <"$BACKUP_DIR$f" 2>/dev/null)" ]; }; then
          rm -f "$BACKUP_DIR$f" 2>/dev/null   # a partial copy must not look backed up
          UNBACKED=$((UNBACKED + 1))
          log "warning: could not back up $f — leaving it in place"
          continue
        fi
      fi
      run rm -f "$f"; [ "$DRY_RUN" = 1 ] || info "removed  $f"
    done < "$MANIFEST"
    { [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ] && info "staged for the archive: $BACKUP_DIR"; } || true
    # The manifest survives whenever something it names is still on disk: it is the only
    # record of what to finish removing, and deleting it would strand those files unowned.
    if [ "$UNBACKED" -gt 0 ]; then
      log "warning: $UNBACKED deployed file(s) could not be backed up and were LEFT ON DISK;"
      log "         keeping $MANIFEST so a later uninstall can finish the job"
    else
      [ "$DRY_RUN" = 1 ] || rm -f "$MANIFEST"
    fi
  else
    log "no manifest at $MANIFEST; removing known deploy targets"
    # The two entry files are deliberately NOT in this list. `$CLAUDE_DIR/CLAUDE.md` is seeded
    # once and the user's thereafter, and `$CODEX_DIR/AGENTS.md` is ours only between the central
    # markers, which --remove-owned above already took. This branch runs precisely when state is
    # missing or agent-bios was never installed here, so nothing says we wrote either file —
    # and deleting them whole destroyed personal instructions with no copy at all, since
    # BACKUP_DIR is set only on the manifest path above.
    local p
    for p in "$CODEX_DIR/bin/codex-run" "$CODEX_DIR/bin/codex-helm" \
             "$CLAUDE_DIR/bin/claude-run" \
             "$LAUNCH_DIR/profiles.toml" "$LAUNCH_DIR/shell.zsh" "$BIN_DIR/agent-launch"; do
      [ -f "$p" ] && { run rm -f "$p"; [ "$DRY_RUN" = 1 ] || info "removed  $p"; }
    done
    # Skills: only the names the shipped tree carries, mirrored under each host's skills
    # directory, and only where the file IS ours — byte-identical to what this package
    # ships. Without a manifest, sameness of content is the one ownership evidence left:
    # a user who authored their own `skills/repo-charter/SKILL.md` before ever installing
    # would otherwise lose it here with no backup. Never the directory wholesale either —
    # a sibling skill of theirs shares the parent.
    local skill sf rel
    for skill in $(shipped_skills); do
      while IFS= read -r sf; do
        rel="${sf#"$REPO/claude/skills/$skill"/}"
        for p in "$CLAUDE_DIR/skills/$skill/$rel" "$CODEX_DIR/skills/$skill/$rel"; do
          if [ -f "$p" ]; then
            if cmp -s "$sf" "$p"; then
              run rm -f "$p"; [ "$DRY_RUN" = 1 ] || info "removed  $p"
            else
              log "kept     $p (differs from the shipped file and no manifest says we wrote it)"
            fi
          fi
        done
      done < <(find "$REPO/claude/skills/$skill" -type f | LC_ALL=C sort)
    done
  fi
  local d
  # `central/` and its subdirectories are entirely ours — the assembler creates them and the
  # manifest covers every file inside — so they belong in this sweep. They were missing from it,
  # which left three empty directories in the user's config dir after a "leave no trace" removal.
  # rmdir, never rm -rf: a directory that is not empty is one we did not fully account for, and
  # the right answer then is to leave it and be visibly incomplete.
  for d in "$CLAUDE_DIR/central/guides" "$CLAUDE_DIR/central/hooks" "$CLAUDE_DIR/central/agents" \
           "$CLAUDE_DIR/central" \
           "$CLAUDE_DIR/guides" "$CLAUDE_DIR/agents" "$CLAUDE_DIR/bin" \
           "$CODEX_DIR/guides" "$CODEX_DIR/agents" "$CODEX_DIR/bin" "$LAUNCH_DIR"; do
    [ -d "$d" ] && rmdir "$d" 2>/dev/null && info "removed empty  $d" || true
  done
  local skill
  for skill in $(shipped_skills); do rmdir_skill_dirs "$skill"; done
  remove_zsh_hook
  archive_and_purge
  log ""
  if [ "${UNBACKED:-0}" -gt 0 ]; then
    log "Uninstalled: the zsh hook, state, backups, cache, and the managed venv — and every"
    log "deployed file EXCEPT the $UNBACKED named above, which had no recoverable copy."
  else
    log "Uninstalled: deployed files, the zsh hook, state, backups, cache, and the managed venv."
  fi
  if [ "${CLEANUP_FAILED:-0}" = 1 ]; then
    log ""
    log "NOT removed: the registrations and instruction region this repo merged into files you"
    log "own — see the warning above. Re-run uninstall once that is resolved, or remove the"
    log "agent-bios entries from settings.json and the marked AGENTS.md region by hand."
    return 1
  fi
}

# Uninstall is a SECURITY operation — nothing of ours may survive it on the machine. That
# conflicts with never destroying what a user added, because full mode writes the corpus into an
# entry file they then edit, so removal takes their work with it. One artifact settles both:
# everything removed leaves as a single archive that can be handed off or deleted in one act,
# and every managed location is then purged. The archive lands in $HOME, outside every path we
# manage, because a copy inside a directory we are about to delete is not a copy.
#
# Order is the safety property: archive first, verify the archive exists, purge only then. A
# failed archive leaves the machine untouched rather than clean and empty-handed.
archive_and_purge() {
  local ts stage rel out list staged skipped
  ts="$(date +%Y%m%d-%H%M%S)"
  out="${AGENT_BIOS_UNINSTALL_ARCHIVE:-$HOME}/agent-bios-uninstall-$ts.tar.gz"
  if [ "$DRY_RUN" = 1 ]; then
    info "[dry-run] archive removed content to $out, then purge $STATE_DIR, the cache and the venv"
    return 0
  fi
  stage="$(mktemp -d)" || { log "warning: no temp dir; leaving state in place"; return 0; }
  list="$(mktemp)" || { rm -rf "$stage"; log "warning: no temp file; leaving state in place"; return 0; }
  [ -d "$STATE_DIR" ] && cp -R "$STATE_DIR" "$stage/state" 2>/dev/null
  # WHICH loose copies are ours is compose/prune-backups.py's question — it deletes them too, on
  # the retention path, and a rule written in both places drifts on one side. `*.bak-*` was the
  # match here, which also claims a `notes.bak-old` the user saved by hand; these sit in
  # directories we share with them and with other tools, so the name must carry the ownership.
  if [ -f "$REPO/compose/prune-backups.py" ]; then
    python3 "$REPO/compose/prune-backups.py" --list-owned \
      --claude-dir "$CLAUDE_DIR" --codex-dir "$CODEX_DIR" >"$list" 2>/dev/null || : >"$list"
  else
    log "note: compose/prune-backups.py is absent, so loose backup copies are left where they are"
  fi
  # Staged UNDER their absolute path, the way deploy_file backs up to "$BACKUP_DIR$dst".
  # Flattening them into one directory let two same-named copies from the two host trees
  # collide, and the loser was then deleted with nothing in the archive to restore it from.
  # Only what verifiably reached the stage may be deleted later. Every failure mode here is
  # silent — a full temp filesystem, an unreadable source, a directory that cannot be created —
  # and purging from the ORIGINAL list removed files the archive does not contain. Size equality
  # rather than cp's exit status alone, because the question is whether the archive can restore
  # it, not whether the copy was attempted.
  staged="$(mktemp)" || { rm -f "$list"; rm -rf "$stage"
                          log "warning: no temp file; leaving state in place"; return 0; }
  skipped=0
  while IFS= read -r -d '' rel; do
    if mkdir -p "$(dirname "$stage/loose$rel")" 2>/dev/null \
       && cp "$rel" "$stage/loose$rel" 2>/dev/null \
       && [ "$(wc -c <"$rel" 2>/dev/null)" = "$(wc -c <"$stage/loose$rel" 2>/dev/null)" ]; then
      printf '%s\0' "$rel" >> "$staged"
    else
      skipped=$((skipped + 1))
      rm -f "$stage/loose$rel" 2>/dev/null   # a partial copy must not look archived
      log "warning: could not stage $rel — leaving it in place"
    fi
  done <"$list"
  if tar czf "$out" -C "$stage" . 2>/dev/null && [ -s "$out" ]; then
    # Only here, with the archive written and non-empty, is removing the originals recoverable.
    # Deleting them before the tar meant a failed archive took the backups with it — while the
    # warning below told the operator they had been left in place.
    while IFS= read -r -d '' rel; do rm -f "$rel" 2>/dev/null; done <"$staged"
    rm -f "$list" "$staged"
    rm -rf "$stage"
    # The state dir holds the manifest, and the manifest is the only record of what is still
    # deployed. When cmd_uninstall left a file behind because it could not be backed up,
    # purging that record here would strand the file unowned — so the same rule that keeps
    # the file keeps the thing that names it. Everything else goes either way.
    if [ "${UNBACKED:-0}" -eq 0 ]; then
      rm -rf "$STATE_DIR"
    else
      # The dir survives for the manifest's sake; the shell-shadow evidence is not that.
      rm -f "$STATE_DIR/shell-shadow.log"
    fi
    rm -rf "$HOME/.cache/agent-launch" \
           "${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch}"
    log ""
    log "Everything removed is in ONE archive:  $out"
    if [ "$skipped" -gt 0 ]; then
      log "Move it somewhere central or delete it. $skipped backup copy(ies) could not be staged,"
      log "so they were LEFT ON DISK rather than deleted with nothing to restore them from."
    elif [ "${UNBACKED:-0}" -gt 0 ]; then
      # Not "nothing of ours is left": cmd_uninstall said the opposite a moment ago, and two
      # lines of the same summary disagreeing is how an operator stops reading either.
      log "Move it somewhere central or delete it. $UNBACKED deployed file(s) and the manifest"
      log "naming them are still on this machine — re-run uninstall once the copy can be made."
    elif [ "${CLEANUP_FAILED:-0}" = 1 ]; then
      # The spans merged into files the user owns are still there — cmd_uninstall says so a
      # few lines below, and this line saying the opposite in the same summary is how an
      # operator learns to read neither.
      log "Move it somewhere central or delete it. What this repo merged into files you own"
      log "could not be removed — see the warning above."
    else
      log "Move it somewhere central or delete it — nothing of ours is left on this machine."
    fi
  else
    rm -f "$list" "$staged"
    rm -rf "$stage"
    log "warning: could not write $out — state, backups and the venv were left in place rather"
    log "         than deleted with no copy. Re-run once the archive path is writable."
  fi
}

cmd_onboard() {
  log "agent-bios onboarding — pick your domain packages (core + infra always install)"
  local names=() line i=1 choice sel="" n picks
  while IFS= read -r line; do names+=("$line"); done \
    < <(python3 -c "import json;print('\n'.join(sorted(json.load(open('$REPO/compose/domains.json'))['domains'])))")
  [ "${#names[@]}" -ge 1 ] || { log "no domains found in compose/domains.json"; exit 1; }
  if [ "$DOMAINS_SET" = 1 ]; then
    # Non-interactive path, per this installer's input contract (stdin is
    # detached at the top of the script): selection arrives as domain names.
    [ "$DOMAINS_ARG" = none ] && DOMAINS_ARG=""
    sel="$DOMAINS_ARG"
  elif ( : </dev/tty ) 2>/dev/null; then
    for line in "${names[@]}"; do info "$i) $line"; i=$((i+1)); done
    printf 'Select by number, comma-separated (empty = core+infra only): '
    read -r choice </dev/tty || choice=""
    if [ -n "$choice" ]; then
      # bash 3.2 + set -u: expanding an EMPTY array errors, so split only
      # when there is input; empty input means core+infra only.
      IFS=',' read -ra picks <<<"$choice"
      for n in "${picks[@]}"; do
        n="${n// /}"; [ -n "$n" ] || continue
        case "$n" in (*[!0-9]*) log "invalid selection: $n"; exit 2 ;; esac
        [ "$n" -ge 1 ] && [ "$n" -le "${#names[@]}" ] || { log "selection out of range: $n"; exit 2; }
        sel="$sel${sel:+,}${names[$((n-1))]}"
      done
    fi
  else
    log "onboard needs a terminal or an explicit selection — run:"
    log "  agent-bios onboard --domains a,b   (or --domains none for core+infra only)"
    exit 2
  fi
  DOMAINS_ARG="$sel"; DOMAINS_SET=1
  log "selection: ${sel:-<core+infra only>}"
  # Subshelled so a failing install can still record its outcome: the launcher's
  # corpus checklist reads `last_apply` from corpus-status.json, and an exit with
  # nothing recorded reads as "nothing happened". cmd_install's shell state stays
  # in the subshell; everything after here uses only top-level globals.
  local apply_rc=0
  # NOT `( cmd_install ) || apply_rc=$?`: a command list that tests the subshell
  # suppresses errexit for everything inside it, so an unguarded failure in
  # cmd_install would run through to a zero return (probed on bash 3.2/5.x).
  # Toggling -e around a STANDALONE subshell keeps errexit live inside while the
  # outer shell survives to record the outcome.
  set +e
  ( set -e; cmd_install )
  apply_rc=$?
  set -e
  if [ "$apply_rc" -ne 0 ]; then
    python3 "$REPO/compose/corpus-state.py" record-apply \
      --requested "$sel" --outcome install_failed >/dev/null 2>&1 || true
    exit "$apply_rc"
  fi
  log ""
  log "Activation canary (proves the bundle loads in a live session)..."
  if [ "$DRY_RUN" = 1 ]; then info "[dry-run] skip canary probe"; return; fi
  local canary_rc=0
  bash "$REPO/compose/canary.sh" || canary_rc=$?
  if [ "$canary_rc" -ne 0 ]; then
    # rc=1 is a real probe that answered "not loading"; rc=3 is "could not
    # probe" (no CLI/auth). Both leave the apply unproven, so both record as
    # canary_failed — the tail carries which, so the panel's loud line does
    # not send the operator to debug imports over an auth problem.
    python3 "$REPO/compose/corpus-state.py" record-apply \
      --requested "$sel" --outcome canary_failed \
      --error-tail "canary exit $canary_rc$([ "$canary_rc" = 3 ] && printf ' (could not probe)')" \
      >/dev/null 2>&1 || true
    log "ONBOARDING INCOMPLETE: the bundle is installed but not loading — fix the cause above and re-run: agent-bios verify"
    exit 1
  fi
  # The SUCCESS record is strict; the two failure records above stay tolerant. The
  # asymmetry is the point: a swallowed failure-record rides a run that is already
  # exiting non-zero and reporting why, while a swallowed success-record is how
  # onboarding prints a completed summary over a status file that never learned the
  # selection was applied. That is the state this whole change exists to remove, so it
  # cannot be the one still guarded by `|| true`.
  record_log="$(mktemp -t corpus-record-apply)"
  if ! python3 "$REPO/compose/corpus-state.py" record-apply \
       --requested "$sel" --outcome applied >"$record_log" 2>&1; then
    log "ONBOARDING INCOMPLETE: the corpus applied, but recording that outcome failed —"
    log "the corpus panel would not show this selection as applied. Its own output:"
    sed 's/^/    /' "$record_log"
    log "    full output: $record_log"
    exit 1
  fi
  rm -f "$record_log"
  # The prune is authorized by the canary's proof, and cmd_install ran before the canary existed
  # for this bundle rev — so it kept everything. Now that loading is proven, run it for real.
  migrate_learnings
}

# ---- deploy-chain drift ---------------------------------------------------
# A repo edit is inert until it is published AND globally installed AND
# deployed. The middle two are checkable: the installer stamps the package
# version it deployed into the state dir, so a stamp older than the package now
# running means someone updated the package and never re-deployed. Reading the
# registry cannot see this, which is why it went unnoticed three times.
json_field() {  # $1=file $2=key
  [ -f "$1" ] || return 1
  python3 -c 'import json,sys
try:
    v=json.load(open(sys.argv[1])).get(sys.argv[2])
except Exception:
    sys.exit(1)
sys.exit(0) if v is None else print(v)' "$1" "$2" 2>/dev/null
}

deployed_version() { json_field "$STATE_DIR/version.json" version; }
source_version()   { json_field "$REPO/package.json" version; }

json_true() {  # exit 0 iff $2 in $1 is JSON true — json.dump writes '"k": true'
  # with a space, so byte-matching a compact spelling read the real writer's
  # output as false forever.
  [ -f "$1" ] || return 1
  python3 -c 'import json,sys
try:
    v=json.load(open(sys.argv[1])).get(sys.argv[2])
except Exception:
    sys.exit(1)
sys.exit(0 if v is True else 1)' "$1" "$2" 2>/dev/null
}

current_commit() {  # the CURRENT side's commit: git HEAD in a clone, the stamp in a package
  # A clone's provenance is its live HEAD — a provenance.json on its disk is a
  # failed pack's residue, and reading it once let a stale label A match a
  # checkout sitting at B.
  if [ -e "$REPO/.git" ]; then
    git -C "$REPO" rev-parse HEAD 2>/dev/null || true
  else
    json_field "$REPO/provenance.json" commit 2>/dev/null || true
  fi
}

current_dirty() {  # exit 0 iff the current side is a dirty-stamped PACKAGE artifact
  [ ! -e "$REPO/.git" ] && json_true "$REPO/provenance.json" dirty
}

drift_state() {  # prints: match | drift | unknown
  local d s dc sc
  d="$(deployed_version)" || { echo unknown; return; }
  s="$(source_version)"   || { echo unknown; return; }
  [ -n "$d" ] && [ -n "$s" ] || { echo unknown; return; }
  [ "$d" = "$s" ] || { echo drift; return; }
  # Same VERSION is not same SOURCE: two locally packed tarballs keep one
  # version across different commits (npm pack is an accommodated flow), and
  # the commit was persisted into version.json exactly so this comparison
  # could read it. Judged only when both sides carry one — a clone deploy
  # stamps no commit, and half a comparison is none.
  dc="$(json_field "$STATE_DIR/version.json" commit 2>/dev/null || true)"
  sc="$(current_commit)"
  # Dirt is judged BEFORE the commit comparison: a dirty artifact's bytes are
  # described by no commit, so differing commit labels prove nothing about
  # differing payloads — unknown, not drift, or npm-layout verify fails on a
  # mismatch nobody proved.
  if json_true "$STATE_DIR/version.json" dirty || current_dirty; then
    echo unknown; return
  fi
  if [ -n "$dc" ] && [ -n "$sc" ] && [ "$dc" != "$sc" ]; then
    echo drift; return
  fi
  # UNPROVABLE is not drift: an unbound side (npm layout without a commit — a
  # lifecycle-disabled pack, or the hook's materialized tree) and a DIRTY side
  # (bytes no commit describes; parsed via json_true, never byte-matched,
  # because json.dump's spacing defeated the compact grep) both make the
  # correspondence unprovable. Drift is a PROVEN mismatch and makes verify
  # fail; branding the unprovable as drift made D-20260809-7954fd's accepted install path
  # fail its own verification. Clone deployments stay version-compared — git
  # itself is their live provenance, and they persist no commit by design.
  if [ "$(json_field "$STATE_DIR/version.json" source 2>/dev/null || true)" = "package" ] \
     && [ -z "$dc" ]; then
    echo unknown; return
  fi
  if [ ! -e "$REPO/.git" ] && [ -z "$sc" ]; then
    echo unknown; return
  fi
  echo match
}

drift_detail() {  # one line naming WHAT drifted: versions, or commits behind one version
  local d s dc sc
  d="$(deployed_version)"; s="$(source_version)"
  dc="$(json_field "$STATE_DIR/version.json" commit 2>/dev/null || true)"
  sc="$(current_commit)"
  if [ "$d" = "$s" ] && { json_true "$STATE_DIR/version.json" dirty || current_dirty; }; then
    printf 'a DIRTY-packed artifact is involved — its bytes are described by no commit; a clean-pack redeploy restores a provable match'
  elif [ "$d" = "$s" ] && [ -n "$dc" ] && [ -n "$sc" ] && [ "$dc" != "$sc" ]; then
    printf 'deployed commit %s but this source is at %s (both version %s)' "$dc" "$sc" "$s"
  elif [ "$(json_field "$STATE_DIR/version.json" source 2>/dev/null || true)" = "package" ] \
       && [ -z "$dc" ]; then
    printf 'the deployed artifact is UNBOUND (packed with lifecycle scripts disabled) — its bytes are proven by no commit; a bound redeploy restores a provable match'
  elif [ ! -e "$REPO/.git" ] && [ -z "$sc" ]; then
    printf 'this package is UNBOUND (no provenance) — its bytes are proven by no commit'
  else
    printf 'deployed %s but this package is %s' "$d" "$s"
  fi
}

cmd_status() {
  local version p
  if [ -e "$REPO/.git" ]; then
    version="$(git -C "$REPO" describe --tags --always --dirty 2>/dev/null || git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
    log "agent-bios  (git clone: $version)"
  elif [ -f "$REPO/package.json" ]; then
    version="$(node -e "try{process.stdout.write(require('$REPO/package.json').version)}catch(e){process.stdout.write('?')}" 2>/dev/null || echo '?')"
    log "agent-bios  (npm package: $version)"
    if [ -f "$REPO/provenance.json" ]; then
      local built_from
      # Tolerated, never trusted: a malformed stamp used to kill status via
      # set -e mid-output, and a well-formed one with no commit passed in
      # silence — both are UNBOUND states, not absences of the question.
      built_from="$(json_field "$REPO/provenance.json" commit 2>/dev/null || true)"
      if [ -n "$built_from" ]; then
        info "built from commit ${built_from}$(
          grep -q '"dirty":true' "$REPO/provenance.json" && printf ' (DIRTY tree at pack time)')"
      else
        info "UNBOUND  provenance.json is unreadable or names no commit — this artifact is not usably bound"
      fi
    else
      # The absence is the finding: D-20260809-7954fd accepts lifecycle-disabled packs as
      # residual BECAUSE this line makes an unbound artifact visible — a silent
      # skip here would unmake that decision's premise.
      info "UNBOUND  no provenance stamp — packed with lifecycle scripts disabled, or a pre-provenance release; this artifact names no commit"
    fi
  else
    log "agent-bios"
  fi
  log "  source:  $REPO"
  case "$(drift_state)" in
    match)   info "deployed version $(deployed_version) (matches this package)" ;;
    drift)   log  "DRIFT    $(drift_detail) — run: agent-bios install" ;;
    unknown) if [ -f "$STATE_DIR/version.json" ]; then
               info "correspondence unprovable: $(drift_detail)"
             else
               info "deployed version unknown (no state marker yet)"
             fi ;;
  esac
  for p in "$CLAUDE_DIR/CLAUDE.md" "$CODEX_DIR/AGENTS.md" "$BIN_DIR/agent-launch" \
           "$LAUNCH_DIR/profiles.toml" "$LAUNCH_DIR/shell.zsh"; do
    if [ -e "$p" ]; then info "present  $p"; else info "MISSING  $p"; fi
  done
  zsh_found="$(zsh_hook_locations)"
  if [ -z "$zsh_found" ]; then
    info "zsh hook absent"
  elif printf '%s\n' "$zsh_found" | grep -qxF "$ZSHRC"; then
    info "zsh hook present  $(printf '%s' "$zsh_found" | tr '\n' ' ')"
  else
    # Present and working, but somewhere this installer will neither update nor remove.
    info "zsh hook present  $(printf '%s' "$zsh_found" | tr '\n' ' ')  (unmanaged location: not $ZSHRC)"
  fi
  shell_shadow_summary
}

# The interception in launch/agent-launch.zsh reasserts `claude`/`codex` at preexec when a
# tool redefined them after the rc files (cmux does, on its first precmd) and appends one
# line per shadowed host per shell to $STATE_DIR/shell-shadow.log. That log is the only
# evidence of shadowing status/verify can read: a child shell cannot reproduce the
# terminal's own bootstrap, so a canary run from here would report PASS while the live
# shell is shadowed — which is why there is none.
shell_shadow_summary() {
  local f="$STATE_DIR/shell-shadow.log" n last
  # A dir that cannot be written records nothing, and "nothing" must not read as "clean" —
  # so this branch is exclusive: no "no shadowing observed" beside it.
  if [ -L "$f" ] || { [ -e "$f" ] && [ ! -f "$f" ]; }; then
    info "shell interception: evidence log is not a regular file ($f) — nothing is recorded there, so absence here is not evidence"
  elif { [ -d "$STATE_DIR" ] && [ ! -w "$STATE_DIR" ]; } || { [ -e "$f" ] && [ ! -w "$f" ]; }; then
    info "shell interception: evidence log not writable ($f) — a shadowing cannot be recorded, so absence here is not evidence"
  elif [ -s "$f" ]; then
    # One line is one host's FIRST observation in one shell, never a count of repairs: a
    # tool that redefines on every prompt is repaired on every command and logged once.
    n=$(wc -l <"$f" | tr -d ' ')
    # Control bytes are stripped again on display: the log is written by a shell the
    # user does not fully own, and a terminal-control sequence in a "foreign body" field
    # could repaint this very line.
    last=$(tail -n 1 "$f" | tr -d '\000-\010\013-\037\177')
    info "shell interception: shadowing observed $n time(s) (first observation per host per shell), last $(printf '%s' "$last" | cut -f1) — $(printf '%s' "$last" | cut -f2) was shadowed by: $(printf '%s' "$last" | cut -f4-)"
  else
    info "shell interception: no shadowing observed"
  fi
}

# The update check is a READ of a public version number: it sends the package name
# and nothing derived from this machine, which is the same class as provision-venv's
# PyPI fetch and the onboard model probe — see ENDPOINTS.md "Zero egress by default",
# whose claim is scoped to DATA egress. It delegates to `npm view` rather than naming
# a registry, so a private registry, a proxy, and the user's auth all keep working and
# no shipped file carries a URL (gates/check-endpoints.py forbids that outright).
#
# `checked_at` is written even when the lookup FAILS. An offline machine that recorded
# nothing would retry on every launch, which is the opposite of once a day.
refresh_update_cache() {
  if [ "${AGENT_BIOS_UPDATE_CHECK:-1}" = "0" ]; then
    log "update check disabled (AGENT_BIOS_UPDATE_CHECK=0)"
    return 0
  fi
  local name latest now out
  name="$(json_field "$REPO/package.json" name)" || return 1
  [ -n "$name" ] || return 1
  now="$(date +%s)"
  latest=""
  if command -v npm >/dev/null 2>&1; then
    # `|| latest=""` is not defensive noise: this file runs under `set -euo pipefail`,
    # so an npm that exits non-zero (offline, firewalled, private registry down) makes
    # the PIPELINE fail and `set -e` abort the function before it can record the
    # attempt — turning every offline launch into a retry and `update --check` into
    # exit 1. Caught by I16's failing-registry stub, not by review.
    latest="$(npm view "$name" version 2>/dev/null | tr -d '[:space:]')" || latest=""
  fi
  mkdir -p "$STATE_DIR" || return 1
  out="$STATE_DIR/update-check.json"
  # Atomic: a half-written cache read by the launcher is a crash in the TUI.
  python3 "$REPO/compose/write-update-cache.py" "$out" "$now" "$latest" "$(source_version)" || return 1
  if [ -n "$latest" ]; then
    log "update check: latest $latest (installed $(source_version))"
  else
    log "update check: could not reach the registry; recorded the attempt"
  fi
}

cmd_update() {
  if [ "${UPDATE_CHECK_ONLY:-0}" = 1 ]; then
    refresh_update_cache
    return $?
  fi
  if [ -e "$REPO/.git" ]; then
    log "Updating from git..."
    run git -C "$REPO" pull --ff-only
    if [ "${AGENT_BIOS_LEGACY_INSTALL:-0}" = 1 ]; then
      cmd_install
    else
      python3 "$REPO/compose/corpus_install.py" --repo "$REPO" install
    fi
  else
    log "Installed as an npm package. Update with:"
    log "  npm install -g agent-bios@latest && agent-bios install"
    log "Then confirm what actually landed — right after a publish the cached"
    log "packument can serve the PREVIOUS version at exit 0:"
    log "  agent-bios status   # must show the version you expected, and no DRIFT"
  fi
}

usage() {
  cat <<'EOF'
agent-bios — manage private corpus content for explicitly activated sessions.

  agent-bios install     store a private runtime and corpus baseline
  agent-bios onboard     select domains for future activated sessions
  agent-bios corpus      open Corpus Studio; list/show/plan/apply also work non-TTY
  agent-bios understand  list corpus learning bundles; --help shows session/discovery commands
  agent-bios shell       show the optional zsh connection status
  agent-bios shell restore   make bare claude/codex open the launcher TUI
  agent-bios shell remove    return bare claude/codex to their native CLI
  agent-bios migrate     preview legacy global cleanup; --apply --yes applies it
  agent-bios reset       preview reset; --apply --yes --expected-revision REV applies it
  agent-bios verify      verify the private runtime, baseline, and managed files
  agent-bios learn       submit a session learning (reads the JSON record on
                         stdin; this is what the learn! flow calls, and it
                         works from any directory, unlike a repo-relative path)
  agent-bios status      show what is installed and where
  agent-bios cost        the session cost / context meter (session-cost.py), from any
                         directory: agent-bios cost [--context [--budget N]] <transcript>
  agent-bios update      git pull + reinstall (clone), or print the npm update line
  agent-bios update --check   ask the registry for the latest version and cache it
                      for the launcher's badge; sends the package name and nothing
                      else, runs at most daily, AGENT_BIOS_UPDATE_CHECK=0 disables it
  agent-bios uninstall   remove the private runtime; preserve personal and session data
  agent-bios help

Launcher (run in an interactive terminal):
  agent-launch claude    open the Claude launch TUI
  agent-launch codex     open the Codex launch TUI
  agent-launch --corpus  open Corpus Studio directly
  agent-launch --understand BUNDLE claude   start a corpus understanding session
  agent-launch --preset balanced claude   launch with a named preset

Shell connection is opt-in and changes only zsh startup wiring, not global
AGENTS.md/CLAUDE.md. Restore/remove it from the TUI's Shell connection menu or
the commands above. After restoring, open a new terminal or reload .zshrc.

Flags: --dry-run       print actions without changing anything
       --domains a,b  assemble ONLY the named domain packages (plus core+infra);
                      with onboard, 'none' means core+infra only. The selection
                      persists in the state dir and later installs/updates reuse
                      it. Default (no flag, no saved selection) selects every
                      domain — one install shape, "full" is just everything
                      selected.
       --with a,b     also install the named optional dependencies (install only).
                      Without it, install offers each missing one when the terminal
                      is interactive, and otherwise just prints its install line.
                      Missing ones are not fatal — they only degrade the review
                      routes that need them.
Env:   CLAUDE_CONFIG_DIR, CODEX_HOME, AGENT_LAUNCH_VENV, ZDOTDIR
EOF
  # DERIVED, not typed: the hardcoded pair went stale the moment a capability was renamed,
  # and the name it still advertised selected a different capability than the one that
  # carries the install line.
  local known; known=$(capability_table 2>/dev/null | cut -f1 | tr '\n' ' ')
  [ -n "$known" ] && printf '       --with names: %s\n' "${known% }"

  # Recovery exists in both modes at different granularity, and naming the wrong one is worse
  # than naming none: a clone can roll the corpus back to a registered mining window, while an
  # npm install has no git history to read and rolls the whole package back by version instead.
  # Derived from which install this is, for the same reason --with names is.
  if [ -e "$REPO/.git" ]; then
    printf '\nRecover: python3 %s/compose/corpus-state.py list, then rollback --version V\n' "$REPO"
  else
    printf '\nRecover: npm install -g agent-bios@<older-version> && agent-bios install\n'
  fi
}

# ---- dispatch ------------------------------------------------------------
CMD="${1:-help}"
if [ $# -gt 0 ]; then shift; fi

# Private installation is the new user path. The explicit legacy flag exists only
# while maintained install fixtures and pre-migration environments exercise the old
# writer. No private operation falls through to a global writer.
if [ "$CMD" = "corpus" ]; then
  exec python3 "$REPO/compose/corpus.py" --repo "$REPO" "$@" <&3
fi
if [ "$CMD" = "shell" ]; then
  exec python3 "$REPO/launch/shell_integration.py" "$@" <&3
fi
if [ "$CMD" = "understand" ]; then
  exec python3 "$REPO/compose/corpus_understand.py" --repo "$REPO" "$@" <&3
fi
if [ "${AGENT_BIOS_LEGACY_INSTALL:-0}" != 1 ]; then
  case "$CMD" in
    install|onboard|verify|status|uninstall|migrate|reset)
      exec python3 "$REPO/compose/corpus_install.py" --repo "$REPO" "$CMD" "$@" <&3
      ;;
  esac
fi

# `learn` forwards its arguments and stdin straight to the collector, so it must
# bypass the flag parser below (which rejects anything it does not know). This
# subcommand is the only PATH-reachable entry to capture: the corpus guide used
# to invoke learn/collect-learning.py relative to the cwd, which works from a
# clone and silently fails for every other install.
if [ "$CMD" = "learn" ]; then
  collector="$REPO/learn/collect-learning.py"
  [ -f "$collector" ] || { log "learn: collector missing at $collector"; exit 1; }
  exec python3 "$collector" "$@" <&3
fi
# `cost` is the same shape for the same reason: the guides tell an installed user to
# measure with session-cost.py, and on a packaged install that file lives inside the
# npm package where no PATH reaches it — the instruction resolved to "command not
# found" everywhere but a clone. Its arguments (--context, --budget, transcript
# paths) are the meter's, so it bypasses the flag parser below.
if [ "$CMD" = "cost" ]; then
  meter="$REPO/session-cost.py"
  [ -f "$meter" ] || { log "cost: meter missing at $meter"; exit 1; }
  exec python3 "$meter" "$@" <&3
fi

WITH=""
DOMAINS_ARG=""
DOMAINS_SET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --check) UPDATE_CHECK_ONLY=1 ;;
    --with) shift; WITH="${1:-}"; [ -n "$WITH" ] || { log "--with needs a comma-separated capability list"; exit 2; } ;;
    --with=*) WITH="${1#--with=}"; [ -n "$WITH" ] || { log "--with needs a comma-separated capability list"; exit 2; } ;;
    --domains) shift; DOMAINS_ARG="${1:-}"; DOMAINS_SET=1; [ -n "$DOMAINS_ARG" ] || { log "--domains needs a comma-separated domain list (use onboard for core-only)"; exit 2; } ;;
    --domains=*) DOMAINS_ARG="${1#--domains=}"; DOMAINS_SET=1; [ -n "$DOMAINS_ARG" ] || { log "--domains needs a comma-separated domain list (use onboard for core-only)"; exit 2; } ;;
    *) log "unknown flag: $1"; exit 2 ;;
  esac
  shift
done

case "$CMD" in
  install)   cmd_install ;;
  onboard)   cmd_onboard ;;
  update)    cmd_update ;;
  uninstall) cmd_uninstall ;;
  verify)    if cmd_verify; then log "VERIFY OK"; else log "VERIFY FAILED"; exit 1; fi ;;
  status)    cmd_status ;;
  help|-h|--help) usage ;;
  *) log "unknown command: $CMD"; usage; exit 2 ;;
esac
