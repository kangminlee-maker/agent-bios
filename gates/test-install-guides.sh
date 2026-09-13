#!/usr/bin/env bash
# Explicit compatibility-install scenarios against a throwaway HOME.
# Native deployment, withholding, cleanup and canary assertions use the legacy
# installer route; private CLI installation is tested by test_corpus_end_to_end.py.
#
# I1 author-only guide withheld in full mode; I2 a copy an earlier install left
# behind is removed; I3 verify accepts the absence rather than demanding presence;
# I4 the subject is real — the guide exists in the source tree and declares it.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
export AGENT_BIOS_LEGACY_INSTALL=1
# `|| exit 1`, because set -u does not catch this: a failed mktemp still ASSIGNS,
# to the empty string, and every path below would then be rooted at / — this file
# runs a real installer, so that is an install into /home and /.claude.
T=$(mktemp -d "${TMPDIR:-/tmp}/inst-test-XXXXXX") || exit 1
[ -n "$T" ] && [ -d "$T" ] || { echo "FAIL: no temp dir; refusing to install into /"; exit 1; }
trap 'rm -rf "$T"' EXIT
# The caller's managed environment is not a fixture. Keep even a regression's inherited
# override inside this test root, then require each install HOME to use its own venv.
OUTER_VENV="$T/inherited-venv"
mkdir -p "$OUTER_VENV"
printf '%s\n' 'parent environment sentinel' > "$OUTER_VENV/keep"
export AGENT_LAUNCH_VENV="$OUTER_VENV"
# A failing check prints the last of whatever install.sh wrote, because the assertion
# alone never says why. Several checks here read only an exit code out of `$T/rc` while
# the reason sits in `$T/log`, which the next run_install overwrites — so a failure
# inside the parity umbrella cost an eleven-minute standalone re-run that came back
# green, three times, before the umbrella learned to keep this file's output. This is
# that same fix one level further down.
fail=0
chk(){
  if eval "$2"; then
    echo "PASS: $1"
  else
    echo "FAIL: $1"
    if [ -s "$T/log" ]; then
      echo "  --- last 12 lines of the install.sh run this check read ---"
      tail -12 "$T/log" | sed 's/^/  /'
      echo "  --- end ---"
    fi
    fail=1
  fi
}

AUTHOR_GUIDE=session-distill-workflow.md
OTHER_GUIDE=learning-flow.md

# I4 first: every assertion below is "the author-only guide is absent", and an
# absent subject satisfies that for the wrong reason. Prove the subject exists
# and still carries the declaration before trusting a single absence.
chk "I4 the author-only guide exists in the source tree" \
    "[ -f \"$REPO/claude/guides/$AUTHOR_GUIDE\" ] && [ -f \"$REPO/codex/guides/$AUTHOR_GUIDE\" ]"
chk "I4 it still declares audience: author" \
    "python3 -c \"import sys,pathlib; sys.path.insert(0,'$REPO/compose'); from assemble import author_only; sys.exit(0 if author_only(pathlib.Path('$REPO/claude/guides/$AUTHOR_GUIDE')) else 1)\""
chk "I4 the contrast guide exists and does NOT declare it" \
    "python3 -c \"import sys,pathlib; sys.path.insert(0,'$REPO/compose'); from assemble import author_only; sys.exit(1 if author_only(pathlib.Path('$REPO/claude/guides/$OTHER_GUIDE')) else 0)\""

# ZDOTDIR is redirected as deliberately as HOME. install.sh writes its shell hook
# to ${ZDOTDIR:-$HOME}/.zshrc, so overriding HOME alone left a developer who
# exports ZDOTDIR having their REAL .zshrc appended to by a test — outside the
# temp tree, and outside the cleanup trap.
sandbox_env() {
  printf '%s\n' "HOME=$T/home" "ZDOTDIR=$T/home" "CLAUDE_CONFIG_DIR=$T/home/.claude" \
                "CODEX_HOME=$T/home/.codex" \
                "AGENT_LAUNCH_VENV=$T/home/.local/share/agent-launch/venv" \
                "AGENT_BIOS_IN_INSTALL_TEST=1"
}

run_install() {   # $1: subcommand, $2...: extra args
  # `install.sh verify` runs gates/check-parity.sh, which runs this file. The
  # sentinel makes the umbrella skip it — loudly — instead of recursing forever.
  local sub="$1"; shift
  env $(sandbox_env) bash "$REPO/install.sh" "$sub" "$@" >"$T/log" 2>&1
  echo $? > "$T/rc"
}

CD="$T/home/.claude"; XD="$T/home/.codex"
mkdir -p "$T/home" "$CD/guides" "$XD/guides"
# Seed the copies an earlier install would have left, so ONE run answers both
# questions: is the guide withheld, and is a copy already on disk removed. Each
# install here costs ~45s, so the difference between one run and two is most of
# this file's wall clock.
# The claude-side seed carries FOREIGN content on purpose: the same run then
# answers "is it removed" and "was it copied somewhere first", and the marker
# proves the backup holds the file that was there rather than ours.
printf 'my own notes, not agent-bios\n' > "$CD/guides/$AUTHOR_GUIDE"
cp "$REPO/codex/guides/$AUTHOR_GUIDE" "$XD/guides/$AUTHOR_GUIDE"
# A file of THEIRS in the shared codex guides directory. The assembler leaves any name it did
# not deploy alone, but the manifest used to be built by scanning that whole directory — so
# uninstall deleted it one step later, and the assembler's care bought nothing.
printf 'a codex guide the user wrote\n' > "$XD/guides/my-own-codex-guide.md"
# And the same question asked of central/, which was exempted from that fix as "ours whole"
# and went on being scanned. The assembler applies ONE ownership rule to every destination —
# the name exists in our source tree — so a file the user left here is as safe from it as one
# in the shared codex directory, and the manifest has to agree or uninstall undoes that.
mkdir -p "$CD/central/guides"
printf 'a note the user left in central/guides\n' > "$CD/central/guides/my-own-central-guide.md"
printf 'a note the user left in central itself\n' > "$CD/central/my-own-central-note.md"
run_install install
chk "I1 install exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
# The mode still matters, but "full" is no longer the ABSENCE of a selection: the
# two install paths collapsed into one, and full mode is now "every domain
# selected" (install.sh assemble_corpus). Asserting no selection.json existed
# described a branch that is gone. Naming every domain keeps the contrast this
# file needs — it is what separates this run from I6's single-domain one — where
# asserting mere presence would pass for either.
chk "I1 ran in FULL mode (every domain selected)" \
    "python3 -c \"import json,sys; sel=set(json.load(open('$T/home/.local/share/agent-bios/selection.json'))['domains']); every=set(json.load(open('$REPO/compose/domains.json'))['domains']); sys.exit(0 if every and sel==every else 1)\""
chk "I1 author-only guide withheld from claude" "[ ! -f \"$CD/guides/$AUTHOR_GUIDE\" ]"
chk "I1 author-only guide withheld from codex" "[ ! -f \"$XD/guides/$AUTHOR_GUIDE\" ]"
# Each absence above needs a presence beside it: an empty guides directory
# satisfies "the author-only guide is not there" for entirely the wrong reason.
# The two hosts read differently on purpose: the claude corpus now lands under
# central/, while the codex tree keeps its flat guides dir. $CD/guides is the
# PRE-unification destination, which is why nothing is expected there any more —
# it is only swept (below), never written.
chk "I1 an ordinary claude guide still deploys" "[ -f \"$CD/central/guides/$OTHER_GUIDE\" ]"
chk "I1 an ordinary codex guide still deploys" "[ -f \"$XD/guides/$OTHER_GUIDE\" ]"
chk "I1 the withholding is reported, not silent" "grep -q 'withheld (audience: author)' \"$T/log\""
# The manifest is what uninstall deletes from, so a name in it is a deletion scheduled. It must
# name what we deployed and nothing else — the presence check beside it keeps this from passing
# on a manifest that is simply empty.
chk "I1 the manifest does not claim a codex guide the user wrote" \
    "! grep -q 'my-own-codex-guide.md' \"$T/home/.local/share/agent-bios/manifest.txt\""
chk "I1 nor a file the user left under central/" \
    "! grep -q 'my-own-central-guide.md\|my-own-central-note.md' \"$T/home/.local/share/agent-bios/manifest.txt\""
chk "I1 and both user files are still on disk after the install" \
    "[ -f \"$CD/central/guides/my-own-central-guide.md\" ] && [ -f \"$CD/central/my-own-central-note.md\" ]"
chk "I1 and it does claim the ones we deployed" \
    "grep -q '/guides/$OTHER_GUIDE' \"$T/home/.local/share/agent-bios/manifest.txt\""
# The absences above need presences beside them, or a manifest that simply stopped naming
# central/ at all would satisfy every one of them.
chk "I1 and it claims the central bundle and the guides we deployed there" \
    "grep -q '/central/bundle.md' \"$T/home/.local/share/agent-bios/manifest.txt\" && grep -q '/central/guides/$OTHER_GUIDE' \"$T/home/.local/share/agent-bios/manifest.txt\""
# I1 zero-egress: the INSTALLED-artifact half of gates/check-endpoints.py's claim.
# That gate probes the resolver on a scratch home; this asserts the same of the home
# a real default install just produced. Instrument first: the probe must see a
# planted slot before its "no transport" answer counts (a dead probe reads as PASS).
cat > "$T/probe-egress.py" <<PYEOF
import importlib.util, os, pathlib, sys, tempfile
spec = importlib.util.spec_from_file_location("cl", "$REPO/learn/collect-learning.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ctl = pathlib.Path(tempfile.mkdtemp(prefix="egress-ctl-")); os.environ["HOME"] = str(ctl)
slot = ctl / ".config" / "agent-bios"; slot.mkdir(parents=True)
(slot / "token").write_text("t"); (slot / "ingest-url").write_text("https://ctl.test")
cfg, why = m.transport_config()
if cfg != ("t", "https://ctl.test") or why is not None:
    sys.exit(2)  # instrument blind to a planted slot; the absence below proves nothing
os.environ["HOME"] = "$T/home"
# The slot DIRECTORY must be absent outright: a partial write (token without
# url) also resolves (None, reason), so cfg alone cannot see it, and a
# dynamically composed installer write evades any static needle (round 3, #0).
if (pathlib.Path("$T/home") / ".config" / "agent-bios").exists():
    sys.exit(3)
# One slot, host-independent, so one call — the two host homes cannot differ.
# Exact reason, not containment: a prefixed or rewritten reason that merely
# CONTAINS the phrase is a different branch than the default one this
# asserts (round 4, #13). The expectation is BUILT from the same path the
# assertion above proved absent, so it cannot drift into naming another slot.
expected_slot = pathlib.Path("$T/home") / ".config" / "agent-bios"
cfg, why = m.transport_config()
if cfg is not None or why != f"no transport configured (no {expected_slot} slot)":
    sys.exit(1)
sys.exit(0)
PYEOF
chk "I1 zero-egress: installed homes (both hosts) resolve no transport (instrument proven first)" \
    "python3 \"$T/probe-egress.py\""
cat > "$T/probe-hooks.py" <<'PYEOF'
import json, pathlib, re, shlex, sys
home, repo = sys.argv[1], sys.argv[2]
installed = json.load(open(f"{home}/.claude/settings.json"))
template = json.load(open(f"{repo}/claude/settings.template.json"))
hookdir = pathlib.Path(home) / ".claude" / "central" / "hooks"

def registrations(doc, rewrite):
    """(event, matcher, command) triples. The installer rewrites the template's
    relative script path to a shlex-quoted ABSOLUTE one (assemble.merge_settings,
    for config homes with spaces), so the template side is rewritten the same way
    before comparing — equality against the raw template would fail on the
    product working correctly. The SAME substitution the installer performs, not
    a reconstruction of the line: rebuilding it as `python3 <abs>` discarded any
    interpreter flag or script argument and would fail on the installer working
    exactly as designed."""
    out = []
    for event, entries in (doc.get("hooks") or {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if rewrite:
                    m = re.search(r"\S*/hooks/([A-Za-z0-9._-]+)", cmd)
                    if m:
                        target = shlex.quote(str(hookdir / m.group(1)))
                        cmd = re.sub(r"\S*/hooks/" + re.escape(m.group(1)),
                                     lambda _m, v=target: v, cmd)
                out.append((event, entry.get("matcher"), cmd))
    return sorted(out)

want = registrations(template, rewrite=True)
got = registrations(installed, rewrite=False)
# Known-opposite on the comparison itself: an extra registration must be visible,
# or "they match" says nothing about what a collection hook would look like.
spiked = json.loads(json.dumps(installed))
spiked.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "curl https://x"}]})
if registrations(spiked, rewrite=False) == got:
    sys.exit(3)  # the comparison cannot see an added hook; its verdict is worthless
sys.exit(0 if want and got == want else 1)
PYEOF
chk "I1 zero-egress: installed hooks are exactly the template's registrations (extra-hook control inline)" \
    "python3 \"$T/probe-hooks.py\" \"$T/home\" \"$REPO\""

# I2: not writing it is not enough for anyone who installed before this rule. The
# manifest is rebuilt from the current deploy, so a file that stops being deployed
# stops being tracked and would otherwise sit there for good. The copies were
# seeded before the run above, so the absences asserted in I1 are removals.
# Two removals with two owners, so one message cannot witness both. assemble.py
# prunes the destinations it writes ($CD/central/guides and $XD/guides) and says
# "remove withheld"; install.sh sweeps the pre-unification $CD/guides, which the
# assembler never touches, and says "removed stale copy". Counting one string
# twice was the old two-path assumption — it asserted that a single mechanism
# reached both hosts, which is no longer how the sweep is divided.
chk "I2 the claude pre-unification copy's removal is reported by the installer" \
    "grep -q 'removed stale copy' \"$T/log\""
chk "I2 the codex copy's removal is reported by the assembler that owns it" \
    "grep -q 'remove withheld .*codex/guides/$AUTHOR_GUIDE' \"$T/log\""

# I3: verify used to require every repo guide to be present, which would have
# turned the withholding into a verification failure.
run_install verify
chk "I3 verify accepts the withheld guide" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I3 verify says so rather than staying quiet" \
    "grep -q 'author-only guides withheld' \"$T/log\""
# The umbrella that launched this suite already judged this tree, so verify skips the
# parity gate here — twelve times, 43 of the commit's 50 minutes. Both directions are
# asserted: the skip must be announced (a silent one is indistinguishable from a gate
# that was deleted), and the two cheap maintainer gates must still RUN, or a later
# widening of that guard would take them with it and nothing would say so.
chk "the parity gate is skipped inside this suite, and announces it" \
    "grep -q 'SKIP: repo mirror parity' \"$T/log\""
chk "the payload gate is NOT skipped with it" \
    "grep -q 'npm payload OK' \"$T/log\""
chk "the prompting-target gate is NOT skipped with it" \
    "grep -q 'prompting targets OK' \"$T/log\""

# I10: the DEPLOYED launcher renders the selected language.
#
# Every other render check in this repo drives the CLONE launcher, which has
# launch/i18n sitting next to it and therefore CANNOT reproduce the shape that
# fails: deployed, the launcher lands in $HOME/.local/bin while its catalogs land
# under $HOME/.config/agent-launch, so it keeps none beside itself and whatever is
# deployed IS the UI text. This runs on the tree the install above just produced,
# so the marginal cost is one launcher start rather than another ~45s install.
#
# Expected text is read from the deployed catalog at run time. Nothing is written
# here for a translator to keep in sync.
DEPLOYED="$T/home/.local/bin/agent-launch"
DEPLOYED_I18N="$T/home/.config/agent-launch/i18n"
chk "I10 the launcher deployed with no catalog beside it" \
    "[ -x \"$DEPLOYED\" ] && [ ! -e \"$T/home/.local/bin/i18n\" ]"
cat_text() {    # $1: language, $2: key — read from the DEPLOYED catalog at run time
  python3 -c "import tomllib,sys;print(tomllib.load(open(sys.argv[1],'rb'))[sys.argv[2]])" \
          "$DEPLOYED_I18N/$1.toml" "$2"
}
render() {      # $1: language, $2: output file
  printf 'q\n' | env $(sandbox_env) AGENT_LAUNCH_TUI=0 AGENT_LAUNCH_LANG="$1" \
    python3 "$DEPLOYED" --preset balanced --custom --dry-run codex >"$2" 2>&1 || true
}
# Every shipped language, not just Korean. Rendering one of them proved nothing
# about the others: deleting the deployed ja.toml left all of these green, which
# is precisely the regression class this leg exists to catch.
for lang in ko ja; do
  title=$(cat_text "$lang" custom.title) || title=""
  # The expected text being non-empty is an ASSERTION, not a detail. An unreadable
  # or missing catalog left it empty, and `grep -qxF ""` matches any file holding a
  # blank line — every render has one — so both checks below passed while the
  # language had never been deployed at all.
  chk "I10 ($lang) the deployed catalog yields a title to expect" "[ -n \"$title\" ]"
  render "$lang" "$T/$lang-render"
  chk "I10 ($lang) the deployed launcher renders it" \
      "[ -n \"$title\" ] && grep -qxF \"$title\" \"$T/$lang-render\""
  chk "I10 ($lang) and shows no key name in place of text" \
      "! grep -qxF 'custom.title' \"$T/$lang-render\""
done
KO_TITLE=$(cat_text ko custom.title) || KO_TITLE=""
render_ko() { render ko "$1"; }

# I10 negative control: catalogs older than the launcher — the state a partial
# upgrade leaves, and the reason the catalogs deploy before the launcher. Drop a
# key from BOTH deployed catalogs and the launcher has nowhere left to read it.
# It must say so rather than quietly drawing the key's own name, which is exactly
# what it used to do.
for lang in en ko; do
  grep -v '^"custom.title"' "$DEPLOYED_I18N/$lang.toml" > "$T/$lang.stale" \
    && cp "$T/$lang.stale" "$DEPLOYED_I18N/$lang.toml"
done
render_ko "$T/ko-stale"
chk "I10 (control) a key missing from every deployed catalog is announced" \
    "grep -q 'no UI text for' \"$T/ko-stale\""
# Whole-line matches: the title occupies its own line, and the phrase also occurs
# INSIDE another string ("...이 구성을 사용자 설정에 이름 있는 프리셋으로..."), so a
# substring search reports the title as present on a screen that never drew it.
chk "I10 (control) and the screen drew the key name instead of the title" \
    "grep -qxF 'custom.title' \"$T/ko-stale\" && ! grep -qxF \"$KO_TITLE\" \"$T/ko-stale\""
# Restore from the same source install.sh deploys from, rather than reinstalling:
# a second install costs ~45s and would prove only that cp overwrites.
cp "$REPO/launch/i18n/en.toml" "$REPO/launch/i18n/ko.toml" "$DEPLOYED_I18N/"
render_ko "$T/ko-restored"
chk "I10 (control) restoring the catalogs brings the Korean title back" \
    "[ -n \"$KO_TITLE\" ] && grep -qxF \"$KO_TITLE\" \"$T/ko-restored\" \
     && ! grep -q 'no UI text for' \"$T/ko-restored\""

# I5: the removal backed up first. An unconditional rm would delete a same-named
# file this installer never wrote — a shared or symlinked guides directory makes
# that somebody's own file, and it is not ours to destroy. Asserted against the
# seeding above rather than a second install: each one costs ~45s.
chk "I5 the foreign file was backed up before removal, recoverably" \
    "grep -rq 'my own notes' \"$T/home/.local/share/agent-bios/backups\""
chk "I5 the backup holds THEIR content, not our copy of the guide" \
    "! grep -rq 'guide_id: session-distill-workflow' \"$T/home/.local/share/agent-bios/backups/\"*/*/*/*/.claude 2>/dev/null"

# I6: the sweep must reach the directory the OTHER mode writes. A machine that
# installed in full mode and then selects domains would otherwise keep the
# full-mode copy for good — the packaged path never looks there.
cp "$REPO/claude/guides/$AUTHOR_GUIDE" "$CD/guides/$AUTHOR_GUIDE"
run_install install --domains builder-base
chk "I6 the domain-selected install exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I6 it really took the packaged path" \
    "[ -f \"$T/home/.local/share/agent-bios/selection.json\" ]"
chk "I6 the full-mode copy is pruned by the packaged run" "[ ! -f \"$CD/guides/$AUTHOR_GUIDE\" ]"
# The packaged destination has never existed before this run, so these two are the
# FIRST-TIME case: every assertion until now started from a seeded copy and so
# could only ever prove removal, never that a fresh install withholds.
chk "I6 a first-time packaged destination withholds it" \
    "[ ! -f \"$CD/central/guides/$AUTHOR_GUIDE\" ]"
chk "I6 and that destination is not simply empty" \
    "[ -f \"$CD/central/guides/$OTHER_GUIDE\" ]"

# I7: an unreadable declaration must abort, not withhold nothing. Empty here means
# "deploy everything", so swallowing the failure ships exactly what the rule holds
# back — a fail-open wearing a degrade-gracefully coat.
B="$T/broken"; mkdir -p "$B"
(cd "$REPO" && git ls-files -z | (cd "$REPO" && tar --null -T - -cf -)) 2>/dev/null | (cd "$B" && tar -xf -) 2>/dev/null \
  || python3 -c "
import pathlib,shutil,subprocess,sys
src,dst=pathlib.Path('$REPO'),pathlib.Path('$B')
for rel in subprocess.run(['git','-C',str(src),'ls-files','-z'],capture_output=True,check=True).stdout.decode().split('\0'):
    if rel:
        (dst/rel).parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src/rel,dst/rel)"
rm -f "$B/compose/assemble.py"
env HOME="$T/broken-home" ZDOTDIR="$T/broken-home" CLAUDE_CONFIG_DIR="$T/broken-home/.claude" \
  CODEX_HOME="$T/broken-home/.codex" AGENT_BIOS_IN_INSTALL_TEST=1 \
  AGENT_LAUNCH_VENV="$T/broken-home/.local/share/agent-launch/venv" \
  bash "$B/install.sh" install >"$T/blog" 2>&1; echo $? > "$T/brc"
chk "I7 an unreadable audience declaration aborts the install" "[ \$(cat \"$T/brc\") -ne 0 ]"
# This one is also the control for a much older defect it uncovered: a bare
# `exec 3<&0 2>/dev/null` applied its redirection to the SHELL, so every error
# install.sh wrote to stderr went to /dev/null for the rest of the run. The
# refusal aborted correctly and told the operator nothing at all.
chk "I7 it says why rather than withholding nothing" \
    "grep -q 'refusing to deploy' \"$T/blog\""
chk "I7 the underlying cause reaches the operator too" \
    "grep -q 'could not be imported' \"$T/blog\""
chk "I7 and nothing was deployed" \
    "[ ! -f \"$T/broken-home/.claude/guides/$AUTHOR_GUIDE\" ]"

# I8: verify judges the absence in BOTH modes. The check used to sit inside the
# full-mode branch, so a packaged machine's restored copy passed.
cp "$REPO/claude/guides/$AUTHOR_GUIDE" "$CD/central/guides/$AUTHOR_GUIDE" 2>/dev/null \
  || { mkdir -p "$CD/central/guides"; cp "$REPO/claude/guides/$AUTHOR_GUIDE" "$CD/central/guides/$AUTHOR_GUIDE"; }
run_install verify
chk "I8 verify fails on a copy restored under the packaged path" "[ \$(cat \"$T/rc\") -ne 0 ]"
chk "I8 and names the file it found" "grep -q 'author-only guide is still installed' \"$T/log\""

# I9: a failed activation canary records its outcome where the launcher's corpus
# checklist reads it. The claude CLI is stubbed to reply without the rev marker,
# so the canary runs its REAL probe path and fails without a live session. The
# flip-side (outcome overwritten on a later apply) is proven through the same
# recording tool the success path calls — a real success-path onboard would need
# an authenticated live probe this suite must not perform.
mkdir -p "$T/stubbin"
printf '#!/usr/bin/env bash\necho "no rev marker in this reply"\n' > "$T/stubbin/claude"
chmod +x "$T/stubbin/claude"
env $(sandbox_env) PATH="$T/stubbin:$PATH" \
  bash "$REPO/install.sh" onboard --domains office-work >"$T/log9" 2>&1
echo $? > "$T/rc9"
chk "I9 onboard exits nonzero on a failed canary" "[ \$(cat \"$T/rc9\") -ne 0 ]"
S9="$T/home/.local/share/agent-bios/corpus-status.json"
chk "I9 the failed canary recorded its outcome" \
    "python3 -c \"import json,sys; s=json.load(open('$S9')); sys.exit(0 if s.get('last_apply',{}).get('outcome')=='canary_failed' else 1)\""
chk "I9 the record names the requested selection" \
    "python3 -c \"import json,sys; s=json.load(open('$S9')); sys.exit(0 if s['last_apply']['requested']==['office-work'] else 1)\""
env $(sandbox_env) python3 "$REPO/compose/corpus-state.py" record-apply \
  --requested office-work --outcome applied >/dev/null 2>&1
chk "I9 a later apply overwrites the failure (negative control: the assertion above cannot pass now)" \
    "python3 -c \"import json,sys; s=json.load(open('$S9')); sys.exit(0 if s['last_apply']['outcome']=='applied' else 1)\""

# I11: `--dry-run` changes nothing. install.sh's own help and README both say "print
# actions without changing anything", and the corpus-status projection sat outside the
# dry-run branch — so the one command a user runs when unwilling to touch anything
# rewrote the file that records what is deployed. The fingerprint covers the whole state
# directory rather than that one file, because the next unguarded write will not be in
# the file we already know about.
S11="$T/home/.local/share/agent-bios"
fingerprint() { find "$1" -type f -exec shasum -a 256 {} \; 2>/dev/null | sort | shasum -a 256; }
chk "I11 the state directory exists to be fingerprinted" "[ -d \"$S11\" ]"
DRY_BEFORE=$(fingerprint "$S11")
chk "I11 the fingerprint is non-empty" "[ -n \"$DRY_BEFORE\" ]"
run_install install --dry-run
chk "I11 dry-run exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
DRY_AFTER=$(fingerprint "$S11")
chk "I11 dry-run left every state file untouched" "[ \"$DRY_BEFORE\" = \"$DRY_AFTER\" ]"
chk "I11 and it still reported the step it skipped" "grep -q 'dry-run..project corpus-status' \"$T/log\""

# I12: a shipped skill is a directory in a directory the host scans and other tools
# populate. It must land on BOTH hosts file by file, each file named in the manifest, and
# uninstall must remove exactly those names — a skill of the user's beside ours survives,
# and so does the shared skills/ parent. Asserted last because uninstall ends the tree.
SKILL_SRC="$REPO/claude/skills"
SKILL=$(for d in "$SKILL_SRC"/*/; do [ -f "$d/SKILL.md" ] && basename "$d" && break; done)
chk "I12 the source tree ships at least one skill (the subject exists)" "[ -n \"$SKILL\" ]"
# A skill reaches only the selections that cover it (I15 below), and I9 left the saved
# selection at office-work — so the deploy is asserted under a selection that HOLDS the
# skill, read from the manifest rather than typed here.
SKILL_DOMAINS=$(python3 -c "import json;print(' '.join(json.load(open('$REPO/compose/domains.json'))['skills']['$SKILL']['domains']))")
OUTSIDE=$(python3 -c "import json;m=json.load(open('$REPO/compose/domains.json'));print(next(d for d in sorted(m['domains']) if d not in m['skills']['$SKILL']['domains']))")
chk "I12 the shipped skill is classified into at least one domain" "[ -n \"$SKILL_DOMAINS\" ]"
run_install install --domains "$(echo $SKILL_DOMAINS | cut -d' ' -f1)"
chk "I12 an install selecting the skill's domain exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I12 the skill deployed to claude" "[ -f \"$CD/skills/$SKILL/SKILL.md\" ]"
chk "I12 the skill deployed to codex" "[ -f \"$XD/skills/$SKILL/SKILL.md\" ]"
chk "I12 byte-identical to the source on both hosts" \
    "cmp -s \"$SKILL_SRC/$SKILL/SKILL.md\" \"$CD/skills/$SKILL/SKILL.md\" && cmp -s \"$SKILL_SRC/$SKILL/SKILL.md\" \"$XD/skills/$SKILL/SKILL.md\""
chk "I12 the manifest names the skill file on both hosts" \
    "grep -qxF \"$CD/skills/$SKILL/SKILL.md\" \"$T/home/.local/share/agent-bios/manifest.txt\" && grep -qxF \"$XD/skills/$SKILL/SKILL.md\" \"$T/home/.local/share/agent-bios/manifest.txt\""
# A skill of THEIRS beside ours, and a file of theirs inside OUR skill directory: the first
# must survive untouched, the second must survive AND keep our directory from being removed
# (rmdir, never rm -rf — a directory we cannot fully account for is left visibly).
mkdir -p "$CD/skills/their-skill" "$XD/skills/their-skill" "$CD/skills/$SKILL/notes"
printf 'their skill\n' > "$CD/skills/their-skill/SKILL.md"
printf 'their skill\n' > "$XD/skills/their-skill/SKILL.md"
printf 'their notes inside our skill\n' > "$CD/skills/$SKILL/notes/mine.md"
chk "I12 the manifest does not claim the skill the user wrote" \
    "! grep -q 'their-skill' \"$T/home/.local/share/agent-bios/manifest.txt\""

# I15: a skill is classified in compose/domains.json like a guide, and the selection
# decides who receives it. Narrowing to a domain the skill is not in must remove the
# deployed copy (backed up, like any withdrawal) and verify must agree; widening back
# must redeploy it. The subject is asserted first: the shipped skill must be classified
# into a domain, and there must be a registered domain it is NOT in, or the scenario
# has nothing to narrow to.
chk "I15 a registered domain outside the skill's exists (the scenario has a subject)" "[ -n \"$OUTSIDE\" ]"
run_install install --domains "$OUTSIDE"
chk "I15 the narrowed install exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I15 the deselected skill is gone from both hosts" \
    "[ ! -f \"$CD/skills/$SKILL/SKILL.md\" ] && [ ! -f \"$XD/skills/$SKILL/SKILL.md\" ]"
chk "I15 and was backed up before removal" \
    "ls \"$T\"/home/.local/share/agent-bios/backups/*/\"$CD\"/skills/$SKILL/SKILL.md >/dev/null 2>&1"
chk "I15 the manifest no longer names it" "! grep -q \"skills/$SKILL/\" \"$T/home/.local/share/agent-bios/manifest.txt\""
chk "I15 the user's file inside our directory survived the narrowing" "[ -f \"$CD/skills/$SKILL/notes/mine.md\" ]"
run_install verify
chk "I15 verify passes with the skill deselected and absent" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I15 verify reports the absence as deselected, not as missing" "grep -q 'absent (deselected)' \"$T/log\""
# Plant the deselected skill back on one host — the state a manual copy or an older
# release leaves — and verify must refuse it: a host loading a package the user did not take.
mkdir -p "$XD/skills/$SKILL" && cp "$SKILL_SRC/$SKILL/SKILL.md" "$XD/skills/$SKILL/SKILL.md"
run_install verify
chk "I15 verify FAILS when a deselected skill is still deployed" "[ \$(cat \"$T/rc\") -ne 0 ]"
chk "I15 and names it" "grep -q 'deselected skill still deployed' \"$T/log\""
rm -f "$XD/skills/$SKILL/SKILL.md"; rmdir "$XD/skills/$SKILL" 2>/dev/null || true
run_install install --domains "$(echo $SKILL_DOMAINS | cut -d' ' -f1)"
chk "I15 widening back redeploys the skill to both hosts" \
    "[ -f \"$CD/skills/$SKILL/SKILL.md\" ] && [ -f \"$XD/skills/$SKILL/SKILL.md\" ]"
chk "I15 the manifest names it again" "grep -qxF \"$CD/skills/$SKILL/SKILL.md\" \"$T/home/.local/share/agent-bios/manifest.txt\""

# I13: a release that stops shipping a skill file must not leave it on the host, unowned.
# Simulated by planting a file in the shipped skill, installing (it deploys and is
# manifested), removing it from the source, and installing again: the deployed copy is
# gone, backed up, and the still-shipped SKILL.md is untouched. Planted in the SOURCE tree
# — this is what the scenario is about — and removed by the trap whatever happens.
PLANT="$SKILL_SRC/$SKILL/gate-i13-probe.md"
trap 'rm -f "$PLANT"; rm -rf "$T"' EXIT
printf 'shipped once, then withdrawn\n' > "$PLANT"
run_install install
chk "I13 a newly shipped skill file deploys to both hosts" \
    "[ -f \"$CD/skills/$SKILL/gate-i13-probe.md\" ] && [ -f \"$XD/skills/$SKILL/gate-i13-probe.md\" ]"
rm -f "$PLANT"
run_install install
chk "I13 the reinstall exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I13 the withdrawn file is gone from both hosts" \
    "[ ! -f \"$CD/skills/$SKILL/gate-i13-probe.md\" ] && [ ! -f \"$XD/skills/$SKILL/gate-i13-probe.md\" ]"
chk "I13 and was backed up before removal" \
    "ls \"$T\"/home/.local/share/agent-bios/backups/*/\"$CD\"/skills/$SKILL/gate-i13-probe.md >/dev/null 2>&1"
chk "I13 the still-shipped SKILL.md is untouched" \
    "cmp -s \"$SKILL_SRC/$SKILL/SKILL.md\" \"$CD/skills/$SKILL/SKILL.md\""
chk "I13 the removal is reported" "grep -q 'removed stale skill file' \"$T/log\""
chk "I13 the rebuilt manifest no longer names it" \
    "! grep -q 'gate-i13-probe' \"$T/home/.local/share/agent-bios/manifest.txt\""

# I14: without a manifest, a same-named skill file is removed only when it is OURS —
# byte-identical to the shipped one. A user who authored their own skills/<name>/SKILL.md
# keeps it. The manifest is deleted to reach the fallback; the codex copy is left as
# deployed (identical) and the claude copy is rewritten as the user's.
rm -f "$T/home/.local/share/agent-bios/manifest.txt"
printf 'my own repo-charter skill, not the shipped one\n' > "$CD/skills/$SKILL/SKILL.md"
run_install uninstall
chk "I14 the no-manifest uninstall exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I14 the user's same-named skill file survived" "[ -f \"$CD/skills/$SKILL/SKILL.md\" ]"
chk "I14 and the uninstall said why it was kept" "grep -q 'kept .*differs from the shipped file' \"$T/log\""
chk "I14 the identical (ours) codex copy was removed" "[ ! -f \"$XD/skills/$SKILL/SKILL.md\" ]"
# Restore the deployed state for I12's manifest-backed uninstall below.
run_install install
chk "I14 reinstall for the manifest-backed scenario exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I14 the user's sibling skill and note survived the round trip" \
    "[ -f \"$CD/skills/their-skill/SKILL.md\" ] && [ -f \"$CD/skills/$SKILL/notes/mine.md\" ]"
run_install uninstall
chk "I12 uninstall exits 0" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I12 our skill file is gone from claude" "[ ! -f \"$CD/skills/$SKILL/SKILL.md\" ]"
chk "I12 our skill file is gone from codex" "[ ! -f \"$XD/skills/$SKILL/SKILL.md\" ]"
chk "I12 our codex skill directory is gone (nothing of theirs inside)" "[ ! -d \"$XD/skills/$SKILL\" ]"
chk "I12 the user's file inside our claude skill directory survived" "[ -f \"$CD/skills/$SKILL/notes/mine.md\" ]"
chk "I12 the user's own skill survived on both hosts" \
    "[ -f \"$CD/skills/their-skill/SKILL.md\" ] && [ -f \"$XD/skills/their-skill/SKILL.md\" ]"
chk "I12 the shared skills/ parents were not removed" "[ -d \"$CD/skills\" ] && [ -d \"$XD/skills\" ]"

# I16: the update check. The registry is stubbed by a fake `npm` on PATH, so this
# scenario reaches no network — a test that phoned npmjs would fail in a tunnel and
# would be measuring the registry rather than this code. The stub also lets the
# lookup FAIL on demand, which is the half that matters: an offline machine must
# record its attempt (so it waits out the interval) while announcing nothing.
STUB="$T/stub"; mkdir -p "$STUB"
UPD="$T/home/.local/share/agent-bios/update-check.json"

write_npm_stub() {   # $1: what `npm view <name> version` prints; empty = fail
  if [ -n "${1:-}" ]; then
    printf '#!/bin/sh\n[ "$1" = view ] && { echo "%s"; exit 0; }\nexit 0\n' "$1" > "$STUB/npm"
  else
    printf '#!/bin/sh\nexit 1\n' > "$STUB/npm"
  fi
  chmod +x "$STUB/npm"
}

run_update_check() {  # $1: extra env assignments
  rm -f "$UPD"
  env $(sandbox_env) PATH="$STUB:$PATH" AGENT_BIOS_UPDATE_CHECK=1 ${1:-} bash "$REPO/install.sh" update --check >"$T/log" 2>&1
  echo $? > "$T/rc"
}

write_npm_stub "9.9.9"
run_update_check
chk "I16 a successful lookup writes the cache" "[ -f \"$UPD\" ]"
chk "I16 and records the version the registry gave" \
    "python3 -c \"import json,sys; sys.exit(0 if json.load(open('$UPD')).get('latest')=='9.9.9' else 1)\""
chk "I16 and records what is installed, so the comparison has two sides" \
    "python3 -c \"import json,sys; sys.exit(0 if json.load(open('$UPD')).get('current') else 1)\""

# The failing half. `latest` must be ABSENT rather than empty or stale: the launcher
# reads absence as 'asked, no answer' and says nothing, where a stale value would
# announce an upgrade that may not exist.
write_npm_stub ""
run_update_check
chk "I16 a failed lookup still records the attempt" "[ -f \"$UPD\" ]"
chk "I16 and leaves out latest rather than inventing one" \
    "python3 -c \"import json,sys; sys.exit(0 if 'latest' not in json.load(open('$UPD')) else 1)\""
chk "I16 and does not fail the command over an unreachable registry" "[ \$(cat \"$T/rc\") -eq 0 ]"

# The opt-out has to reach the writer, not merely the help text.
write_npm_stub "9.9.9"
run_update_check "AGENT_BIOS_UPDATE_CHECK=0"
chk "I16 the opt-out writes no cache at all" "[ ! -f \"$UPD\" ]"
chk "I16 and says why rather than going quiet" \
    "grep -q 'update check disabled' \"$T/log\""

# I17: the corpus-status projection is required, and the npm layout degrades honestly.
#
# The defect this pins: `compose/corpus-state.py` was not in the package, install.sh
# discarded the command's stderr AND exit status, and printed one guessed note for every
# failure. A real npm install then rewrote the corpus, passed verification, exited 0, and
# left corpus-status.json describing a PREVIOUS deployment — which is what the launcher's
# panel reads. Two separate silences, so two separate cases below.
UPD_HOME="$T/i17home"; mkdir -p "$UPD_HOME"
BLOCKED="$T/i17blocked"; mkdir -p "$BLOCKED"; chmod 500 "$BLOCKED"

run_i17() {   # $1: extra env
  rm -rf "$UPD_HOME"; mkdir -p "$UPD_HOME"
  env HOME="$UPD_HOME" ZDOTDIR="$UPD_HOME" CLAUDE_CONFIG_DIR="$UPD_HOME/.claude" \
      CODEX_HOME="$UPD_HOME/.codex" AGENT_BIOS_IN_INSTALL_TEST=1 ${1:-} \
      AGENT_LAUNCH_VENV="$UPD_HOME/.local/share/agent-launch/venv" \
      bash "$REPO/install.sh" install >"$T/log" 2>&1
  echo $? > "$T/rc"
}

run_i17 "AGENT_BIOS_CORPUS_STATUS=$BLOCKED/status.json"
chk "I17 an unwritable corpus status fails the install" "[ \$(cat \"$T/rc\") -ne 0 ]"
chk "I17 and names the projection rather than guessing a cause" \
    "grep -q 'corpus-status projection FAILED' \"$T/log\""
chk "I17 and does not also say Done" "! grep -q '^Done\.' \"$T/log\""
# The manifest must still describe what IS deployed: returning at the projection would
# fire the EXIT trap and restore the PREVIOUS manifest, leaving the new corpus on disk
# under the old record — the split state this whole check exists to prevent.
chk "I17 and the manifest still records the deployment" \
    "[ -s \"$UPD_HOME/.local/share/agent-bios/manifest.txt\" ]"

run_i17
chk "I17 a writable destination installs cleanly" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I17 and the status file is there" \
    "[ -f \"$UPD_HOME/.local/share/agent-bios/corpus-status.json\" ]"
chmod 700 "$BLOCKED"

# The npm layout: a tree with the shipped compose/ and no author registries. The domain
# half must be real and the version half must say it cannot know — null, never 0, because
# a fabricated zero is indistinguishable from a real count.
NPM="$T/i17npm"; mkdir -p "$NPM/compose"
cp "$REPO/compose/domains.json" "$REPO/compose/corpus-state.py" "$REPO/compose/assemble.py" "$NPM/compose/"
env AGENT_BIOS_CORPUS_STATUS="$NPM/status.json" python3 "$NPM/compose/corpus-state.py" \
    project --repo "$NPM" >"$T/log" 2>&1
echo $? > "$T/rc"
chk "I17 project succeeds with no author registries" "[ \$(cat \"$T/rc\") -eq 0 ]"
chk "I17 and reports version/ledger as unknown, not as zero" \
    "python3 -c \"import json,sys; d=json.load(open('$NPM/status.json')); sys.exit(0 if d['versions'] is None and d['summary'] is None else 1)\""
chk "I17 and still projects real domains" \
    "python3 -c \"import json,sys; d=json.load(open('$NPM/status.json')); sys.exit(0 if d['domains']['available'] else 1)\""
env AGENT_BIOS_CORPUS_STATUS="$NPM/status.json" python3 "$NPM/compose/corpus-state.py" \
    list --repo "$NPM" >"$T/log" 2>&1
chk "I17 list refuses by name instead of dying on a missing file" \
    "grep -q 'not part of a packaged install' \"$T/log\""

# I18: the SECOND silence. The projection and the apply-record were two different
# `>/dev/null 2>&1` sites, so one fixture cannot prove both — a run whose projection
# succeeds can still lose the record of WHICH selection was applied, and used to print a
# completed-onboarding summary over exactly that. The canary stub here succeeds (it echoes
# the bundle's real rev marker, so the canary takes its pass branch) and deletes the status
# file on its way out, which is the only way to reach record-apply with nothing to record
# into without also breaking the projection.
S18="$T/home/.local/share/agent-bios/corpus-status.json"
BUNDLE18="$T/home/.claude/central/bundle.md"
mkdir -p "$T/stubbin18"
cat > "$T/stubbin18/claude" <<STUB
#!/usr/bin/env bash
rev="\$(grep -m1 '^agent-bios-bundle-rev: ' "$BUNDLE18" 2>/dev/null)"
rm -f "$S18"
printf '%s\n' "\$rev"
STUB
chmod +x "$T/stubbin18/claude"
env $(sandbox_env) PATH="$T/stubbin18:$PATH" \
  bash "$REPO/install.sh" onboard --domains office-work >"$T/log18" 2>&1
echo $? > "$T/rc18"
chk "I18 a lost apply-record fails the onboarding" "[ \$(cat \"$T/rc18\") -ne 0 ]"
chk "I18 and says the outcome could not be recorded" \
    "grep -q 'recording that outcome failed' \"$T/log18\""
# Positive control on the FIXTURE, not the code: without it the two assertions above
# could both pass because the canary failed first, which is I9's case and proves nothing
# about the apply-record. This one says the run really did reach the success path.
chk "I18 and the run reached record-apply through a PASSING canary" \
    "grep -q 'CANARY PASS' \"$T/log18\""
chk "I18 and no status is fabricated to paper over the loss" \
    "! [ -f \"$S18\" ] || python3 -c \"import json,sys; s=json.load(open('$S18')); sys.exit(0 if (s.get('last_apply') or {}).get('outcome')!='applied' else 1)\""

chk "I19 child installs and purge preserve the inherited parent venv" \
    "[ -f \"$OUTER_VENV/keep\" ] && grep -qx 'parent environment sentinel' \"$OUTER_VENV/keep\""

echo
if [ $fail -eq 0 ]; then echo "INSTALL GUIDE TESTS OK"; else echo "INSTALL GUIDE TESTS FAIL"; exit 1; fi
