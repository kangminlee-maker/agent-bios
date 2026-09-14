#!/usr/bin/env bash
# End-to-end assembler scenarios against throwaway dirs. Exit 0 iff all pass.
# S1 selection filtering + rewrites; S2 idempotent re-run + selection change;
# S3 legacy entry migration; S4 user entry protection (exit 2, untouched);
# S5 codex personal region survives; S6 unknown domain rejected.
set -u
cd "$(dirname "$0")/.."
T=$(mktemp -d "${TMPDIR:-/tmp}/asm-test-XXXXXX") || exit 1
[ -n "$T" ] && [ -d "$T" ] || { echo "FAIL: no test directory"; exit 1; }
trap 'rm -rf "$T"' EXIT
OUTER_VENV="$T/inherited-venv"
mkdir -p "$OUTER_VENV"
printf '%s\n' 'parent environment sentinel' > "$OUTER_VENV/keep"
export AGENT_LAUNCH_VENV="$OUTER_VENV"
CD="$T/claude"; XD="$T/codex"; SD="$T/state"
fail=0; chk(){ if eval "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; fail=1; fi; }
asm(){ python3 compose/assemble.py --claude-dir "$3" --codex-dir "$4" --state-dir "$5" --domains "$2" >"$T/out" 2>&1; echo $? > "$T/rc"; sed -n '1,3p' "$T/out"; }

# How many of KIND a selection should deliver. The tier contract is stated HERE rather than
# imported: an oracle that shares the predicate under test cannot see a bug in that predicate.
# Import the assembler's own selection predicate and a change to it moves the output and the
# expectation by the same amount — drop the universal tier and both shrink by exactly the core
# count, so the suite stays green over an empty answer. A typed count rots; a borrowed
# predicate is worse, because it fails silently in the direction that matters.
#
# author_only STAYS imported: it reads a declaration rather than deciding selection, and the
# withheld/delivered contrast pair in S1 is its control. The tier registry is compared against
# what this oracle knows, so a tier added to the manifest fails here instead of being guessed.
expect_delivered(){ python3 - "$1" "$2" <<'EXPECT_PY'
import json, pathlib, sys
sys.path.insert(0, "compose")
from assemble import author_only

UNIVERSAL, NEVER, PER_DOMAIN = {"core", "infra"}, {"env-personal"}, {"domain"}

def delivers(entry, sel):
    tier = entry.get("tier")
    if tier in UNIVERSAL:
        return True
    if tier in NEVER:
        return False
    if tier in PER_DOMAIN:
        return bool(set(entry.get("domains") or []) & sel)
    raise SystemExit(f"oracle: unknown tier {tier!r}; this contract is stale")

kind, sel = sys.argv[1], set(sys.argv[2].split(",")) - {""}
m = json.load(open("compose/domains.json"))
declared = set(m.get("tiers", []))
known = UNIVERSAL | NEVER | PER_DOMAIN
if declared != known:
    raise SystemExit(f"oracle: manifest declares tiers {sorted(declared)}, oracle knows "
                     f"{sorted(known)} — the contract moved and this expectation is stale")
section = m[kind]
if kind == "bullets":                      # the only section stored as a list
    n = sum(1 for e in section if delivers(e, sel))
else:
    src = pathlib.Path("claude") / kind
    for name in section:
        if kind != "guides" and (src / name).is_file() and author_only(src / name):
            raise SystemExit(f"{kind}/{name} declares audience: author, which assemble.py does "
                             f"not filter — expect_delivered's guides-only rule is now stale")
    n = sum(1 for name, e in section.items()
            if delivers(e, sel) and not (kind == "guides" and author_only(src / name)))
assert n > 0, f"expect_delivered({kind}) derived 0 — a zero expectation passes vacuously"
print(n)
EXPECT_PY
}
# Assigned with the `||` at TOP level, not through a wrapper function: a wrapper called
# inside $( ) exits only the subshell, so a failed derivation would land its error text in
# the variable and let the suite run on.
BB_GUIDES=$(expect_delivered guides builder-base) \
  || { echo "FAIL: could not derive guides for builder-base"; exit 1; }
BB_BULLETS=$(expect_delivered bullets builder-base) \
  || { echo "FAIL: could not derive bullets for builder-base"; exit 1; }
BB_MAO_BULLETS=$(expect_delivered bullets builder-base,multi-agent-orchestration) \
  || { echo "FAIL: could not derive bullets for the two-domain selection"; exit 1; }
BB_MAO_AGENTS=$(expect_delivered agents builder-base,multi-agent-orchestration) \
  || { echo "FAIL: could not derive agents for the two-domain selection"; exit 1; }

asm S1 builder-base "$CD" "$XD" "$SD"
chk "S1 exit 0" "[ \$(cat $T/rc) -eq 0 ]"
chk "S1 bullets match the manifest ($BB_BULLETS)" "[ \$(grep -c '^- ' $CD/central/bundle.md) -eq $BB_BULLETS ]"
# A core bullet must survive EVERY selection. Counts alone cannot say this once the
# expectation is derived, and absence contrasts cannot either — dropping the whole
# universal tier satisfies every "is not present" check in this file.
chk "S1 core tier still delivered" "grep -q 'Keep file changes within the requested scope' $CD/central/bundle.md"
chk "S1 env-personal excluded" "! grep -q 'Prefer concise Korean' $CD/central/bundle.md"
chk "S1 unselected domain excluded" "! grep -q 'Use the LLM for semantic work' $CD/central/bundle.md"
chk "S1 guide refs rewritten" "grep -q 'central/guides/coding-staged-workflow.md' $CD/central/bundle.md"
chk "S1 guides count matches the manifest ($BB_GUIDES: builder-base + infra, less author-only)" \
    "[ \$(find $CD/central/guides -maxdepth 1 -type f | wc -l) -eq $BB_GUIDES ]"
# The audience declaration decides delivery, not the tier. Both guides below are
# infra, so tier alone would deliver both — the contrast is what shows the filter
# read the frontmatter rather than dropping a whole tier.
chk "S1 author-only guide withheld" "[ ! -f $CD/central/guides/session-distill-workflow.md ]"
chk "S1 the other infra guide still delivered" "[ -f $CD/central/guides/learning-flow.md ]"
chk "S1 author-only guide withheld on the codex side too" "[ ! -f $XD/guides/session-distill-workflow.md ]"
# The line above is an ABSENCE, which an empty codex guides directory would also
# satisfy — deleting the codex copy step entirely would pass it while breaking
# every ordinary codex guide. The positive contrast is what gives it a subject.
chk "S1 codex guides are delivered at all" "[ -f $XD/guides/learning-flow.md ]"
chk "S1 the withholding is reported, not silent" "grep -q 'withheld 1 author-only guide' $T/out"
chk "S1 hook copied" "[ -f $CD/central/hooks/tooling-gotchas-hook.py ]"
chk "S1 entry seeded" "grep -q '@central/bundle.md' $CD/CLAUDE.md"
chk "S1 personal import seeded" "grep -q '@personal/learnings.md' $CD/CLAUDE.md"
chk "S1 personal learnings file seeded" "[ -f $CD/personal/learnings.md ]"
chk "S1 settings central hook" "grep -q 'central/hooks/tooling-gotchas-hook.py' $CD/settings.json"
chk "S1 codex markers" "grep -q 'agent-bios:central:start' $XD/AGENTS.md"
chk "S1 no codex-only bullet w/o orchestration" "! grep -q 'Codex-only standing authorization' $XD/AGENTS.md"
# Contrast for the review-independence rule: absent without orchestration, present
# with it. A bullet count alone moves for any edit; this proves the CONTENT routed.
chk "S1 no review-independence rule w/o orchestration" "! grep -q 'how much independence it actually bought' $CD/central/bundle.md"
chk "S1 review guide excluded w/o orchestration" "[ ! -f $CD/central/guides/cli-multi-model-workflow.md ]"
chk "S1 codex var swapped" "grep -q 'CODEX_HOME' $XD/AGENTS.md && ! grep -q 'CLAUDE_CONFIG_DIR' $XD/AGENTS.md"

asm S2 builder-base,multi-agent-orchestration "$CD" "$XD" "$SD"
chk "S2 bullets match the manifest ($BB_MAO_BULLETS)" "[ \$(grep -c '^- ' $CD/central/bundle.md) -eq $BB_MAO_BULLETS ]"
chk "S2 core tier still delivered" "grep -q 'Keep file changes within the requested scope' $CD/central/bundle.md"
chk "S2 agents match the manifest ($BB_MAO_AGENTS)" "[ \$(ls $CD/central/agents | wc -l) -eq $BB_MAO_AGENTS ]"
chk "S2 codex-only bullet present" "grep -q 'Codex-only standing authorization' $XD/AGENTS.md"
chk "S2 review-independence rule present" "grep -q 'how much independence it actually bought' $CD/central/bundle.md"
chk "S2 review guide carries the grade ladder" "grep -q 'perspective_floor' $CD/central/guides/cli-multi-model-workflow.md"
chk "S2 isolation is a gate not a rung" "grep -q 'Isolation is a gate, not a rung' $CD/central/guides/cli-multi-model-workflow.md"
chk "S2 codex mirror carries it too" "grep -q 'how much independence it actually bought' $XD/AGENTS.md"
chk "S2 markers unique" "[ \$(grep -c 'agent-bios:central:start' $XD/AGENTS.md) -eq 1 ]"
chk "S2 settings hook unique" "[ \$(grep -c 'central/hooks/tooling-gotchas-hook.py' $CD/settings.json) -eq 1 ]"

T2="$T/legacy"; mkdir -p "$T2/claude"; cp claude/CLAUDE.md "$T2/claude/CLAUDE.md"
asm S3 builder-base "$T2/claude" "$T2/codex" "$T2/state"
chk "S3 legacy replaced by seed" "grep -q '@central/bundle.md' $T2/claude/CLAUDE.md"
chk "S3 legacy backup kept" "ls $T2/claude/*.bak-legacy-* >/dev/null 2>&1"

# S3b is the ACTUAL upgrade input, which S3 misses: someone on an EARLIER release has that
# release's monolith on disk, so it does not byte-match this one. Recognizing legacy by content
# alone reported our own file as the user's, and the instructions never loaded until they edited it.
# Ownership comes from the previous install's manifest — the record of what we deployed.
T2b="$T/upgrade"; mkdir -p "$T2b/claude" "$T2b/state"
printf '# CLAUDE.md\n\n## Global Preferences\n\n- an earlier release, not this one\n' \
  > "$T2b/claude/CLAUDE.md"
printf '%s\n' "$T2b/claude/CLAUDE.md" > "$T2b/state/manifest.prev.txt"
python3 compose/assemble.py --claude-dir "$T2b/claude" --codex-dir "$T2b/codex" \
  --state-dir "$T2b/state" --domains builder-base \
  --prior-manifest "$T2b/state/manifest.prev.txt" >"$T/out" 2>&1; echo $? > "$T/rc"
chk "S3b upgrade from an earlier release exits 0" "[ \$(cat $T/rc) -eq 0 ]"
chk "S3b the earlier monolith is replaced by the seed" \
    "grep -q '@central/bundle.md' $T2b/claude/CLAUDE.md"
chk "S3b and it was backed up first" "ls $T2b/claude/*.bak-legacy-* >/dev/null 2>&1"
# The other direction, which is the one that must never break: a file we never deployed stays
# theirs even when a prior manifest exists. Without this, "recognize more things as ours"
# passes S3b by simply rewriting everything.
T2c="$T/notours"; mkdir -p "$T2c/claude" "$T2c/state"
echo "# genuinely mine" > "$T2c/claude/CLAUDE.md"
printf '%s\n' "$T2c/claude/central/guides/x.md" > "$T2c/state/manifest.prev.txt"
python3 compose/assemble.py --claude-dir "$T2c/claude" --codex-dir "$T2c/codex" \
  --state-dir "$T2c/state" --domains builder-base \
  --prior-manifest "$T2c/state/manifest.prev.txt" >"$T/out" 2>&1; echo $? > "$T/rc"
# The exit code alone is not enough: a python that cannot start also exits 2, and this
# assertion passed that way once while proving nothing. The message is what distinguishes
# "refused on purpose" from "never ran".
chk "S3c a file the manifest does not claim stays the user's" \
    "[ \$(cat $T/rc) -eq 2 ] && grep -q 'ACTION NEEDED' $T/out"
chk "S3c and its contents are untouched" \
    "[ \"\$(cat $T2c/claude/CLAUDE.md)\" = '# genuinely mine' ]"

T3="$T/user"; mkdir -p "$T3/claude"; echo "# my own rules" > "$T3/claude/CLAUDE.md"
asm S4 builder-base "$T3/claude" "$T3/codex" "$T3/state"
chk "S4 exit 2 (needs action)" "[ \$(cat $T/rc) -eq 2 ]"
chk "S4 user file untouched" "[ \"\$(cat $T3/claude/CLAUDE.md)\" = '# my own rules' ]"

printf '\n## Personal\n- my personal codex rule\n' >> "$XD/AGENTS.md"
asm S5 builder-base "$CD" "$XD" "$SD"
chk "S5 personal codex rule survived" "grep -q 'my personal codex rule' $XD/AGENTS.md"
chk "S5 central region refreshed to $BB_BULLETS" "[ \$(grep -c '^- ' $CD/central/bundle.md) -eq $BB_BULLETS ]"

asm S6 no-such-domain "$CD" "$XD" "$SD"
chk "S6 unknown domain exit 1" "[ \$(cat $T/rc) -eq 1 ]"

# S6b: NARROWING a selection. Every other scenario widens or keeps it, and writing the
# selected files is all a widening needs — so nothing here noticed that a narrowed selection
# left the dropped files on disk, and selection.json stopped describing the deploy.
T4="$T/narrow"; mkdir -p "$T4"
ALLD=$(python3 -c "import json;print(','.join(sorted(json.load(open('compose/domains.json'))['domains'])))")
asm S6b "$ALLD" "$T4/claude" "$T4/codex" "$T4/state"
wide_g=$(find "$T4/claude/central/guides" -maxdepth 1 -type f | wc -l); wide_a=$(ls "$T4/claude/central/agents" | wc -l)
chk "S6b every domain deploys more than builder-base alone" "[ $wide_g -gt $BB_GUIDES ] && [ $wide_a -gt 0 ]"
# A file of theirs in the same directory. Ownership is the source tree, not the directory,
# and without this the fix could pass by emptying the directory instead of reconciling it.
echo "my own note" > "$T4/claude/central/guides/my-notes.md"
asm S6b2 builder-base "$T4/claude" "$T4/codex" "$T4/state"
chk "S6b narrowing drops the deselected guides" \
    "[ \$(find $T4/claude/central/guides -maxdepth 1 -type f | wc -l) -eq $((BB_GUIDES + 1)) ]"
chk "S6b narrowing drops the deselected agents" \
    "[ \$(ls $T4/claude/central/agents 2>/dev/null | wc -l) -eq 0 ]"
chk "S6b the codex side is reconciled too" \
    "[ \$(find $T4/codex/guides -maxdepth 1 -type f | wc -l) -eq $BB_GUIDES ]"
chk "S6b a file we never deployed is left alone" "[ -f $T4/claude/central/guides/my-notes.md ]"
chk "S6b what was removed was backed up first" \
    "[ \$(find $T4/state/backups -path '*deselected*' -name '*.md' | wc -l) -gt 0 ]"
chk "S6b the removal is reported, not silent" "grep -q 'deselected, removed' $T/out"

# S6c: REPLACING is as destructive as removing, and README promises a copy of the exact prior
# bytes. install.sh's deploy_file kept that promise; the assembler is the default path now and
# wrote straight over whatever was there, including a guide the user had edited.
T5="$T/replace"; mkdir -p "$T5"
asm S6c builder-base "$T5/claude" "$T5/codex" "$T5/state"
chk "S6c a first install backs nothing up" \
    "[ \$(find $T5/state/backups -type f 2>/dev/null | wc -l) -eq 0 ]"
echo "EDITED BY THE USER" >> "$T5/codex/guides/learning-flow.md"
asm S6c2 builder-base "$T5/claude" "$T5/codex" "$T5/state"
chk "S6c replacing an edited guide keeps the prior bytes" \
    "grep -rq 'EDITED BY THE USER' $T5/state/backups"
chk "S6c and it is filed under replaced, not deselected" \
    "[ \$(find $T5/state/backups -path '*replaced*' -type f | wc -l) -ge 1 ]"
# Without this, "back up before writing" fills the backup directory on every no-op reinstall —
# which is the churn compose/prune-backups.py exists because of.
n_before=$(find "$T5/state/backups" -type f | wc -l)
asm S6c3 builder-base "$T5/claude" "$T5/codex" "$T5/state"
chk "S6c an unchanged rewrite backs nothing up" \
    "[ \$(find $T5/state/backups -type f | wc -l) -eq $n_before ]"

# S7: every merge into a file we do not own needs a matching removal, and the removal must not
# reach past what the merge wrote. A merge-only span leaves the harness invoking deleted files
# after a successful uninstall, which is what this asserts against.
python3 - "$CD" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "settings.json"
s = json.loads(p.read_text()) if p.exists() else {}
s.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
    {"matcher": "Edit", "hooks": [{"type": "command", "command": "someone-elses-tool"}]})
p.write_text(json.dumps(s, indent=2))
PY
python3 compose/assemble.py --remove-owned --claude-dir "$CD" --codex-dir "$XD" --state-dir "$SD" >/dev/null
chk "S7 our hook registration removed" "! grep -q 'central/hooks' $CD/settings.json"
chk "S7 another tool's hook kept" "grep -q 'someone-elses-tool' $CD/settings.json"
chk "S7 codex central region removed" "! grep -q 'agent-bios:central:start' $XD/AGENTS.md"
chk "S7 personal codex rule still survives" "grep -q 'my personal codex rule' $XD/AGENTS.md"
# S8: withholding must also REMOVE what an earlier install deployed. The manifest
# is rebuilt from the current deploy, so a file that stops being deployed stops
# being tracked — not rewriting it would leave it there for good. Every other
# scenario starts from an empty mktemp dir and so could never see this.
T8="$T/stale"; mkdir -p "$T8/claude/central/guides" "$T8/codex/guides"
cp claude/guides/session-distill-workflow.md "$T8/claude/central/guides/"
cp codex/guides/session-distill-workflow.md "$T8/codex/guides/"
asm S8 builder-base "$T8/claude" "$T8/codex" "$T8/state"
chk "S8 exit 0" "[ \$(cat $T/rc) -eq 0 ]"
chk "S8 stale claude copy removed" "[ ! -f $T8/claude/central/guides/session-distill-workflow.md ]"
chk "S8 stale codex copy removed" "[ ! -f $T8/codex/guides/session-distill-workflow.md ]"
chk "S8 the removal is reported" "grep -q 'remove withheld' $T/out"
chk "S8 an ordinary guide is still written" "[ -f $T8/claude/central/guides/learning-flow.md ]"


# S9: an AGENTS.md the user wrote, with no markers and no deployment record, is theirs.
# "Missing marker pair" used to mean "legacy whole-file deploy", so the first install replaced
# the active body of every Codex user who had written one. A backup made it recoverable; nothing
# made it noticed. Absence of a marker is absence of evidence, in both directions — so the
# evidence is the prior manifest, exactly as seed_entry reads it on the Claude side.
T9="$T/markerless"; mkdir -p "$T9/claude" "$T9/codex" "$T9/state"
printf '## My Codex Rules\nKEEP-MY-RULE\n' > "$T9/codex/AGENTS.md"
asm S9 builder-base "$T9/claude" "$T9/codex" "$T9/state"
chk "S9 exit 0" "[ \$(cat $T/rc) -eq 0 ]"
chk "S9 the user's own AGENTS.md text is still ACTIVE, not only backed up" \
    "grep -q 'KEEP-MY-RULE' $T9/codex/AGENTS.md"
chk "S9 and the central region was adopted alongside it" \
    "grep -q 'agent-bios:central:start' $T9/codex/AGENTS.md"
# The control: the same file named by a PRIOR manifest is ours by record, and replacing it
# with the marked shape is the upgrade. Without this, "never replace" would satisfy S9 too.
T9B="$T/markerless-ours"; mkdir -p "$T9B/claude" "$T9B/codex" "$T9B/state"
printf '## My Codex Rules\nKEEP-MY-RULE\n' > "$T9B/codex/AGENTS.md"
printf '%s\n' "$T9B/codex/AGENTS.md" > "$T9B/state/manifest.prev.txt"
python3 compose/assemble.py --claude-dir "$T9B/claude" --codex-dir "$T9B/codex" \
  --state-dir "$T9B/state" --domains builder-base \
  --prior-manifest "$T9B/state/manifest.prev.txt" >"$T/out" 2>&1; echo $? > "$T/rc"
chk "S9 exit 0 (ours by record)" "[ \$(cat $T/rc) -eq 0 ]"
chk "S9 a file the PRIOR MANIFEST names is replaced with the marked shape" \
    "! grep -q 'KEEP-MY-RULE' $T9B/codex/AGENTS.md"
chk "S9 and that replacement leaves a backup" \
    "ls $T9B/codex/AGENTS.md.bak-legacy-* >/dev/null 2>&1"

# S10: settings ownership is a name on ONE command, so removal is per hook. An entry holding
# ours beside the user's answered "ours" and took theirs with it.
T10="$T/shared-entry"; mkdir -p "$T10/claude" "$T10/codex" "$T10/state"
cat > "$T10/claude/settings.json" <<'JSON'
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
  {"type": "command", "command": "python3 /old/hooks/tooling-gotchas-hook.py"},
  {"type": "command", "command": "python3 /home/me/hooks/MY-OWN-HOOK.py"}]}]}}
JSON
asm S10 builder-base "$T10/claude" "$T10/codex" "$T10/state"
chk "S10 exit 0" "[ \$(cat $T/rc) -eq 0 ]"
chk "S10 the user's hook sharing an entry with ours survives" \
    "grep -q 'MY-OWN-HOOK.py' $T10/claude/settings.json"
chk "S10 and ours is registered exactly once, at its current path" \
    "[ \$(grep -c 'central/hooks/tooling-gotchas-hook.py' $T10/claude/settings.json) -eq 1 ]"
chk "S10 the stale old-path registration is gone" \
    "! grep -q '/old/hooks/tooling-gotchas-hook.py' $T10/claude/settings.json"
# S11: a config home with a space in it must still be idempotent. The registration is
# shlex.quote'd so such a home works at all, and the quote lands right after the filename —
# so a matcher wanting end-of-string or a following space could not recognize the line it
# had just written, and every reinstall appended another copy. The plain-home run beside it
# is the control: without it, "one registration" would pass on a matcher that matches
# nothing at all, because the re-add would still put exactly one in.
T11="$T/spaced home"; mkdir -p "$T11/claude" "$T11/codex" "$T11/state"
asm S11 builder-base "$T11/claude" "$T11/codex" "$T11/state"
asm S11 builder-base "$T11/claude" "$T11/codex" "$T11/state"
chk "S11 exit 0 on a config home containing a space" "[ \$(cat $T/rc) -eq 0 ]"
chk "S11 two installs leave exactly one registration" \
    "[ \$(grep -c 'central/hooks/tooling-gotchas-hook.py' \"$T11/claude/settings.json\") -eq 1 ]"
T11B="$T/plainhome"; mkdir -p "$T11B/claude" "$T11B/codex" "$T11B/state"
asm S11 builder-base "$T11B/claude" "$T11B/codex" "$T11B/state"
asm S11 builder-base "$T11B/claude" "$T11B/codex" "$T11B/state"
chk "S11 and so do two installs on a home without one" \
    "[ \$(grep -c 'central/hooks/tooling-gotchas-hook.py' $T11B/claude/settings.json) -eq 1 ]"

# S12: guide bundles have one manifest key but several exact deployed members.  Start wide so
# slide-writing is selected, then narrow it away: only the source-owned paths may be removed.
# A user note nested beside an owned script is the contrast for a tempting `rm -r` cleanup.
T12="$T/guide-bundle"; mkdir -p "$T12"
asm S12 "$ALLD" "$T12/claude" "$T12/codex" "$T12/state"
chk "S12 slide-writing primary guide is delivered" \
    "[ -f $T12/claude/central/guides/slide-writing.md ] && [ -f $T12/codex/guides/slide-writing.md ]"
chk "S12 nested Markdown companion is delivered" \
    "[ -f $T12/claude/central/guides/slide-writing/RUNBOOK.md ] && [ -f $T12/codex/guides/slide-writing/RUNBOOK.md ]"
chk "S12 immutable companion code stays byte-identical across assembled hosts" \
    "cmp -s claude/guides/slide-writing/scripts/pair.py $T12/claude/central/guides/slide-writing/scripts/pair.py && cmp -s claude/guides/slide-writing/scripts/pair.py $T12/codex/guides/slide-writing/scripts/pair.py"
mkdir -p "$T12/claude/central/guides/slide-writing/scripts"
printf 'my nested note\n' > "$T12/claude/central/guides/slide-writing/scripts/user-note.txt"
printf 'EDITED RUNBOOK\n' >> "$T12/claude/central/guides/slide-writing/RUNBOOK.md"
asm S12b builder-base "$T12/claude" "$T12/codex" "$T12/state"
chk "S12 narrowing removes the primary and every exact owned nested member" \
    "[ ! -f $T12/claude/central/guides/slide-writing.md ] && [ ! -f $T12/claude/central/guides/slide-writing/RUNBOOK.md ] && [ ! -f $T12/claude/central/guides/slide-writing/scripts/pair.py ] && [ ! -f $T12/codex/guides/slide-writing.md ] && [ ! -f $T12/codex/guides/slide-writing/scripts/pair.py ]"
chk "S12 narrowing leaves a user-created nested file alone" \
    "[ -f $T12/claude/central/guides/slide-writing/scripts/user-note.txt ]"
chk "S12 deselecting an edited nested member backs it up first" \
    "grep -rq 'EDITED RUNBOOK' $T12/state/backups"

# S13/S14: the bundle destination itself is user-configured, but no member may cross a
# symlink BELOW that root.  A leaf-only check misses both shapes because the leaf it reaches
# is a normal file outside the selected guide tree.  Each failure must occur before the
# selected primary is replaced or the deselected primary is removed.
T13="$T/bundle-symlink-selected"; mkdir -p "$T13/claude/central/guides" "$T13/outside"
printf 'FOREIGN PRIMARY\n' > "$T13/claude/central/guides/slide-writing.md"
printf 'OUTSIDE SELECTED SENTINEL\n' > "$T13/outside/RUNBOOK.md"
ln -s "$T13/outside" "$T13/claude/central/guides/slide-writing"
SOURCE_PAIR_SUM=$(shasum -a 256 claude/guides/slide-writing/scripts/pair.py | awk '{print $1}')
asm S13 "$ALLD" "$T13/claude" "$T13/codex" "$T13/state"
chk "S13 selected bundle through a nested symlink is refused before any member write" \
    "[ \$(cat $T/rc) -eq 1 ] && grep -q 'ancestor symlink' $T/out && grep -q 'FOREIGN PRIMARY' $T13/claude/central/guides/slide-writing.md && grep -q 'OUTSIDE SELECTED SENTINEL' $T13/outside/RUNBOOK.md && [ \"$SOURCE_PAIR_SUM\" = \"\$(shasum -a 256 claude/guides/slide-writing/scripts/pair.py | awk '{print \$1}')\" ]"

T14="$T/bundle-symlink-deselected"; mkdir -p "$T14"
asm S14 "$ALLD" "$T14/claude" "$T14/codex" "$T14/state"
mv "$T14/claude/central/guides/slide-writing/scripts" "$T14/original-scripts"
mkdir -p "$T14/outside"
printf 'OUTSIDE DESELECTED SENTINEL\n' > "$T14/outside/pair.py"
ln -s "$T14/outside" "$T14/claude/central/guides/slide-writing/scripts"
asm S14b builder-base "$T14/claude" "$T14/codex" "$T14/state"
chk "S14 deselecting through a nested symlink is refused before removing owned siblings" \
    "[ \$(cat $T/rc) -eq 1 ] && grep -q 'ancestor symlink' $T/out && [ -f $T14/claude/central/guides/slide-writing.md ] && grep -q 'OUTSIDE DESELECTED SENTINEL' $T14/outside/pair.py && [ \"$SOURCE_PAIR_SUM\" = \"\$(shasum -a 256 claude/guides/slide-writing/scripts/pair.py | awk '{print \$1}')\" ]"

# S15: source release A has a companion member; release B removes only that member while
# retaining the guide.  Historic manifests over-claimed files below a guide root, so B must
# leave every prior-only path in place — including the genuinely old pair.py — and disclose
# the manual-inspection path rather than treat manifest membership as deletion authority.
# The fixture is a private package copy: changing its B source cannot touch this checkout.
T15="$T/withdrawn-member"; P15="$T15/package"; mkdir -p "$T15"
python3 gates/fixture_support.py "$PWD" "$P15" || exit 1
fixture_asm(){ python3 "$P15/compose/assemble.py" --claude-dir "$2" --codex-dir "$3" --state-dir "$4" --domains "$1" ${5:+--prior-manifest "$5"} >"$T/out" 2>&1; echo $? > "$T/rc"; }
fixture_asm "$ALLD" "$T15/claude" "$T15/codex" "$T15/state"
printf 'user sibling\n' > "$T15/claude/central/guides/slide-writing/scripts/user-note.txt"
printf 'top-level user note\n' > "$T15/claude/central/guides/my-notes.md"
printf 'OUTSIDE PRIOR SENTINEL\n' > "$T15/outside-prior.txt"
cat > "$T15/prior-manifest.txt" <<EOF
$T15/claude/central/guides/slide-writing/scripts/pair.py
$T15/codex/guides/slide-writing/scripts/pair.py
$T15/claude/central/guides/slide-writing/scripts/user-note.txt
$T15/claude/central/guides/my-notes.md
$T15/outside-prior.txt
relative-not-owned
$T15/claude/central/guides/slide-writing/scripts/../../outside-prior.txt
EOF
# A prior manifest is text, not a parser boundary.  An embedded NUL is malformed ownership
# evidence and must be ignored rather than reaching pathlib/filesystem operations.
printf 'broken\0prior-record\n' >> "$T15/prior-manifest.txt"
mv "$P15/claude/guides/slide-writing/scripts/pair.py" "$T15/release-a-claude-pair.py"
mv "$P15/codex/guides/slide-writing/scripts/pair.py" "$T15/release-a-codex-pair.py"
fixture_asm "$ALLD" "$T15/claude" "$T15/codex" "$T15/state" "$T15/prior-manifest.txt"
chk "S15 B preserves prior-only members and names them for manual inspection" \
    "[ \$(cat $T/rc) -eq 0 ] && cmp -s $T15/release-a-claude-pair.py $T15/claude/central/guides/slide-writing/scripts/pair.py && cmp -s $T15/release-a-codex-pair.py $T15/codex/guides/slide-writing/scripts/pair.py && grep -q 'prior guide remnant left in place.*pair.py' $T/out && grep -q 'inspect it and remove it manually' $T/out"
chk "S15 historic top-level/nested overclaims and malformed/out-of-root rows do not expand deletion" \
    "[ -f $T15/claude/central/guides/slide-writing.md ] && [ -f $T15/claude/central/guides/slide-writing/RUNBOOK.md ] && grep -q 'user sibling' $T15/claude/central/guides/slide-writing/scripts/user-note.txt && grep -q 'top-level user note' $T15/claude/central/guides/my-notes.md && grep -q 'OUTSIDE PRIOR SENTINEL' $T15/outside-prior.txt"
# This is the installer manifest enumerator's exact authority: B's source members that are
# still present on disk.  It excludes pair.py even though the conservative policy leaves it
# in place, which pins the disclosed limitation rather than pretending the remnant is owned.
python3 - "$P15" "$T15/claude/central/guides" "$T15/codex/guides" > "$T15/manifest-b.txt" <<'PY'
import pathlib, sys
repo, claude_dest, codex_dest = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(repo / "compose"))
from assemble import guide_member_map
for source, dest in ((repo / "claude" / "guides", claude_dest),
                     (repo / "codex" / "guides", codex_dest)):
    for paths in guide_member_map(source).values():
        for rel in paths:
            if (dest / rel).is_file():
                print(dest / rel)
PY
chk "S15 B's rebuilt manifest excludes prior-only files, including the uncertain old artifact" \
    "! grep -q 'slide-writing/scripts/pair.py\|user-note.txt\|my-notes.md' $T15/manifest-b.txt && grep -q 'slide-writing/RUNBOOK.md' $T15/manifest-b.txt"
# Feed that rebuilt manifest to the real legacy uninstall command.  Its manifest-based
# removal deletes B-owned members but leaves every candidate the assembler disclosed.
mkdir -p "$T15/home/.local/share/agent-bios"
cp "$T15/manifest-b.txt" "$T15/home/.local/share/agent-bios/manifest.txt"
env HOME="$T15/home" ZDOTDIR="$T15/home" CLAUDE_CONFIG_DIR="$T15/claude" CODEX_HOME="$T15/codex" \
  AGENT_LAUNCH_VENV="$T15/home/.local/share/agent-launch/venv" \
  AGENT_BIOS_LEGACY_INSTALL=1 bash "$P15/install.sh" uninstall > "$T15/uninstall.out" 2>&1; echo $? > "$T15/uninstall.rc"
chk "S15 legacy uninstall preserves candidate remnants omitted by B's manifest" \
    "[ \$(cat $T15/uninstall.rc) -eq 0 ] && [ -f $T15/claude/central/guides/slide-writing/scripts/pair.py ] && [ -f $T15/codex/guides/slide-writing/scripts/pair.py ] && [ -f $T15/claude/central/guides/slide-writing/scripts/user-note.txt ] && [ -f $T15/claude/central/guides/my-notes.md ]"
chk "S15 legacy uninstall preserves the inherited parent venv" \
    "[ -f \"$OUTER_VENV/keep\" ] && grep -qx 'parent environment sentinel' \"$OUTER_VENV/keep\""

# S16: a prior-only candidate through a nested link is left alone and disclosed.  B carries
# no current scripts/ member, so this proves candidates are not preflighted as write/delete
# targets; the external sentinel remains untouched.
T16="$T/withdrawn-member-symlink"; P16="$T16/package"; mkdir -p "$T16"
python3 gates/fixture_support.py "$PWD" "$P16" || exit 1
fixture_asm16(){ python3 "$P16/compose/assemble.py" --claude-dir "$2" --codex-dir "$3" --state-dir "$4" --domains "$1" ${5:+--prior-manifest "$5"} >"$T/out" 2>&1; echo $? > "$T/rc"; }
fixture_asm16 "$ALLD" "$T16/claude" "$T16/codex" "$T16/state"
mv "$P16/claude/guides/slide-writing/scripts" "$T16/release-a-claude-scripts"
mv "$P16/codex/guides/slide-writing/scripts" "$T16/release-a-codex-scripts"
mv "$T16/claude/central/guides/slide-writing/scripts" "$T16/original-scripts"
mkdir -p "$T16/outside"
printf 'OUTSIDE WITHDRAWN SENTINEL\n' > "$T16/outside/pair.py"
ln -s "$T16/outside" "$T16/claude/central/guides/slide-writing/scripts"
printf '%s\n' "$T16/claude/central/guides/slide-writing/scripts/pair.py" > "$T16/prior-manifest.txt"
fixture_asm16 "$ALLD" "$T16/claude" "$T16/codex" "$T16/state" "$T16/prior-manifest.txt"
chk "S16 a prior-only target through a nested symlink is disclosed without touching its target" \
    "[ \$(cat $T/rc) -eq 0 ] && grep -q 'prior guide remnant left in place.*pair.py' $T/out && [ -f $T16/claude/central/guides/slide-writing.md ] && grep -q 'OUTSIDE WITHDRAWN SENTINEL' $T16/outside/pair.py && cmp -s $T16/release-a-claude-scripts/pair.py $T16/original-scripts/pair.py"

echo
if [ $fail -eq 0 ]; then echo "ASSEMBLE TESTS OK"; else echo "ASSEMBLE TESTS FAIL"; exit 1; fi
