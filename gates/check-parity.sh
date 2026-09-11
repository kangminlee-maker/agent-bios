#!/usr/bin/env bash
# Parity gate for mirrored instruction files.
# EN canonical (installed): claude/, codex/.  KO reference (never installed): ko/claude, ko/codex.
# Checks:
#   (1) codex/ and ko/codex/ hold exactly the projection gates/emit-mirrors.py emits
#       from the claude-side canonical (config-home var, title, declared Codex bullet)
#   (2) EN and KO guide sets match — every English guide has a Korean counterpart
#   (3) every guide referenced by claude/CLAUDE.md exists in both EN guide dirs
#   (4) frontmatter: guide_id matches filename; language matches tree (ko/ => ko, else en); parent resolves
#   (5) anchor phrases: each intentional global↔guide restatement pair shares a fixed anchor
#       phrase in both EN files, so editing one side without the other fails here
#   (6) launch-profile, Codex role-slot, and wrapper defaults match runtime projections
# Exit non-zero on any divergence. Run from the repo root; safe as a pre-commit hook.
set -u
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"   # resolved BEFORE the cd below
cd "$(dirname "$0")/.."
fail=0

# Non-empty-subject guards: a parity check over missing inputs must fail, not pass vacuously.
for p in claude/guides codex/guides ko/claude/guides ko/codex/guides; do
  [ -d "$p" ] || { echo "FAIL: required dir missing: $p"; exit 1; }
done
for p in claude/CLAUDE.md codex/AGENTS.md ko/claude/CLAUDE.md ko/codex/AGENTS.md gates/emit-mirrors.py \
         gates/test-install-guides.sh; do
  [ -f "$p" ] || { echo "FAIL: required file missing: $p"; exit 1; }
done
guide_count=$(ls claude/guides/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "$guide_count" -ge 1 ] || { echo "FAIL: no guides found in claude/guides"; exit 1; }

# Every leg below is written `if [ -f subject ]`, so deleting the subject deletes the leg while
# this umbrella still reports OK — a staged deletion is exactly the state the pre-commit hook
# judges. (Reproduction and history: design/surface-placement/, the verifier-coverage-map record.)
#
# Subjects are read out of THIS FILE rather than listed here, so a leg added later is required
# without anyone remembering to add it; a hand-kept list is the same rot one level up. Two guards
# on the scan itself: it must find something, and it must account for every conditional leg, so a
# guard written in a form this cannot parse fails loudly instead of going uncounted.
legs=$(grep -oE '^if \[ -[fxd] [A-Za-z0-9_./-]+ \]' "$SELF" | awk '{print $3 ":" $4}')
# The COUNT below accepts every conditional-leg spelling this file could plausibly
# grow — either bracket form, `test`, any predicate letter, quoted or variable
# subjects, and negation — while the PARSE above stays deliberately strict. A form
# the parse cannot read therefore DIVERGES the two counts and fails loudly instead
# of dropping out of both (PR #44 review: `[ -f "$REPO/x" ]` and `[ ! -f x ]` were
# invisible to both greps at once, which is the silent skip this guard exists for).
leg_n=$(printf '%s\n' "$legs" | grep -c . || true)
guard_n=$(grep -cE '^if (\[\[?|test) (! )?-[A-Za-z] ' "$SELF" || true)
[ "$leg_n" -gt 0 ] \
  || { echo "FAIL: no leg subjects parsed from $SELF — the scan is broken, not the tree"; exit 1; }
[ "$leg_n" -eq "$guard_n" ] \
  || { echo "FAIL: $guard_n conditional legs but $leg_n subjects parsed — a guard form this scan cannot read"; exit 1; }
leg_missing=""
for pair in $legs; do
  pred=${pair%%:*}; p=${pair#*:}
  # The leg's OWN predicate, not -e: a directory squatting on a -f subject
  # satisfies -e while the leg silently skips (endpoint round 1, #0).
  [ $pred "$p" ] || leg_missing="$leg_missing $p"
done
[ -z "$leg_missing" ] \
  || { echo "FAIL: leg subject(s) missing or of the wrong kind, so their checks would silently not run:$leg_missing"; exit 1; }

# Residual, disclosed rather than gated: both scans are anchored at column 0
# because a leg IS top-level here — an indented `if [ ... ]` in this file is body
# logic inside a loop, not a leg. An indented LEG would therefore leave both
# scans at once. Catching that needs block-structure analysis (a leg's guard
# subject is often a data file, not the script it runs — `domains.json` guards
# check-domains.py), which is not decidable by grep, and a gate on an
# undecidable rule is one people route around.

# Mirror gate: codex/ and ko/codex/ are PROJECTIONS of the claude-side canonical,
# emitted by gates/emit-mirrors.py, which owns the projection rule (config-home
# variable, title, and the one declared Codex-only standing-authorization bullet the
# host trigger contract requires). Checking the generator's own output subsumes the
# per-file mirror diffs it replaces and additionally pins the declared bullet's
# position, which a presence grep could not. --self-test proves each drift kind fails.
python3 gates/emit-mirrors.py --check >/dev/null \
  || { echo "FAIL: codex mirrors diverge from their projection (run gates/emit-mirrors.py)"; fail=1; }
python3 gates/emit-mirrors.py --self-test >/dev/null \
  || { echo "FAIL: mirror gate self-test missed a negative control"; fail=1; }

# EN/KO guide-bundle parity: primary names and every exact member path agree.  A directory
# name alone is not enough — it can hide a missing Korean RUNBOOK or an immutable asset the
# generator was meant to project.  The member resolver also rejects orphan trees/symlinks, so
# this is a subject check rather than an `ls` comparison that silently flattens the structure.
if ! python3 - <<'PY'
import pathlib
import sys
sys.path.insert(0, "compose")
from assemble import GuideMemberError, guide_member_map

try:
    en = guide_member_map(pathlib.Path("claude/guides"))
    ko = guide_member_map(pathlib.Path("ko/claude/guides"))
except GuideMemberError as exc:
    raise SystemExit(f"invalid guide bundle source: {exc}")
if not en or not ko:
    raise SystemExit("guide member subject is empty")
if set(en) != set(ko):
    raise SystemExit(f"primary guide sets differ: EN={sorted(en)} KO={sorted(ko)}")
for name in sorted(en):
    if en[name] != ko[name]:
        raise SystemExit(f"member sets differ for {name}: EN={en[name]} KO={ko[name]}")
PY
then
  echo "FAIL: EN and KO guide bundle sets differ"; fail=1
fi

# Every guide referenced from the global file must exist in both EN guide dirs.
refs=$(grep -o 'guides/[a-z0-9-]*\.md' claude/CLAUDE.md | sort -u)
[ -n "$refs" ] || { echo "FAIL: global file references no guides (extraction empty)"; fail=1; }
for ref in $refs; do
  name=$(basename "$ref")
  for dir in claude/guides codex/guides; do
    [ -f "$dir/$name" ] || { echo "FAIL: $dir/$name referenced from a global file but missing"; fail=1; }
  done
done

# Frontmatter gate: every guide declares guide_id/language; guide_id matches the
# filename, language matches the tree (files under ko/ are ko, else en), and any
# declared parent resolves to a sibling guide in the same dir.
for f in claude/guides/*.md codex/guides/*.md ko/claude/guides/*.md ko/codex/guides/*.md; do
  name=$(basename "$f")
  case "$f" in ko/*) want_lang=ko ;; *) want_lang=en ;; esac
  if [ "$(head -1 "$f")" != "---" ]; then
    echo "FAIL: missing YAML frontmatter: $f"; fail=1; continue
  fi
  fm=$(awk '/^---$/{n++; next} n==1{print} n>=2{exit}' "$f")
  gid=$(printf '%s\n' "$fm" | awk -F': ' '$1=="guide_id"{print $2; exit}')
  lang=$(printf '%s\n' "$fm" | awk -F': ' '$1=="language"{print $2; exit}')
  parent=$(printf '%s\n' "$fm" | awk -F': ' '$1=="parent"{print $2; exit}')
  [ "$name" = "$gid.md" ] || { echo "FAIL: guide_id does not match filename: $f (guide_id=$gid)"; fail=1; }
  [ "$lang" = "$want_lang" ] || { echo "FAIL: language does not match tree: $f (language=$lang, want=$want_lang)"; fail=1; }
  if [ -n "$parent" ] && [ ! -f "$(dirname "$f")/$parent.md" ]; then
    echo "FAIL: parent guide missing: $f (parent=$parent)"; fail=1
  fi
done

# Anchor-phrase gate: the global↔guide restatement pairs kept on purpose share a
# fixed anchor phrase; a one-sided edit that drops or rewords the anchor fails here.
# Format: anchor|fileA|fileB (EN canonical only; ko is a translation, not checked).
while IFS='|' read -r anchor fa fb; do
  [ -n "$anchor" ] || continue
  for f in "$fa" "$fb"; do
    grep -qF "$anchor" "$f" || { echo "FAIL: anchor phrase '$anchor' missing from $f (restatement pair drifted)"; fail=1; }
  done
done <<'ANCHORS'
difficulty × blast radius|claude/CLAUDE.md|claude/guides/cli-multi-model-workflow.md
convergence heuristic by reviewer kind|claude/guides/verification-discipline.md|claude/guides/cli-multi-model-workflow.md
code-level circuit breaker|claude/CLAUDE.md|claude/guides/cli-multi-model-workflow.md
current-state dashboard|claude/CLAUDE.md|claude/guides/implementation-map.md
Verification Menus|claude/CLAUDE.md|claude/guides/verification-discipline.md
real Microsoft Excel engine|claude/CLAUDE.md|claude/guides/verification-discipline.md
severity contract|docs/corpus.md|claude/guides/coding-staged-workflow.md
Ambient state|claude/CLAUDE.md|claude/guides/tooling-gotchas.md
the full lifecycle of what you create|claude/CLAUDE.md|claude/guides/tooling-gotchas.md
dual-provider frontier design drafts|claude/CLAUDE.md|claude/guides/cli-multi-model-workflow.md
ANCHORS

# Domain-manifest gate: bullet<->anchor bijection, file coverage, router
# co-packaging (compose/domains.json vs the monolith); its --self-test proves
# every negative control still fails, so a green gate is falsifiable.
if [ -f gates/fixture_support.py ]; then
  python3 gates/fixture_support.py --self-test >/dev/null \
    || { echo "FAIL: author fixture isolation (gates/fixture_support.py --self-test)"; fail=1; }
fi

if [ -f compose/domains.json ]; then
  python3 compose/check-domains.py >/dev/null \
    || { echo "FAIL: domains manifest gate (run compose/check-domains.py)"; fail=1; }
  python3 compose/check-domains.py --self-test >/dev/null \
    || { echo "FAIL: domains gate self-test missed a negative control"; fail=1; }
  bash gates/test-assemble.sh >/dev/null \
    || { echo "FAIL: assembler scenario suite (run gates/test-assemble.sh)"; fail=1; }
fi

# Full-mode install scenarios. The assembler suite above only exercises the
# domain-selected path; `packaged_mode()` keys on that selection, not on npm
# versus clone, so the command package.json advertises takes the OTHER branch.
#
# The sentinel breaks a real cycle rather than guarding a hypothetical one: the
# test runs `install.sh verify`, and verify runs THIS umbrella (install.sh:707),
# which would run the test again. The skip announces itself — a leg that goes
# quiet is how a suite reports clean over something it never ran.
# Not conditional on the file existing — it is asserted above with the other
# required subjects, because an `if [ -f ]` around the ONLY suite covering a
# branch means deleting the file deletes the leg and the umbrella still says OK.
if [ "${AGENT_BIOS_IN_INSTALL_TEST:-0}" = 1 ]; then
  echo "SKIP: full-mode install scenarios — already inside them (install.sh verify)"
else
  # Output kept, not discarded. This leg is the slowest and the only one that runs real
  # installs, and it failed three times inside this umbrella while passing standalone —
  # each time `>/dev/null` had thrown away the one thing that would have said why, so
  # the only way to ask was to re-run it for another eleven minutes and watch it pass.
  # A failure nobody can diagnose is how a gate earns a reputation for flaking, which is
  # how it stops being read at all.
  install_log="$(mktemp -t install-scenarios)"
  if AGENT_BIOS_LEGACY_INSTALL=1 bash gates/test-install-guides.sh >"$install_log" 2>&1; then
    rm -f "$install_log"
  else
    echo "FAIL: full-mode install scenarios (run gates/test-install-guides.sh)"
    echo "--- its own failing output ---"
    grep -a 'FAIL' "$install_log" | head -20
    echo "--- last 15 lines ---"
    tail -15 "$install_log"
    echo "--- full log kept at $install_log ---"
    fail=1
  fi
fi

# Payload boundary (gates/check-package.sh). The gate itself runs from the
# pre-commit hook and install.sh verify; what runs HERE is its negative control,
# which until now did not exist — the flag was rejected rather than implemented,
# so no leg had ever been shown to fail. It plants each violation into a
# throwaway copy of the tree, so it costs a few seconds rather than milliseconds.
if [ -x gates/check-package.sh ]; then
  ./gates/check-package.sh --self-test >/dev/null \
    || { echo "FAIL: package gate self-test missed a planted violation"; fail=1; }
fi

# Learning record gate: learn/learning.schema.json (collection-loop
# SSOT) vs its fixtures; --self-test proves every mutation is still caught.
if [ -f learn/learning.schema.json ]; then
  python3 learn/check-learning.py >/dev/null \
    || { echo "FAIL: learning record gate (run learn/check-learning.py)"; fail=1; }
  python3 learn/check-learning.py --self-test >/dev/null \
    || { echo "FAIL: learning gate self-test missed a negative control"; fail=1; }
  # collect-learning Phase 2 transport: the watermark upload-drain logic
  # (status classification, watermark advance, transient-stop, poison-skip)
  # plus the capture-time secret-redaction wiring.
  python3 learn/collect-learning.py --self-test >/dev/null \
    || { echo "FAIL: collect-learning upload-drain self-test"; fail=1; }
fi

# Corpus rollback (compose/corpus-state.py) — a destructive path with no other
# coverage: every version registered today is UNAVAILABLE (it predates the assembled
# layout), so the write loop is unreachable from `list` and nothing else exercises it.
# --self-test drives it against a throwaway git repo and proves a run that fails
# partway restores rather than leaving the corpus split across two versions.
if [ -f compose/corpus-state.py ]; then
  python3 compose/corpus-state.py --self-test >/dev/null \
    || { echo "FAIL: corpus rollback self-test (compose/corpus-state.py)"; fail=1; }
fi

# Secret-redaction floor (learn/redact.py) — single-sourced by the heavy
# (digest.py) and light (collect-learning.py) flows; --self-test proves each
# pattern fires and that lessons ABOUT secrets are not over-redacted.
if [ -f learn/redact.py ]; then
  python3 learn/redact.py --self-test >/dev/null \
    || { echo "FAIL: secret-redaction floor self-test (learn/redact.py)"; fail=1; }
fi

# Phase 3 curation intake (learn/ingest-learnings-export.py) — validates a
# dashboard learnings export and maps it to ledger candidates; --self-test
# proves valid rows map (cardinality > 0) and broken/non-v1 rows are diverted.
if [ -f learn/ingest-learnings-export.py ]; then
  python3 learn/ingest-learnings-export.py --self-test >/dev/null \
    || { echo "FAIL: curation-intake self-test (learn/ingest-learnings-export.py)"; fail=1; }
fi

# Phase 4 promote->migrate: the promotion manifest (learn/promotions.json) is
# DERIVED from the ledger — --check fails if it is stale, so a promotion can't
# ship without its manifest entry; migrate-learnings clears personal copies only
# for in-bundle promotions (--self-test proves the not-in-bundle keep guard).
if [ -f learn/build-promotions.py ]; then
  python3 learn/build-promotions.py --self-test >/dev/null \
    || { echo "FAIL: build-promotions self-test"; fail=1; }
  python3 learn/build-promotions.py --check >/dev/null \
    || { echo "FAIL: learn/promotions.json is stale vs the ledger (run learn/build-promotions.py)"; fail=1; }
fi
if [ -f compose/prune-backups.py ]; then
  python3 compose/prune-backups.py --self-test >/dev/null \
    || { echo "FAIL: backup retention self-test"; fail=1; }
fi
if [ -f learn/migrate-learnings.py ]; then
  python3 learn/migrate-learnings.py --self-test >/dev/null \
    || { echo "FAIL: migrate-learnings self-test (personal-copy prune + in-bundle guard)"; fail=1; }
fi

# Decision record (decisions/record-decision.py) — the submit tool that owns id,
# timestamp, provenance, and interval so a caller cannot author its own. Its
# --self-test proves the recording bar refuses, no stamped field is settable from
# the payload, and a backfilled record claims no interval it cannot derive.
if [ -f decisions/record-decision.py ]; then
  python3 decisions/record-decision.py --self-test >/dev/null \
    || { echo "FAIL: decision-record self-test (decisions/record-decision.py)"; fail=1; }
  # The self-test proves the code; --check proves the ARTIFACT. Without it a
  # hand-edited or forged row renders as fact and no gate ever looks at it.
  python3 decisions/record-decision.py --check >/dev/null \
    || { echo "FAIL: decision ledger (run decisions/record-decision.py --check)"; fail=1; }
fi

# Lexicon gate: forbid deprecated terminology tokens in live files
# (LEXICON.md is the SSOT); --self-test proves the detector can fire.
if [ -f LEXICON.md ]; then
  python3 gates/check-lexicon.py >/dev/null \
    || { echo "FAIL: lexicon gate (run gates/check-lexicon.py)"; fail=1; }
  python3 gates/check-lexicon.py --self-test >/dev/null \
    || { echo "FAIL: lexicon gate self-test failed"; fail=1; }
fi

# Content-hygiene gate: the shipped distribution (npm payload + ko corpus trees) stays
# free of org identifiers everywhere and author identifiers outside `(private)`-marked
# lines or per-reason exemptions. The subject set is derived from package.json files[]
# and asserted non-empty; --self-test plants each violation class and requires a named
# failure, positive control first.
if [ -f gates/check-hygiene.py ]; then
  python3 gates/check-hygiene.py >/dev/null \
    || { echo "FAIL: content-hygiene gate (run gates/check-hygiene.py)"; fail=1; }
  python3 gates/check-hygiene.py --self-test >/dev/null \
    || { echo "FAIL: content-hygiene self-test failed"; fail=1; }
fi

# Endpoint contract gate: ENDPOINTS.md's wire literals are held against the code,
# a default install resolves no transport (probed through the real transport_config
# with the instrument proven against a planted slot first), registered hooks carry
# no network primitive, and no shipped code file hardcodes an endpoint URL outside
# anchored, exercised exemptions. --self-test plants each violation and requires a
# named failure, positive control first.
# Offline only. --online reaches the vendor docs and must never run here: a gate that
# reaches the network fails in a tunnel. What runs is the structural half — that every pin
# names a mapped document and every mapped document is pinned — which is what makes the
# online comparison able to run at all.
if [ -f gates/check-prompting-sources.py ]; then
  python3 gates/check-prompting-sources.py >/dev/null \
    || { echo "FAIL: prompting source pins (run gates/check-prompting-sources.py)"; fail=1; }
  python3 gates/check-prompting-sources.py --self-test >/dev/null \
    || { echo "FAIL: prompting-source self-test (gates/check-prompting-sources.py --self-test)"; fail=1; }
fi

if [ -f gates/check-endpoints.py ]; then
  python3 gates/check-endpoints.py >/dev/null \
    || { echo "FAIL: endpoint contract gate (run gates/check-endpoints.py)"; fail=1; }
  python3 gates/check-endpoints.py --self-test >/dev/null \
    || { echo "FAIL: endpoint-contract self-test failed"; fail=1; }
fi

# Coverage, which is a different question from every check above: those ask whether
# a claim holds, this asks whether any harness EXECUTES the branch that would break
# the claim. It is here rather than in a report because the lesson that produced it
# was a 105-minute audit nobody ran — a check that is not run is not a check. Seconds,
# not minutes: it traces two in-process harnesses.
if [ -f gates/check-seam-coverage.py ]; then
  python3 gates/check-seam-coverage.py >/dev/null \
    || { echo "FAIL: transport seam has statements no harness executes (run gates/check-seam-coverage.py)"; fail=1; }
  python3 gates/check-seam-coverage.py --self-test >/dev/null \
    || { echo "FAIL: seam-coverage self-test failed"; fail=1; }
fi

# Receipt chain, over a space derived from the config rather than listed: every preset
# and host the config declares, the plan the real launcher renders for it, and the seat
# that plan projects. A stub adapter keeps it free of spend; --real dispatches for
# real and is deliberately never run here. --self-test proves a cell can fail.
if [ -f gates/check-receipt-chain.py ]; then
  python3 gates/check-receipt-chain.py >/dev/null \
    || { echo "FAIL: receipt chain (run gates/check-receipt-chain.py)"; fail=1; }
  python3 gates/check-receipt-chain.py --self-test >/dev/null \
    || { echo "FAIL: receipt chain self-test missed a negative control"; fail=1; }
fi

# Publication provenance gate: npm lifecycle runs it for real (prepack stamps,
# prepublishOnly guards); here only its self-test runs, because the guard's
# verdict on THIS tree at commit time is meaningless — trees are legitimately
# dirty mid-work — while a broken stamp or guard would let the next publish
# repeat the v0.9.9 unbound-tarball shape silently.
if [ -f gates/check-publish.sh ]; then
  bash gates/check-publish.sh --self-test >/dev/null \
    || { echo "FAIL: publish-provenance self-test (run gates/check-publish.sh --self-test)"; fail=1; }
fi

# Surface catalog gate: SURFACES.md routes every promoted learning and every new tool,
# so a catalog that has drifted routes them wrongly while reading as current. Two
# decidable directions — an authority path matching no file, and a deploy target no
# surface claims. --self-test proves each fires.
if [ -f SURFACES.md ]; then
  python3 gates/check-surfaces.py >/dev/null \
    || { echo "FAIL: surface catalog gate (run gates/check-surfaces.py)"; fail=1; }
  python3 gates/check-surfaces.py --self-test >/dev/null \
    || { echo "FAIL: surface catalog gate self-test failed"; fail=1; }
fi

# Review-routing golden: normalised dry-run projections + resolver decisions
# (gates/goldens/ — count the entries there; a number written here went stale once).
# It pins the ENTIRE rendered contract byte-for-byte across every
# setup/host/family/capability/delegation combination, which subsumes the per-reviewer
# prose substrings the runtime checks used to assert — and unlike them it also covers
# reviewers this repo has never seen. --self-test proves each of its four controls
# still fires, so a green golden is falsifiable rather than merely large.
if [ -f gates/goldens/review-matrix.json ]; then
  python3 gates/capture-review-goldens.py --check >/dev/null \
    || { echo "FAIL: review routing diverges from gates/goldens/review-matrix.json"; fail=1; }
  python3 gates/capture-review-goldens.py --self-test >/dev/null \
    || { echo "FAIL: review golden self-test missed a negative control"; fail=1; }
fi

# The ontology (ontology/) claims dependency facts about this repo. A claim nobody
# checks decays into a confidently wrong dependency map, which is worse than none — so
# the gate re-derives the facts from source and fails on disagreement, and --self-test
# proves each of its negative controls still fires.
if [ -f ontology/check-ontology.py ]; then
  python3 ontology/check-ontology.py >/dev/null \
    || { echo "FAIL: ontology disagrees with the code (run ontology/check-ontology.py)"; fail=1; }
  python3 ontology/check-ontology.py --self-test >/dev/null \
    || { echo "FAIL: ontology gate self-test missed a negative control"; fail=1; }
fi

# The hook is the one mechanism here that provably fires on every session, and until now it was
# asserted only by "the file was copied" and "the registration string is present" — a hook that
# crashed on every invocation passed every gate in this repo, and its own docstring claimed a
# verification that did not exist. Its self-test runs the real entry point over real stdin, and
# checks each rule's declared anchor against the guide AND the codex mirror, which is the only
# thing keeping shared hook reminders aligned with both guide fallbacks.
# Every shipped hook, not a named one: the list is the directory, so a hook added later is
# covered by existing, and a hook that ships without a --self-test fails here rather than
# riding along untested. The count is asserted because an empty glob satisfies a loop.
hook_count=0
for hook in claude/hooks/*.py; do
  [ -f "$hook" ] || continue
  hook_count=$((hook_count + 1))
  python3 "$hook" --self-test >/dev/null \
    || { echo "FAIL: $(basename "$hook") self-test (run python3 $hook --self-test)"; fail=1; }
done
if [ "$hook_count" -eq 0 ]; then
  echo "FAIL: no hook self-tests ran — claude/hooks/ holds no .py, so this leg judged nothing"
  fail=1
fi

# Prompting guides name concrete models, so they go stale on a rebinding rather than degrading
# quietly. This ran only from `install.sh verify`, which means a commit that bound a tier to a
# model no guide covered landed clean and surfaced at the next install. 26ms, no network, no
# install state — it was unwired rather than deliberately deferred.
if [ -x launch/check-prompting-targets.sh ]; then
  ./launch/check-prompting-targets.sh >/dev/null \
    || { echo "FAIL: prompting guides do not cover a configured model (run launch/check-prompting-targets.sh)"; fail=1; }
fi

# Reach: a check that exists, has a subject, and never runs before a commit is indistinguishable
# from no check. The subject set is every check-shaped file in the repo; reachability is the
# transitive closure of script references from the pre-commit hook through the two umbrellas it
# runs. Derived both ways rather than listed, so adding a gate without wiring it fails here
# instead of being discovered the next time something it guards breaks.
# Not inside $( ... ): the shell matches parens through a heredoc body, so a python
# program this size eventually trips its quote scanner. The scan prints its own
# failure, so there is nothing to capture.
python3 - <<'REACH' || fail=1
import pathlib, re, subprocess, sys

HOOK = '.githooks/pre-commit'
# \Z rather than $: inside $( ... ) the shell reads `$"` and `$'` as its own quoting forms,
# and a regex ending in one breaks the command substitution that carries this script.
FILE_TEST = re.compile(r"-[xferd]\s*\"?\Z")
# A path is an invocation only in execution position: run directly, or handed to an
# interpreter — including one held in a variable, as `"$VENV/bin/python" gates/check_parity.py`.
EXEC_PREFIX = re.compile(r'(?:\./|(?:python3?|bash|sh|zsh|exec)["\']?\s+)\Z')
FOR_LINE = re.compile(r'\bfor\s+(\w+)\s+in\b')


def live_lines(text):
    """The file's lines minus the statically dead ones — both directions. `false && cmd`,
    `true || cmd`, and the dead side of a literal-condition if: `if false` kills the then
    branch and its else branch is LIVE (the first version dropped the whole block, hiding
    real code), `if true` keeps the then branch and kills the else (review planted a
    checker there and the scan credited it). One filter, every consumer.

    Only literal constants are decidable. A non-literal `if` keeps both branches and its
    own line — the hook's real invocation rides on `if ! ( ... "./$gate" ); then`. An
    `elif` after a literal condition makes the frame opaque (kept from there on): keeping
    possibly-dead code is the lenient error, and stated. One-line `if false; ...; fi`
    with an else clause keeps the limitation too — the whole line is consumed.
    """
    kept, stack = [], []      # stack frames: [literal?, current-branch-live?]
    heredoc_end = None
    dead_loop_depth = 0       # inside `while false` / `until true` — the body never runs
    for raw in text.splitlines():
        s = raw.strip()
        if dead_loop_depth > 0:
            sc = code_only(s)
            dead_loop_depth += len(re.findall(r'\bdo\b', sc)) \
                - len(re.findall(r'\bdone\b', sc))
            continue
        if dead_loop_depth == -1:
            # a dead loop declared without `do` on its own line: structural lines up to
            # and including the do are consumed, then the body skip begins.
            sc = code_only(s)
            d = len(re.findall(r'\bdo\b', sc)) - len(re.findall(r'\bdone\b', sc))
            if re.search(r'\bdo\b', sc):
                dead_loop_depth = d if d > 0 else 0
            continue
        lm = re.match(r'(while|until)\s+(!\s*)?(true|false)\b', s)
        if lm:
            val = (lm.group(3) == "true") != bool(lm.group(2))
            if (lm.group(1) == "while") != val:
                # while-false / until-true: the guard is a constant the wrong way, so the
                # body is as dead as an `if false` branch — same literal family. Valid
                # Bash may put `do` on the NEXT line; -1 marks the loop as pending its do.
                sc = code_only(s)
                d = len(re.findall(r'\bdo\b', sc)) - len(re.findall(r'\bdone\b', sc))
                if re.search(r'\bdo\b', sc):
                    if d > 0:
                        dead_loop_depth = d
                else:
                    dead_loop_depth = -1
                continue
            # live loop (while-true / until-false): the line may carry commands after `do`;
            # fall through and keep it.
        # A heredoc body is data fed to a command, not shell: `python3 - <<'REACH'` feeds
        # this very scan its own source, and a checker path at command position inside
        # such a payload read as an invocation. The opening line stays (it IS a command);
        # the body is skipped to the terminator. First heredoc per line only, stated.
        if heredoc_end is not None:
            if s == heredoc_end:
                heredoc_end = None
            continue
        # All three shell quoting forms for the delimiter — <<'EOF', <<"EOF", <<\EOF —
        # plus bare. Only single quotes were handled first, and a payload behind a
        # double-quoted delimiter read as live shell again.
        hd = re.search(r"<<-?\s*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][A-Za-z_0-9]*))", s)
        if hd:
            heredoc_end = next(g for g in hd.groups() if g)
        m = re.match(r'if\s+(!\s*)?(true|false)\b', s)
        if m:
            # `if ! true` is as dead as `if false` — negation of a literal is a literal.
            stack.append([True, (m.group(2) == "true") != bool(m.group(1))])
            continue
        if re.match(r'if\b', s):
            stack.append([False, True])
            if all(f[1] for f in stack):
                kept.append(raw)
            continue
        if re.match(r'elif\b', s) and stack:
            if stack[-1][0]:
                stack[-1][:] = [False, True]
            if all(f[1] for f in stack):
                kept.append(raw)
            continue
        if re.match(r'else\b', s) and stack:
            if stack[-1][0]:
                stack[-1][1] = not stack[-1][1]
            continue
        if re.match(r'fi\b', s) and stack:
            stack.pop()
            continue
        # `! true && cmd` is `false && cmd`; negation of a literal is a literal here too.
        # The lookbehinds keep `! false && cmd` — which is LIVE — from matching the bare
        # `false &&` branch: the fix for the negated form almost dropped its dual.
        if re.search(r'(?:(?<!!)(?<!!\s)\bfalse\b|!\s*true\b)\s*&&'
                     r'|(?:(?<!!)(?<!!\s)\btrue\b|!\s*false\b)\s*\|\|', s):
            continue
        if all(f[1] for f in stack):
            kept.append(raw)
    return kept


def quote_mask(line):
    """True at positions inside a quoted region (openers/closers included), escape-aware.
    Shell separators and keywords lose their meaning inside quotes: `echo "; ./$gate"`
    carries an anchor-shaped `;` that anchors nothing, and review reproduced both the
    loop-variable and helper-call scans crediting such diagnostics as execution."""
    mask, quote, esc = [], None, False
    for ch in line:
        if esc:
            mask.append(quote is not None)
            esc = False
            continue
        if ch == "\\" and quote != "'":
            mask.append(quote is not None)
            esc = True
            continue
        if quote:
            mask.append(True)
            quote = None if ch == quote else quote
            continue
        if ch in "'\"":
            quote = ch
            mask.append(True)
            continue
        mask.append(False)
    return mask


def unquoted_anchors(line):
    """Command-start positions whose anchor is REAL shell syntax: line start, an unquoted
    separator, or an unquoted do/then/else keyword."""
    mask = quote_mask(line)
    anchors = [0]
    for m in re.finditer(r'[;&|(]', line):
        if not mask[m.start()]:
            anchors.append(m.end())
    for m in re.finditer(r'\b(?:do|then|else)\b', line):
        if not mask[m.start()]:
            anchors.append(m.end())
    return anchors, mask


def invokes_var(text, var):
    """Does this file actually RUN the loop variable it just bound?

    `for gate in A B` names two paths, and crediting the list alone was a hole: replace the
    loop body with `:` and both umbrellas still read as wired while pre-commit ran neither.
    The list is a binding; the body is the invocation."""
    # COMMAND position, the same discipline EXEC_PREFIX applies to literal paths:
    # `echo "./$gate"` carries the exec shape inside a diagnostic string, and without the
    # anchor a loop that only prints its variable counted as running it. A command starts
    # at line start (continuation lines land there), after ; & | (, or after do/then/else,
    # with env-var assignments allowed in front — the hook's real call is
    # `GIT_INDEX_FILE="..." "./$gate"`.
    tail = re.compile(r'\s*(?:\w+=[^\s;&|()]*\s+)*'
                      r'["\']?(?:\./|(?:python3?|bash|sh|zsh|exec)["\']?\s+)["\']?\$\{?'
                      + re.escape(var) + r'\}?')
    for l in live_lines(text):
        s = sans_comment(l.strip())
        if not s or l.strip().startswith('#') or FOR_LINE.search(l):
            continue
        anchors, _mask = unquoted_anchors(s)
        if any(tail.match(s, a) for a in anchors):
            return True
    return False


def read_real(rel):
    p = pathlib.Path(rel)
    return p.read_text() if p.is_file() else None


def sans_comment(line):
    """The line with its trailing unquoted comment removed, quoted text KEPT. For edge
    and invocation matching: `echo ok # python3 gates/dead.py` credited the commented
    path, but stripping quotes too would blind the matcher to "./$gate", which lives in
    quotes on purpose. code_only() below strips both and serves structure only.

    Backslash escapes a character rather than opening anything: `echo \" # ...` puts a
    literal quote and then a real comment, and the unescaped scanner opened a quote
    there and kept the commented path alive."""
    out, quote, esc = [], None, False
    for ch in line:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\" and quote != "'":
            out.append(ch)
            esc = True
            continue
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            continue
        if ch == '#':
            break
        out.append(ch)
    return "".join(out)


def code_only(line):
    """The line minus quoted text and the trailing comment, for STRUCTURAL counting only
    (braces, do/done, function defs). A `# }` inside an uncalled helper closed the parsed
    function early and promoted its dead command to top level; `echo "}"` would do the
    same from a string. Invocation/edge matching keeps the full line — `"./$gate"` lives
    inside quotes on purpose."""
    out, quote, esc, i = [], None, False, 0
    while i < len(line):
        ch = line[i]
        if esc:
            esc = False
            i += 1
            continue
        if ch == "\\" and quote != "'":
            esc = True
            i += 1
            continue
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if ch == '#':
            break
        out.append(ch)
        i += 1
    return "".join(out)


def called_bodies(text):
    """Lines of the file that can actually run: top level, plus bodies of functions the
    top level (transitively) calls. `unused() { python3 gates/dead.py; }` credited an
    edge for a command nothing invokes — moving an invocation into a helper and dropping
    the helper's call kept the scan green.

    THE CONTRACT BOUNDARY, stated once: this scan is syntactic. It understands literal
    constant-false guards, function-call reachability, comments, self-test flags, and
    file tests. It is not a shell interpreter: eval, aliases, `sh -c` strings, sourced
    files, and paths held in variables are OUT of its reach, permanently — each would be
    another rung on a ladder with no top. A disabling trick from that list is not a
    scan defect; it is outside the declared contract, and belongs to review."""
    defs, order, def_pos = {}, [], {}
    top, cur, depth, closer, pending = [], None, 0, None, None
    for raw in text.splitlines():
        s = raw.strip()
        sc = code_only(s)
        # Bash also accepts the opener on the NEXT line: `unused ()` newline `{`. A
        # declaration line with no opener holds as pending; the following line either
        # opens the body or the pending name is discarded.
        if pending is not None and cur is None:
            name, pending = pending, None
            if sc[:1] in ("{", "("):
                opener = sc[0]
                closer = '}' if opener == '{' else ')'
                cur, depth = name, sc.count(opener) - sc.count('}' if opener == '{' else ')')
                defs[cur] = []
                order.append(cur)
                def_pos[cur] = len(top)
                # Same as the same-line form: the opener line may CARRY the body
                # (`{ python3 gates/foo.py; }`), and counting delimiters without storing
                # the text between them rejected called wiring as orphaned.
                tail_raw = s[1:]
                if depth <= 0 and closer in tail_raw:
                    tail_raw = tail_raw.rsplit(closer, 1)[0]
                if tail_raw.strip():
                    defs[cur if depth > 0 else name].append(tail_raw)
                if depth <= 0:
                    cur = None
                continue
        pm = re.match(r'(?:function\s+)?(\w+)\s*\(\)\s*$', sc) \
            or re.match(r'function\s+(\w+)\s*$', sc)
        if cur is None and pm:
            # `function name` with no parens also takes its opener on the next line —
            # the composition of the two forms each already handled alone.
            pending = pm.group(1)
            continue
        # Every declaration style: `name() {`, bash's `function name {` (parens optional
        # with the keyword), and the SUBSHELL body `name() ( ... )` — each earlier form
        # was unrecognized in its turn, leaking an uncalled helper's body to top level.
        # The body's delimiter pair is whichever opener follows the name.
        m = re.match(r'(?:function\s+)?(\w+)\s*\(\)\s*([({])', sc) \
            or re.match(r'function\s+(\w+)\s*([({])', sc)
        if cur is None and m:
            opener = m.group(2)
            closer = '}' if opener == '{' else ')'
            body_sc = sc[m.end() - 1:]
            cur, depth = m.group(1), body_sc.count(opener) - body_sc.count(closer)
            defs[cur] = []
            order.append(cur)
            def_pos[cur] = len(top)
            # Executable text on the DECLARATION line is body too: `f() { cmd; }` closed
            # at depth zero with cmd never stored, so a legitimately wired one-line
            # helper read as an orphan — the false-positive direction.
            mr = re.match(r'(?:function\s+)?\w+\s*(?:\(\))?\s*' + re.escape(opener), s)
            if mr:
                tail_raw = s[mr.end():]
                if depth <= 0 and closer in tail_raw:
                    tail_raw = tail_raw.rsplit(closer, 1)[0]
                if tail_raw.strip():
                    defs[cur].append(tail_raw)
            if depth <= 0:
                cur = None
            continue
        if cur is not None:
            opener = '{' if closer == '}' else '('
            depth += sc.count(opener) - sc.count(closer)
            if depth <= 0:
                cur = None
            else:
                defs[cur].append(raw)
            continue
        top.append(raw)

    def invoked(name, lines):
        # code_only strips quoted text and comments: a function CALL is bare shell, so
        # `echo "; unused"` and `echo ok # ; unused` stop reading as calls.
        # `unused=1` shares the name and calls nothing: \b matches before `=`, so an
        # ordinary variable assignment read as an invocation. A call ends the word at
        # whitespace, a separator, or EOL — never at an assignment operator.
        # `MODE=full run_checks` is a real call: per-command assignments precede the
        # name, exactly as the variable-invocation matcher already allows.
        pat = re.compile(rf'(?:^|[;&|(]\s*|&&\s*|\|\|\s*)(?:\w+=[^\s;&|()]*\s+)*'
                         rf'{re.escape(name)}\b(?!\+?=)')
        return any(pat.search(code_only(l.strip())) for l in lines
                   if not l.strip().startswith('#'))

    # Bash resolves a function at CALL time: a top-level call ABOVE its definition is
    # "command not found" — under this repo's `set -u` umbrellas that is one stderr
    # line and a green exit, so an early call roots nothing. Only top-level lines
    # after the definition completes count as roots (no top line can fall inside a
    # definition, so its start index is its end index). Calls from inside another
    # called body stay order-free: a body runs when its caller does, and deciding
    # that ordering statically is interpreter work the contract above excludes.
    called, frontier = set(), [n for n in order if invoked(n, top[def_pos[n]:])]
    while frontier:
        f = frontier.pop()
        if f in called:
            continue
        called.add(f)
        frontier.extend(n for n in order if n not in called and invoked(n, defs[f]))
    body = list(top)
    for n in order:
        if n in called:
            body.extend(defs[n])
    return body


def edges(text):
    """Script paths this file EXECUTES in default mode.

    Three exclusions, each a way a path appears without the current tree being judged. A
    comment naming a file runs nothing. `--self-test` proves the gate CAN fail without asking
    whether it does today — a leg reduced to its self-test leaves live drift unchecked while
    still looking wired. And a file test (`[ -x path ]`) is a predicate, not an invocation:
    the parity umbrella guards the package gate on one line and runs only its self-test on the
    next, so counting the guard silently re-admitted the edge the self-test rule had removed.

    Deliberately not requiring a run-shaped prefix: the hook invokes its gates from a
    `for gate in ...` list, a real execution edge with no prefix on the line. The residual is a
    path named in non-comment prose, e.g. inside an echo; narrower than the failure this exists
    to catch, and stated rather than hidden."""
    out = set()
    # live_lines FIRST, reachability second: seeding the call graph from unfiltered top
    # level marked a helper called from inside `if false` as live, and its body's edges
    # came back — a composition bug between two features each correct alone. Filtering
    # first also drops function definitions inside dead blocks, which in shell would
    # never be defined at all.
    lines = called_bodies("\n".join(live_lines(text)))
    for idx, line in enumerate(lines):
        s = sans_comment(line.strip())
        if not s or line.strip().startswith('#'):
            continue
        loop = FOR_LINE.search(s)
        body = None
        if loop:
            # THIS loop's body, not the whole file: two loops reusing one variable name
            # cross-credited — a dead `do :; done` list satisfied by a later loop that
            # happened to bind the same word. The body runs from the first `do` (same
            # line included, for one-liners) to the matching `done`.
            parts = re.split(r'\bdo\b', s, maxsplit=1)
            segs = [parts[1]] if len(parts) == 2 else []
            sco = code_only(s)
            depth, seen_do, j = (len(re.findall(r'\bdo\b', sco))
                                 - len(re.findall(r'\bdone\b', sco)),
                                 bool(len(parts) == 2), idx)
            while depth > 0 or not seen_do:
                j += 1
                if j >= len(lines):
                    break
                sj = lines[j]
                sjc = code_only(sj)
                depth += len(re.findall(r'\bdo\b', sjc)) - len(re.findall(r'\bdone\b', sjc))
                seen_do = seen_do or bool(re.search(r'\bdo\b', sjc))
                segs.append(sj)
            # Innermost binding wins: a nested `for` rebinding the SAME name shadows the
            # outer variable, so its region is masked from the outer loop's body before
            # the invocation test — `for gate in dead; do for gate in live; do "./$gate"`
            # runs only live, and crediting the outer list was review's reproduction.
            # The outer binding never comes back: after a same-name nested loop ends,
            # bash leaves the variable at the inner list's last value for the REST of
            # the iteration, so an invocation after that point runs the inner value,
            # not the outer list. The first masking pass resumed collecting there and
            # credited the outer list for it — review's reproduction. Collection stops
            # for good at the first same-name rebind; the nested loop's own line is
            # judged as its own loop when the scan reaches it.
            masked = []
            for seg in segs:
                fm = FOR_LINE.search(seg.strip())
                if fm and fm.group(1) == loop.group(1):
                    break
                masked.append(seg)
            body = "\n".join(masked)
        hits = list(re.finditer(r'([a-z]+/[a-z_.-]+\.(?:py|sh))\b', s))
        _, hmask = unquoted_anchors(s)
        # A path inside quotes is an argument or a diagnostic, not an invocation:
        # `echo "; ./gates/a.sh"` carried its own separator and exec shape, all quoted.
        hits = [h for h in hits if not hmask[h.start()]]
        for i, hit in enumerate(hits):
            # Argument span, not rest-of-line: the tail used to run to EOL, which made a line
            # naming two scripts register only the first. The hook invokes both umbrellas from
            # one `for gate in A B` list, so the second was invisible and the closure had to be
            # seeded with the umbrellas to reach anything — the very seeding that then hid
            # whether the hook still ran them.
            tail = s[hit.end():hits[i + 1].start()] if i + 1 < len(hits) else s[hit.end():]
            if '--self-test' in tail or FILE_TEST.search(s[:hit.start()]):
                continue
            if loop:
                if not invokes_var(body, loop.group(1)):
                    continue
            elif not EXEC_PREFIX.search(s[:hit.start()]):
                continue
            out.add(hit.group(1))
    return out


def reach_from(read):
    """Transitive closure from the hook ALONE.

    The umbrellas used to be seeded as roots beside it, which made the scan answer out of the
    gate files themselves: dropping an umbrella's invocation from the hook changed no finding,
    so the one thing this check exists to see — the wiring — was the one thing it could not."""
    seen, frontier = set(), [HOOK]
    while frontier:
        rel = frontier.pop()
        if rel in seen:
            continue
        seen.add(rel)
        text = read(rel)
        # Shell invokes; Python describes. check-receipt-chain.py's docstring names
        # check_parity.py, which forged an edge and made a module look wired by prose alone.
        if text is None or not (rel == HOOK or rel.endswith('.sh')):
            continue
        frontier.extend(n for n in edges(text) if n not in seen)
    return seen - {HOOK}


# The subject set is derived from the tracked files, not from a list of directory globs. The
# globs enumerated a separator as well as a directory: `gates/check-*.py` never matched
# `gates/check_parity.py`, so the one module with no self-test was also the one no orphan check
# could see. Tracked rather than walked, because the worktrees the agent harness leaves under
# .claude/ are full copies of this tree and would enter the subject set as permanent orphans.
D = 'gates/'
CHECK_NAME = re.compile(r'(?:^|/)(?:check[-_.]|test-)[^/]*\.(?:py|sh)$')
ls = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)
if ls.returncode != 0:
    print("FAIL: git ls-files failed, so the reach scan has no subject set: "
          + ls.stderr.strip()[:120]); sys.exit(1)
# Props, not gates. `benchmarks/fixtures/` holds miniature projects the battery runs a model
# against, and one of them IS a CI parity check that reports `ok` while its subject cannot be
# imported — that lie is the scenario's whole subject. Scanning it as a gate blocked a commit
# once and the fixture was renamed to get past the scan, which made the fixture less faithful
# to satisfy a check about something else. Named as one tree with its reason, not as a general
# licence: "fixtures may imitate anything" would excuse every tree that ever grows a fixtures
# directory, and an enumeration that happens to exclude something has not named it.
NOT_A_GATE = ('benchmarks/fixtures/',)
tracked = ls.stdout.splitlines()
for tree in NOT_A_GATE:
    if not any(f.startswith(tree) for f in tracked):
        print(f"FAIL: {tree} is declared not-a-gate but no tracked file lives there — a stale "
              f"exemption is one nobody will notice has stopped excluding anything"); sys.exit(1)
subjects = sorted(f for f in tracked
                  if CHECK_NAME.search(f) and not f.startswith(NOT_A_GATE))
if not subjects:
    print("FAIL: no check-shaped files found — the reach scan judged nothing"); sys.exit(1)
exempted = sorted(f for f in tracked if CHECK_NAME.search(f) and f.startswith(NOT_A_GATE))
if not exempted:
    print("FAIL: the fixtures exemption excluded nothing — an exemption with no subject is "
          "not an exemption, and the leg it was added for would fire again unnoticed")
    sys.exit(1)

# The naming rule has to admit both separators and refuse a word that merely starts with
# "check". Underscore is the case that was missing, so it is the case that is asserted.
# Split literals: a probe naming a real checker would be read as an execution edge by the
# very scan below, and the fixture would forge the wiring it is meant to test.
for name, want in ((D + 'check' + '_parity.py', True), (D + 'check' + '-lexicon.py', True),
                   (D + 'test' + '-assemble.sh', True), ('compose/check' + 'out.py', False),
                   ('claude/guides/check' + 'list.md', False)):
    if bool(CHECK_NAME.search(name)) is not want:
        print(f"FAIL: reach subject naming — {name} should{'' if want else ' not'} be a "
              f"subject"); sys.exit(1)
# The exemption has to exclude a prop and nothing else. Both directions, because a prefix test
# that excluded the wrong tree would hide a real unwired gate rather than a fixture.
for name, exempt in (('benchmarks/fixtures/parity-ci/scripts/check' + '-parity.py', True),
                     ('benchmarks/fixture' + '_state.py', False),
                     (D + 'check' + '-lexicon.py', False)):
    if name.startswith(NOT_A_GATE) is not exempt:
        print(f"FAIL: fixtures exemption — {name} should{'' if exempt else ' not'} be "
              f"exempt"); sys.exit(1)
if read_real(HOOK) is None:
    print(f"FAIL: {HOOK} is missing, so reachability was computed from no root"); sys.exit(1)

reach = reach_from(read_real)

# Checks whose LIVE gate runs at another lifecycle point. The edge scan
# deliberately refuses --self-test invocations as wiring, so a check that
# correctly runs only its self-test at commit time reads as unreached — this
# declaration names each such check together with the lifecycle file that must
# still wire its live run, and that wiring is asserted rather than trusted:
# an entry whose named file no longer invokes it excuses an unwired check, and
# an entry the hook DOES reach live is a stale declaration hiding nothing.
# The basename test below guards the DECLARATION from dangling, nothing more —
# WHICH lifecycle scripts must run WHICH entry points is owned by
# check-package's publication-provenance leg, which asserts the prepack and
# prepublishOnly pairs exactly; a second exact copy here would be the third
# restatement AGENTS.md warns a gate's own copy always becomes.
LIFECYCLE_GATED = {
    D + 'check-publish.sh': 'package.json',   # prepack/prepublishOnly run the live gate
}
for path, wiring in LIFECYCLE_GATED.items():
    wtext = read_real(wiring)
    if wtext is None or path.split('/')[-1] not in wtext:
        print(f"FAIL: {path} is declared lifecycle-gated by {wiring}, but {wiring} wires "
              f"no script to it — the declaration excuses a check nothing runs"); sys.exit(1)
    if path in reach:
        print(f"FAIL: {path} is declared lifecycle-gated yet the pre-commit hook reaches "
              f"it live — a stale declaration hides the next unreached check"); sys.exit(1)

orphans = [s for s in subjects if s not in reach and s not in LIFECYCLE_GATED]
if orphans:
    print("FAIL: check(s) never reached from the pre-commit hook, so they gate nothing at "
          "commit time: " + " ".join(orphans)); sys.exit(1)

# Controls, run every time rather than kept in a self-test.
#
# 1. The closure must come from the WIRING. Empty the hook and nothing may remain reachable.
#    This passes trivially under the current definition and that is the point: it is a
#    regression control, and it does not survive the revert. Seeding the umbrellas as roots
#    beside the hook — which is what this replaced — leaves the whole closure standing with an
#    empty hook, and that seeding is why dropping an umbrella from the hook used to change no
#    finding. A per-edge control is NOT usable here: the two umbrellas cite each other and
#    install.sh reaches the package gate a second way through the install scenarios, so every
#    subject has a redundant path and no single edge is load-bearing.
if reach_from(lambda rel: '' if rel == HOOK else read_real(rel)):
    print(f"FAIL: checks are still reported as reached with {HOOK} emptied — reachability is "
          f"seeded from something other than the wiring"); sys.exit(1)

# 2. Traversal follows shell only. A Python file naming a gate is describing it; treating that
#    as an invocation is how a docstring made a module look wired.
FAKE = {HOOK: './gates/one.sh', 'gates/one.sh': 'python3 gates/two.py',
        'gates/two.py': './gates/three.sh'}
seen_fake = reach_from(FAKE.get)
if 'gates/two.py' not in seen_fake:
    print("FAIL: reach traversal dropped a shell-invoked python check"); sys.exit(1)
if 'gates/three.sh' in seen_fake:
    print("FAIL: reach traversal followed a path named inside a .py file — prose there is a "
          "description, not an invocation"); sys.exit(1)

# 2. The two exclusions have to actually exclude, and the extractor has to see every path on a
#    line. Both were wrong at once: the tail ran to EOL, so `for gate in A B` registered only A,
#    and the file-test guard readmitted a gate whose only real invocation is its self-test.
probes = [
    ("for gate in gates/a.sh gates/b.sh; do\n  \"./$gate\"\ndone",
     {"gates/a.sh", "gates/b.sh"}, "a list whose body runs the variable"),
    ("for gate in gates/a.sh gates/b.sh; do\n  :\ndone",
     set(), "a list whose body never runs the variable — the reported gap"),
    ("if [ -x gates/a.sh ]; then", set(), "a file test is a predicate, not an invocation"),
    ("./gates/a.sh --self-test >/dev/null", set(), "a self-test run is not default-mode coverage"),
    ("# gates/a.sh", set(), "a comment executes nothing"),
    ("./gates/a.sh && python3 gates/b.py", {"gates/a.sh", "gates/b.py"}, "chained invocations"),
    ("false && python3 gates/dead.py", set(), "a constant-false guard never executes"),
    ("if false; then\n  python3 gates/dead.py\nfi", set(),
     "a constant-false block never executes"),
    ("if true; then\n  ./gates/a.sh\nfi", {"gates/a.sh"}, "a live block still counts"),
    ("unused() {\n  python3 gates/dead.py\n}", set(),
     "a function nothing calls never executes"),
    ("used() {\n  python3 gates/b.py\n}\nused", {"gates/b.py"},
     "a called function's body counts"),
    ("inner() {\n  ./gates/a.sh\n}\nouter() {\n  inner\n}\nouter", {"gates/a.sh"},
     "transitive calls reach the leaf"),
    ("run_gate() {\n  python3 gates/dead.py\n}\nif false; then\n  run_gate\nfi", set(),
     "a helper called only from a dead block never executes"),
    ("if true; then\n  :\nelse\n  python3 gates/dead.py\nfi", set(),
     "the else of a true condition never executes"),
    ("if false; then\n  :\nelse\n  ./gates/a.sh\nfi", {"gates/a.sh"},
     "the else of a false condition is the LIVE branch"),
    ("if ! true; then\n  python3 gates/dead.py\nfi", set(),
     "a negated literal is a literal"),
    ("if ! false; then\n  ./gates/a.sh\nfi", {"gates/a.sh"},
     "a negated false is live"),
    ("cat <<'EOF'\npython3 gates/dead.py\nEOF", set(),
     "a heredoc body is data, not shell"),
    ('cat <<"EOF"\npython3 gates/dead.py\nEOF', set(),
     "a double-quoted delimiter is still a heredoc"),
    ("cat <<\\EOF\npython3 gates/dead.py\nEOF", set(),
     "a backslash-quoted delimiter is still a heredoc"),
    ("cat <<'EOF'\nwords\nEOF\n./gates/a.sh", {"gates/a.sh"},
     "a command after the heredoc still counts"),
    ("for gate in gates/dead.py; do :; done\nfor gate in gates/live.py; do\n  \"./$gate\"\ndone",
     {"gates/live.py"}, "a loop variable's invocation binds to its own loop"),
    ("for g in gates/a.sh; do \"./$g\"; done", {"gates/a.sh"},
     "a one-line loop still counts its same-line invocation"),
    ("for gate in gates/dead.py; do echo \"./$gate\"; done", set(),
     "an echoed loop variable is diagnostics, not an invocation"),
    ("for gate in gates/dead.py; do\n  for gate in gates/live.py; do\n    \"./$gate\"\n  done\ndone",
     {"gates/live.py"}, "a nested same-name loop shadows the outer binding"),
    ("for outer in gates/a.sh; do\n  for inner in gates/b.py; do\n    \"./$outer\"\n  done\ndone",
     {"gates/a.sh"}, "a different-name nested loop does not shadow"),
    ("for gate in gates/dead.py; do\n  for gate in gates/live.py; do\n    :\n  done\n  \"./$gate\"\ndone",
     set(), "same-name reuse with a post-loop invocation is REJECTED, not modeled: the "
            "leaked binding runs the inner value, so the outer list is never credited, "
            "and the inner loop earns credit only from its own body — a hook written "
            "this way reads as unreached and gets restructured, the fail-loud direction"),
    ("! true && python3 gates/dead.py", set(),
     "a negated literal in a short-circuit guard is dead"),
    ("! false && ./gates/a.sh", {"gates/a.sh"},
     "a negated false in a short-circuit guard is live"),
    ("helper() {\n  # }\n  python3 gates/dead.py\n}", set(),
     "a commented brace does not close the function early"),
    ("shown() {\n  echo \"}\"\n  ./gates/a.sh\n}\nshown", {"gates/a.sh"},
     "a quoted brace does not close the function either"),
    ("function unused {\n  python3 gates/dead.py\n}", set(),
     "the bash function-keyword form is a declaration too"),
    ("function unused() {\n  python3 gates/dead.py\n}", set(),
     "the keyword-plus-parens form is a declaration too"),
    ("function used {\n  ./gates/a.sh\n}\nused", {"gates/a.sh"},
     "a called keyword-form function still counts"),
    ("unused() (\n  python3 gates/dead.py\n)", set(),
     "a subshell-bodied function nothing calls never executes"),
    ("used() (\n  ./gates/a.sh\n)\nused", {"gates/a.sh"},
     "a called subshell-bodied function counts"),
    ("unused ()\n{\n  python3 gates/dead.py\n}", set(),
     "a next-line opener is still a declaration"),
    ("used ()\n{\n  ./gates/a.sh\n}\nused", {"gates/a.sh"},
     "a called next-line-opener function counts"),
    ("function unused\n{\n  python3 gates/dead.py\n}", set(),
     "the keyword form also takes its opener on the next line"),
    ("function used\n{\n  ./gates/a.sh\n}\nused", {"gates/a.sh"},
     "a called keyword next-line function counts"),
    ("while false\ndo\n  python3 gates/dead.py\ndone", set(),
     "a dead loop's do may arrive on the next line"),
    ("while true\ndo\n  ./gates/a.sh\n  break\ndone", {"gates/a.sh"},
     "a live loop's next-line do keeps its body"),
    ("run_checks() { python3 gates/b.py; }\nrun_checks", {"gates/b.py"},
     "a one-line body on the declaration line is body"),
    ("run_checks\nrun_checks() { python3 gates/dead.py; }", set(),
     "a top-level call above its definition is command-not-found, not wiring"),
    ("outer() {\n  inner\n}\ninner() {\n  ./gates/a.sh\n}\nouter", {"gates/a.sh"},
     "a body's forward reference resolves when its caller runs after both definitions"),
    ("unused() { python3 gates/dead.py; }", set(),
     "an uncalled one-line helper stays dead"),
    ("run_checks() {\n  ./gates/a.sh\n}\nMODE=full run_checks", {"gates/a.sh"},
     "an assignment-prefixed helper call is a call"),
    ("run_checks ()\n{ python3 gates/b.py; }\nrun_checks", {"gates/b.py"},
     "a next-line opener carrying the body keeps it"),
    ("unused ()\n{ python3 gates/dead.py; }", set(),
     "an uncalled next-line one-liner stays dead"),
    ("while false; do\n  python3 gates/dead.py\ndone", set(),
     "a while-false body never runs"),
    ("until true; do\n  python3 gates/dead.py\ndone", set(),
     "an until-true body never runs"),
    ("while true; do\n  ./gates/a.sh\n  break\ndone", {"gates/a.sh"},
     "a while-true body is live"),
    ("until false; do\n  ./gates/a.sh\n  break\ndone", {"gates/a.sh"},
     "an until-false body is live"),
    ("echo ok # python3 gates/dead.py", set(),
     "a trailing comment is not an execution edge"),
    ("./gates/a.sh  # runs the umbrella", {"gates/a.sh"},
     "a command with a trailing comment still counts"),
    ('echo \\" # python3 gates/dead.py', set(),
     "an escaped quote is a literal, and the comment after it is a comment"),
    ('echo \\"ok\\" && ./gates/a.sh', {"gates/a.sh"},
     "escaped quotes do not swallow the live command after them"),
    ('for gate in gates/dead.py; do\n  echo "; ./$gate"\ndone', set(),
     "a separator inside a quoted diagnostic anchors nothing"),
    ('unused() {\n  python3 gates/dead.py\n}\necho "; unused"', set(),
     "a helper name inside a quoted string is not a call"),
    ('unused() {\n  python3 gates/dead.py\n}\necho ok # ; unused', set(),
     "a helper name inside a trailing comment is not a call"),
    ('unused() {\n  python3 gates/dead.py\n}\nunused=1', set(),
     "assigning a variable that shares the helper name is not a call"),
    ('echo "; ./gates/dead.py"', set(),
     "a quoted literal path is a diagnostic, not an edge"),
    ('echo "see gates/a.sh for details"', set(), "a path named in prose is not an invocation"),
    ('"$VENV/bin/python" gates/b.py', {"gates/b.py"}, "an interpreter held in a variable"),
]
for text, want, why in probes:
    got = edges(text)
    if got != want:
        print(f"FAIL: reach edge extraction — {why}: {text!r} gave {sorted(got)}, "
              f"expected {sorted(want)}"); sys.exit(1)

REACH

# The launcher's Textual preflight UI tests need the managed venv (textual).
# Provision it if missing; every non-UI check above runs under system python.
VENV="${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}"
if ! { [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import textual' 2>/dev/null; }; then
  echo "provisioning agent-launch venv for parity UI tests ($VENV) ..."
  AGENT_LAUNCH_VENV="$VENV" bash launch/provision-venv.sh >/dev/null 2>&1 || {
    echo "FAIL: could not provision the textual venv required for UI parity tests"; exit 1; }
fi
export AGENT_LAUNCH_VENV="$VENV"

# Runtime-projection checks (role slots, wrapper defaults, launcher behavior) live in
# gates/check_parity.py — a real module so it can be syntax-checked and read.
if ! AGENT_BIOS_LEGACY_INSTALL=1 "$VENV/bin/python" gates/check_parity.py; then
  fail=1
fi

# Default private installation and the manager are exercised independently of
# the retained legacy migration regression fixtures above.
if ! "$VENV/bin/python" launch/test-tier-effort.py; then
  fail=1
fi
if ! "$VENV/bin/python" -m unittest discover -s compose -p 'test_corpus*.py'; then
  fail=1
fi
if ! "$VENV/bin/python" gates/test-slide-writing.py; then
  fail=1
fi

[ "$fail" -eq 0 ] && echo "PARITY OK: mirrors, globals, guides, domain manifest, assembler, launch profile, bypass paths, role bindings, and wrapper defaults aligned"
exit "$fail"
