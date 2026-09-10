#!/usr/bin/env bash
# Publication provenance: bind the npm tarball to the commit it was built from,
# and refuse to publish a tree no commit describes.
#
#   --stamp       (npm prepack)         write provenance.json: commit, committedAt, dirty
#   --guard       (npm prepublishOnly)  refuse a dirty tree or a HEAD no remote ref holds
#   --self-test   prove both directions in a scratch clone
#
# v0.9.9 shipped from an uncommitted tree and nothing recorded that: the registry
# holds a tarball no commit describes. The stamp makes every tarball name its
# commit, and it REFUSES a dirty tree by default — the two-step release form
# (`npm pack`, then `npm publish <tgz>`) runs no lifecycle at all (verified
# against npm 11.4.2), so the pack step is the only gate that survives into it,
# and a stamped-but-dirty tarball there would recreate the 0.9.9 shape. A test
# pack from mid-work state stays possible behind AGENT_BIOS_PACK_DIRTY=1, which
# still stamps dirty:true honestly. npm's postpack removes the stamp after the
# tarball is sealed, so a NORMAL pack leaves no residue for a later
# script-disabled pack to ship as a stale, WRONG binding — worse than the
# accepted missing-stamp residual, because it looks bound. (The residue window is npm's own
# sequencing: a pack that FAILS after prepack — a missing --pack-destination
# reproduces it — leaves that run's stamp, and nothing of ours runs on the
# failure path. Turning that into a false binding takes a second deliberate
# step, packing with --ignore-scripts instead of letting any scripted pack
# overwrite the residue; a loudly failed pack followed by a script-disabled
# pack is a two-fault chain outside the single-accident threat model, and the
# healing action is any scripted pack.) The guard makes the directory-form
# `npm publish` additionally refuse a HEAD no remote ref holds — after a
# fetch --prune, because locally cached refs outlive deleted and force-pushed
# branches and would vouch for a commit nobody can fetch. Stated residuals: on
# the tgz path nothing re-checks reachability at publish time (the binding is a
# real commit, push order is the operator's); and an operator who disables the
# lifecycle outright (ignore-scripts config, --ignore-scripts) has told npm not
# to run this gate at all — npm offers no non-disableable hook, and a release
# wrapper would be one more voluntary surface at the same trust level, so that
# path is accepted by decision rather than chased. And permission bits beyond
# git's two file modes (0700 where HEAD says 100755, umask variants) have no
# HEAD truth to compare against — the stamp certifies equality over what the
# commit CAN describe, and a gate-invented canonical mode policy was declined
# by decision (D-20260809-eeb459): its canon would have this gate as its only author and
# an open ladder of successors (setuid, ACLs) behind it.
# Operates on the CURRENT directory (npm runs lifecycle scripts at the package
# root), never on this file's own location, so the self-test can point it at a
# scratch clone.
set -u

die() { printf '%s\n' "$*" >&2; exit 1; }

repo_guard() {
  git rev-parse --git-dir >/dev/null 2>&1 \
    || die "check-publish: $PWD is not a git repository — provenance needs one"
}

refuse_hidden_flags() {   # $1: "PACK" | "PUBLISH"
  # assume-unchanged lowercases the ls-files tag letter; skip-worktree tags S
  # (s when both). Either makes `git status` blind to real modifications, so a
  # clean verdict over a flagged index is no verdict — the closed set of ways
  # git can be told to lie to status, refused rather than seen through.
  local lsout flagged
  lsout="$(git ls-files -v 2>/dev/null)" \
    || die "$1 BLOCKED: git ls-files failed — the index cannot be judged"
  flagged="$(printf '%s\n' "$lsout" | grep -E '^([a-z]|S) ' | cut -c3- || true)"
  [ -z "$flagged" ] \
    || die "$1 BLOCKED: index flags hide changes from status (assume-unchanged/skip-worktree): $(printf '%s' "$flagged" | tr '\n' ' ')— clear them (git update-index --no-assume-unchanged / --no-skip-worktree) first"
}

verify_payload_in_head() {   # $1: "PACK" | "PUBLISH"
  # The packlist is what npm will actually ship — enumerated with
  # --ignore-scripts, which also keeps this from re-entering prepack — and
  # every packed path except the stamp itself must BE IN HEAD, byte for byte.
  # Presence closes the ignore-side holes (.git/info/exclude, global excludes,
  # whatever config comes next); the byte comparison closes the filter side,
  # which falsified the earlier "tracked needs no hash pass" claim: git status
  # judges through clean/smudge filters, so core.autocrlf reports a clean tree
  # while npm packs the smudged worktree bytes — a CRLF shebang shipped that
  # way does not execute. --no-filters hashes what npm will actually read.
  local plist p hmode
  plist="$(npm pack --dry-run --json --ignore-scripts 2>/dev/null \
           | python3 -c 'import json,sys; d=json.load(sys.stdin); pkg=d[0] if isinstance(d,list) else next(iter(d.values())); [print(f["path"]) for f in pkg["files"]]' 2>/dev/null)" \
    || die "$1 BLOCKED: cannot enumerate the npm packlist to compare against HEAD"
  [ -n "$plist" ] || die "$1 BLOCKED: the npm packlist came back empty — nothing to verify is not verified"
  local want have
  while IFS= read -r p; do
    [ "$p" = provenance.json ] && continue
    want="$(git rev-parse -q --verify "HEAD:$p" 2>/dev/null)" \
      || die "$1 BLOCKED: the tarball would ship $p, which HEAD does not contain — locally ignored or excluded files ride npm packs invisibly"
    have="$(git hash-object --no-filters -- "$p" 2>/dev/null)" \
      || die "$1 BLOCKED: cannot hash $p to compare against HEAD"
    [ "$want" = "$have" ] \
      || die "$1 BLOCKED: $p on disk differs byte-wise from its HEAD blob — checkout filters (e.g. core.autocrlf) or attributes would ship bytes the stamped commit does not describe"
    # Bytes and MODE are the two properties tar carries from the worktree, and
    # core.filemode=false hides mode drift from status while the byte hash
    # still matches — a shipped executable packed 0644 does not run.
    hmode="$(git ls-tree HEAD -- "$p" 2>/dev/null | awk '{print $1; exit}')"
    case "$hmode" in
      100755) [ -x "$p" ] \
        || die "$1 BLOCKED: $p is executable in HEAD but not on disk — the tarball would ship a non-executable copy (core.filemode=false hides this from status)" ;;
      100644) [ ! -x "$p" ] \
        || die "$1 BLOCKED: $p is not executable in HEAD but is on disk — the tarball would ship a mode the stamped commit does not describe" ;;
    esac
  done <<PLIST
$plist
PLIST
  # The OTHER direction: nothing HEAD ships may be missing from the packlist.
  # A .npmignore in a shipped subtree — even one hidden from git by local
  # excludes — SUBTRACTS committed payload silently, and the shipped global
  # then routes readers to guides the tarball does not carry. Expected is
  # derived from files[] expanded against HEAD plus npm's auto-includes, so
  # the comparison has no second hand-kept list to rot.
  # The difference is taken in ONE language on purpose. It used to be `comm -23`
  # over a Python-sorted expected list and a shell-sorted packlist, and comm
  # assumes both sides collate alike: under LANG=ko_KR.UTF-8 (or en_US — any
  # locale that folds case) `sort` puts claude/agents/ before claude/CLAUDE.md
  # while Python's sorted() puts it after, comm desynchronised, and the guard
  # reported 74 committed files as "omitted" from a packlist that carried every
  # one of them. A false BLOCK is the loud direction; the same desync can also
  # walk past a real omission, which is the quiet one.
  # The packlist rides an environment variable: a heredoc is the script's
  # stdin, so a pipe into `python3 -` never reaches sys.stdin — the first cut of
  # this reported EVERY committed file as omitted, which is at least loud.
  local missing_p
  missing_p="$(AGENT_BIOS_PACKLIST="$plist" python3 - <<'PYEOF'
import json, os, subprocess, sys
files = json.load(open("package.json")).get("files", [])
expected = set()
for e in files:
    e = e.strip("/")
    if e == "provenance.json":       # pack-generated; absent at dry-run time
        continue
    ls = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "--", e],
                        capture_output=True, text=True)
    expected.update(x for x in ls.stdout.splitlines() if x)
for auto in ("package.json", "README.md", "LICENSE"):
    ls = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", "--", auto],
                        capture_output=True, text=True)
    expected.update(x for x in ls.stdout.splitlines() if x)
if not expected:
    print("EMPTY-EXPECTED"); sys.exit(0)
packed = {line.strip() for line in os.environ.get("AGENT_BIOS_PACKLIST", "").splitlines() if line.strip()}
print("\n".join(sorted(expected - packed)[:5]))
PYEOF
)" || die "$1 BLOCKED: cannot derive the expected payload from HEAD"
  [ "$missing_p" != "EMPTY-EXPECTED" ] || die "$1 BLOCKED: the expected payload derived from HEAD is empty — nothing to require is not a requirement"
  [ -z "$missing_p" ] \
    || die "$1 BLOCKED: HEAD ships $(printf '%s' "$missing_p" | tr '\n' ' ')— but the npm packlist omits it; a .npmignore or npm config is subtracting committed payload"
}

cmd_stamp() {
  repo_guard
  refuse_hidden_flags "PACK"
  local commit committed_at status_out dirty=false
  commit="$(git rev-parse HEAD)" || die "check-publish: no HEAD to stamp"
  committed_at="$(git show -s --format=%cI HEAD)"
  # Fail CLOSED: an inspection that errors (corrupt index, unreadable worktree)
  # must not read as "clean" — an empty substitution from a failed command is
  # exactly how a modified tree would stamp itself unbound.
  # --untracked-files=all explicitly: status.showUntrackedFiles=no is a CONFIG
  # that hides untracked payload from status while npm pack ships it — the
  # tarball would not match the stamped commit, with no index flag set at all.
  status_out="$(git status --porcelain --untracked-files=all 2>/dev/null)" \
    || die "PACK BLOCKED: git status failed — the tree cannot be judged, so it cannot be stamped clean"
  [ -n "$status_out" ] && dirty=true
  if [ "$dirty" = true ] && [ "${AGENT_BIOS_PACK_DIRTY:-}" != 1 ]; then
    printf 'PACK BLOCKED: working tree is dirty — the tgz publish path runs no\n' >&2
    printf 'lifecycle, so this tarball could ship unbound; commit first, or for a\n' >&2
    printf 'local test pack set AGENT_BIOS_PACK_DIRTY=1 (stamps dirty:true).\n' >&2
    printf '%s\n' "$status_out" | head -10 >&2
    exit 1
  fi
  # The write itself must be judged: under set -u a failed redirection continues
  # execution, and the final status line would hand npm a green prepack over a
  # tarball with no provenance in it. A SYMLINK squatter is worse — the write
  # succeeds through it, and npm never packs a symlink, so the tarball ships
  # unbound behind a green exit. Clear any squatter first (a directory refuses
  # the clear), and require a regular file after the write.
  # Payload-vs-HEAD runs on the publishable path only: an opted-in dirty test
  # pack already declares itself unbound via dirty:true.
  [ "$dirty" = true ] || verify_payload_in_head "PACK"
  if [ -e provenance.json ] || [ -L provenance.json ]; then
    rm -f provenance.json 2>/dev/null \
      || die "PACK BLOCKED: cannot clear the provenance.json path — the tarball would ship unbound"
  fi
  printf '{"commit":"%s","committedAt":"%s","dirty":%s}\n' \
    "$commit" "$committed_at" "$dirty" > provenance.json \
    || die "PACK BLOCKED: cannot write provenance.json — the tarball would ship unbound"
  [ -f provenance.json ] && [ ! -L provenance.json ] \
    || die "PACK BLOCKED: provenance.json is not a regular file after the write — npm would not pack it"
  printf 'provenance: %s (dirty=%s)\n' "$commit" "$dirty"
}

cmd_guard() {
  repo_guard
  refuse_hidden_flags "PUBLISH"
  local status_out
  status_out="$(git status --porcelain --untracked-files=all 2>/dev/null)" \
    || die "PUBLISH BLOCKED: git status failed — the tree cannot be judged, so it cannot be proven clean"
  if [ -n "$status_out" ]; then
    printf 'PUBLISH BLOCKED: working tree is dirty — the tarball would match no commit:\n' >&2
    printf '%s\n' "$status_out" | head -10 >&2
    exit 1
  fi
  verify_payload_in_head "PUBLISH"
  # Containment must be judged against the LIVE remote: locally cached
  # remote-tracking refs outlive deleted and force-pushed branches, and a stale
  # one would vouch for a commit nobody can fetch. Publish needs the network
  # anyway, so an unreachable remote fails closed here.
  # The refspec is explicit: a single-branch clone configures a NARROW
  # remote.origin.fetch, and --prune only judges refs the refspec maps — a
  # stale origin/* ref outside it would survive the prune and vouch anyway.
  # Mapping all of refs/heads/* makes the prune judge the whole namespace
  # against what origin actually advertises, whatever the clone's config says.
  git fetch --quiet --prune origin '+refs/heads/*:refs/remotes/origin/*' 2>/dev/null \
    || die "PUBLISH BLOCKED: cannot refresh origin to verify the stamped commit is fetchable — publish needs that network anyway"
  if ! git branch -r --contains HEAD --list 'origin/*' 2>/dev/null | grep -q .; then
    # Second chance: a release checkout is detached at a pushed TAG, which no
    # origin/* branch holds — refusing it blocks the tag-based publish flow.
    # Tags are fetched WITHOUT prune (local tags are user state, not cache),
    # and containment is judged against what origin actually advertises.
    git fetch --quiet origin --tags 2>/dev/null || true
    tag_hold=""
    while read -r sha ref; do
      [ -n "$sha" ] || continue
      if git merge-base --is-ancestor HEAD "$sha" 2>/dev/null; then
        tag_hold="$ref"
        break
      fi
    done <<TAGS
$(git ls-remote --tags origin 2>/dev/null | awk '{print $1, $2}')
TAGS
    [ -n "$tag_hold" ] \
      || die "PUBLISH BLOCKED: HEAD $(git rev-parse --short HEAD) is on no origin branch or advertised tag after fetch --prune — the provenance would name a commit nobody can fetch; push first"
  fi
}

self_test() {
  local self src out rc fails=0
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  tmp="$(mktemp -d)" || die "self-test: no temp dir"   # not local: the EXIT trap outlives this scope
  trap 'rm -rf "$tmp"' EXIT
  # Clone from the GIT DIR, not the worktree: the pre-commit hook runs gates in a
  # materialized index copy with no .git of its own, exporting GIT_DIR at the real
  # repository — and those inherited variables must not leak into the clone, or
  # every git command inside it silently operates on the original.
  src="$(git rev-parse --absolute-git-dir 2>/dev/null)" \
    || die "self-test: not inside a git repository"
  cleangit() { env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE "$@"; }
  in_clone() { (cd "$tmp/clone" && cleangit bash "$self" "$@"); }
  cg() { cleangit git -C "$tmp/clone" "$@"; }
  cleangit git clone -q "$src" "$tmp/clone" \
    || die "self-test: could not clone the repo"
  # The caller's HEAD may be detached and unreferenced (this repo commits from
  # worktrees), and the controls must not inherit that: a positive control that
  # depends on the CALLER being publishable blocks commits for a publication
  # condition unrelated to them. Seat the clone on a commit an origin ref
  # advertises, so "clean and reachable" holds by construction.
  # Seat choice carries the TREE the controls run under (its .gitignore is what
  # keeps the stamp out of status), so prefer a branch holding the clone's
  # initial HEAD — the tree under test — and fall back to any real branch.
  # Never origin/HEAD: it is a symref, and the narrow-refspec control would
  # name a branch origin does not have, failing on fetch instead of on the
  # shelter it exists to judge.
  seat="$(cg for-each-ref --format='%(refname)' --contains HEAD refs/remotes/origin 2>/dev/null | grep -v '/HEAD$' | head -1)"
  [ -n "$seat" ] || seat="$(cg for-each-ref --format='%(refname)' refs/remotes/origin | grep -v '/HEAD$' | head -1)"
  [ -n "$seat" ] || die "self-test: the clone has no origin refs to seat a control on"
  cg checkout -q --detach "$seat" || die "self-test: could not seat the clone on $seat"

  say() { printf 'self-test [%s] %s\n' "$1" "$2"; [ "$1" = FAIL ] && fails=$((fails+1)); return 0; }

  # Positive control first, so a later failure is attributable to its mutation.
  if in_clone --guard >/dev/null 2>&1; then
    say OK "a clean clone with a reachable HEAD passes the guard"
  else
    say FAIL "the guard refused a clean, remote-reachable clone"
  fi

  # The verdict must not depend on the caller's locale. The packlist comparison
  # once ran `comm` over two lists sorted by different collations and refused a
  # clean clone under any case-folding locale. Run the same clean guard under
  # the first such locale the machine has; a machine with none cannot run this
  # control and says so rather than passing over nothing.
  fold_loc=""
  for cand in $(locale -a 2>/dev/null | grep -aE '^(en_US|ko_KR|ja_JP|de_DE)\.UTF-8$'); do
    if [ "$(printf 'B\na\n' | LC_ALL="$cand" sort 2>/dev/null | head -1)" = a ]; then fold_loc="$cand"; break; fi
  done
  if [ -z "$fold_loc" ]; then
    say FAIL "no case-folding locale on this machine — the collation control cannot run, so a locale-dependent verdict would go unnoticed"
  elif (cd "$tmp/clone" && LC_ALL="$fold_loc" cleangit bash "$self" --guard) >/dev/null 2>&1; then
    say OK "the guard's verdict is the same under $fold_loc as under C"
  else
    say FAIL "the guard refused the same clean clone under LC_ALL=$fold_loc — the verdict depends on collation"
  fi
  out="$(in_clone --stamp)" && [ -f "$tmp/clone/provenance.json" ] \
    && grep -q "\"commit\":\"$(cg rev-parse HEAD)\"" "$tmp/clone/provenance.json" \
    && grep -q '"dirty":false' "$tmp/clone/provenance.json" \
    && say OK "the stamp names the clone's own HEAD, clean" \
    || say FAIL "the stamp did not record the clone's HEAD as clean provenance"

  # An unwritable stamp target must fail the pack, not narrate success over a
  # tarball with no provenance in it: squat a directory on the path.
  rm -f "$tmp/clone/provenance.json"
  mkdir "$tmp/clone/provenance.json"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "cannot clear the provenance.json path"; then
    say OK "a directory squatting on the stamp target refuses the pack by name"
  else
    say FAIL "a directory squatting on the stamp target let prepack succeed (rc=$rc)"
  fi
  rmdir "$tmp/clone/provenance.json"

  # A SYMLINK squatter must be replaced, not written through: npm never packs a
  # symlink, so a write-through "succeeds" into an unbound tarball.
  # The target lives OUTSIDE the clone: inside it, the untracked target itself
  # would read as dirt (correctly, per the untracked-files rule) and mask what
  # this control judges.
  echo "target-before" > "$tmp/zz-symlink-target"
  (cd "$tmp/clone" && ln -s "$tmp/zz-symlink-target" provenance.json)
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -eq 0 ] && [ -f "$tmp/clone/provenance.json" ] \
     && [ ! -L "$tmp/clone/provenance.json" ] \
     && grep -q '"commit"' "$tmp/clone/provenance.json" \
     && ! grep -q '"commit"' "$tmp/zz-symlink-target"; then
    say OK "a symlink squatter is replaced by a regular stamp, never written through"
  else
    say FAIL "a symlink squatter survived or took the write-through (rc=$rc)"
  fi
  rm -f "$tmp/clone/provenance.json" "$tmp/zz-symlink-target"

  # Index flags that hide changes from status must refuse, not stamp clean over
  # a modification git was told to ignore: assume-unchanged with real bytes
  # changed, then skip-worktree (the flag alone blinds status, so the flag alone
  # refuses).
  cg update-index --assume-unchanged README.md
  echo "hidden" >> "$tmp/clone/README.md"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "hide changes"; then
    say OK "an assume-unchanged modification refuses the stamp by name"
  else
    say FAIL "an assume-unchanged modification stamped clean (rc=$rc)"
  fi
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "hide changes"; then
    say OK "an assume-unchanged modification refuses the guard by name"
  else
    say FAIL "an assume-unchanged modification passed the guard (rc=$rc)"
  fi
  cg update-index --no-assume-unchanged README.md
  cg checkout -q -- README.md
  cg update-index --skip-worktree README.md
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "hide changes"; then
    say OK "a skip-worktree flag refuses the stamp by name"
  else
    say FAIL "a skip-worktree flag was seen through or ignored (rc=$rc)"
  fi
  cg update-index --no-skip-worktree README.md

  # Config alone can hide payload: status.showUntrackedFiles=no omits an
  # untracked file that npm pack SHIPS, so the stamp must enumerate untracked
  # files explicitly rather than inherit the maintainer's config.
  cg config status.showUntrackedFiles no
  echo "config-hidden" > "$tmp/clone/claude/guides/zz-untracked-probe.md"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "dirty"; then
    say OK "config-hidden untracked payload still reads as dirty"
  else
    say FAIL "status.showUntrackedFiles=no let untracked payload stamp clean (rc=$rc)"
  fi
  rm -f "$tmp/clone/claude/guides/zz-untracked-probe.md"
  cg config --unset status.showUntrackedFiles

  # A LOCALLY ignored payload file is invisible to status at every setting yet
  # rides the tarball: hide one via .git/info/exclude — the packlist-vs-HEAD
  # pass must refuse it by name.
  echo "zz-local-excluded.md" >> "$tmp/clone/.git/info/exclude"
  echo "smuggled" > "$tmp/clone/claude/guides/zz-local-excluded.md"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "which HEAD does not contain"; then
    say OK "a locally excluded payload file refuses the stamp by name"
  else
    say FAIL "a locally excluded payload file rode the packlist unseen (rc=$rc)"
  fi
  rm -f "$tmp/clone/claude/guides/zz-local-excluded.md"
  cg checkout -q -- .git/info/exclude 2>/dev/null || printf '' > "$tmp/clone/.git/info/exclude"

  # A .npmignore in a shipped subtree subtracts committed payload from the
  # packlist — hidden from git via local excludes, it leaves the tree reading
  # clean while the tarball loses a guide the shipped global routes to. The
  # completeness direction must refuse it by name.
  echo "claude/.npmignore" >> "$tmp/clone/.git/info/exclude"
  printf 'guides/tooling-gotchas.md\n' > "$tmp/clone/claude/.npmignore"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "packlist omits it"; then
    say OK "a hidden .npmignore subtracting committed payload refuses the stamp"
  else
    say FAIL "a hidden .npmignore silently shrank the packlist (rc=$rc)"
  fi
  rm -f "$tmp/clone/claude/.npmignore"
  cg checkout -q -- .git/info/exclude 2>/dev/null || printf '' > "$tmp/clone/.git/info/exclude"

  # Filters smudge silently: with core.autocrlf the tree reads clean while the
  # worktree bytes npm packs differ from HEAD's blob — the CRLF-shebang
  # reproduction. The control first proves the smudge happened, or it would
  # pass vacuously on a platform that did not convert.
  cg config core.autocrlf true
  rm -f "$tmp/clone/install.sh"
  cg checkout -q -- install.sh
  grep -q "$(printf '\r')" "$tmp/clone/install.sh" \
    || die "self-test: core.autocrlf did not smudge install.sh — the filter control has no subject"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "differs byte-wise"; then
    say OK "a filter-smudged worktree refuses the stamp by name"
  else
    say FAIL "a filter-smudged worktree stamped clean over different bytes (rc=$rc)"
  fi
  cg config --unset core.autocrlf
  rm -f "$tmp/clone/install.sh"
  cg checkout -q -- install.sh

  # Mode drift hides the same way: core.filemode=false keeps status clean while
  # the tarball packs a stripped execute bit — a shipped CLI that does not run.
  # Precondition first: the subject must BE executable in HEAD, or the control
  # judges nothing.
  cg ls-tree HEAD -- session-cost.py | grep -q '^100755' \
    || die "self-test: session-cost.py is not 100755 in HEAD — the filemode control has no subject"
  cg config core.filemode false
  chmod -x "$tmp/clone/session-cost.py"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "executable in HEAD but not on disk"; then
    say OK "a stripped execute bit refuses the stamp by name"
  else
    say FAIL "a stripped execute bit stamped clean over a different artifact (rc=$rc)"
  fi
  chmod +x "$tmp/clone/session-cost.py"
  cg config --unset core.filemode

  # A dirty tree must be refused BY NAME — by the guard, and by the default
  # stamp too, because the tgz publish path runs no lifecycle and the pack step
  # is the only gate that survives into it.
  echo "planted" >> "$tmp/clone/README.md"
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "dirty"; then
    say OK "a dirty tree is refused by the guard, naming the dirt"
  else
    say FAIL "a dirty tree was not refused by the guard (rc=$rc)"
  fi
  rm -f "$tmp/clone/provenance.json"   # the clean-stamp control's residue, not this control's subject
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "PACK BLOCKED" \
     && [ ! -f "$tmp/clone/provenance.json" ]; then
    say OK "a default dirty pack is refused before any stamp is written"
  else
    say FAIL "a default dirty pack was not refused (rc=$rc)"
  fi
  (cd "$tmp/clone" && AGENT_BIOS_PACK_DIRTY=1 cleangit bash "$self" --stamp) >/dev/null \
    && grep -q '"dirty":true' "$tmp/clone/provenance.json" \
    && say OK "an opted-in test pack is stamped dirty:true honestly" \
    || say FAIL "the AGENT_BIOS_PACK_DIRTY opt-in did not stamp dirty:true"
  cg checkout -q -- README.md
  # The stamp's own residue must not read as dirt on the next run — in the real
  # tree /provenance.json is gitignored; the clone's .gitignore may lag the
  # working tree's during development, so each leg leaves the clone as found.
  rm -f "$tmp/clone/provenance.json"

  # A local-only commit must be refused: its provenance would dangle.
  cg -c user.name=self-test -c user.email=self-test@local \
    commit -q --allow-empty -m "local only" || die "self-test: could not commit in the clone"
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "no origin branch or advertised tag"; then
    say OK "a HEAD on no origin ref is refused, naming the reason"
  else
    say FAIL "an unpushed HEAD was not refused by name (rc=$rc)"
  fi

  # A locally cached remote ref must not vouch for it: plant a stale origin/*
  # ref at the unpushed HEAD — fetch --prune must discard what origin no longer
  # advertises, or the guard passes on a commit nobody can fetch.
  cg update-ref refs/remotes/origin/zz-stale HEAD
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "no origin branch or advertised tag"; then
    say OK "a stale cached origin ref is pruned rather than trusted"
  else
    say FAIL "a stale cached origin ref vouched for an unfetchable commit (rc=$rc)"
  fi

  # A NARROW fetch refspec (what single-branch clones configure) must not
  # shelter the stale ref: with the config mapping only one branch, the prune
  # still judges the whole origin/* namespace via the explicit refspec.
  cg config remote.origin.fetch "+refs/heads/${seat#refs/remotes/origin/}:refs/remotes/origin/${seat#refs/remotes/origin/}"
  cg update-ref refs/remotes/origin/zz-stale HEAD
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "no origin branch or advertised tag"; then
    say OK "a narrow fetch refspec does not shelter a stale origin ref"
  else
    say FAIL "a stale ref outside the configured refspec vouched for the commit (rc=$rc)"
  fi
  cg config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"

  # A release checkout is detached at a pushed TAG no branch holds. Origin is
  # re-pointed at a bare COPY first, so the control can push a tag without
  # touching the real repository; every later guard control fetches from the
  # copy the same way.
  cleangit git clone -q --bare "$src" "$tmp/origin.git" \
    || die "self-test: could not make the bare origin copy"
  cg remote set-url origin "$tmp/origin.git"
  cg tag zz-release-probe HEAD
  cg push -q origin refs/tags/zz-release-probe 2>/dev/null \
    || die "self-test: could not push the probe tag to the bare copy"
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -eq 0 ]; then
    say OK "a commit held only by a pushed origin tag passes the guard"
  else
    say FAIL "a tag-retained release commit was refused as unfetchable (rc=$rc)"
  fi
  cg tag -d zz-release-probe >/dev/null

  # An inspection that ERRORS must fail closed, not read as clean: corrupt the
  # clone's index (the reviewer's reproduction) and both entry points must
  # refuse by name rather than stamp or pass an unjudgeable tree. Last control —
  # the clone is unusable afterwards.
  printf x > "$tmp/clone/.git/index"
  rm -f "$tmp/clone/provenance.json"
  out="$(in_clone --stamp 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "cannot be judged" \
     && [ ! -f "$tmp/clone/provenance.json" ]; then
    say OK "a failing git status refuses the stamp instead of stamping clean"
  else
    say FAIL "a failing git status let the stamp through (rc=$rc)"
  fi
  out="$(in_clone --guard 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "cannot be judged"; then
    say OK "a failing git status refuses the guard instead of passing"
  else
    say FAIL "a failing git status let the guard pass (rc=$rc)"
  fi

  if [ "$fails" -gt 0 ]; then
    printf 'CHECK-PUBLISH SELF-TEST FAIL: %s problem(s)\n' "$fails"
    return 1
  fi
  printf 'CHECK-PUBLISH SELF-TEST OK: stamp binds and refuses dirty by default, guard refuses dirty, unpushed, and stale-ref-vouched, all by name\n'
}

case "${1:-}" in
  --stamp)     cmd_stamp ;;
  --guard)     cmd_guard ;;
  --self-test) self_test ;;
  *) die "usage: check-publish.sh --stamp | --guard | --self-test" ;;
esac
