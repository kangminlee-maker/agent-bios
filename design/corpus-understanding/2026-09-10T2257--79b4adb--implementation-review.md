---
created_at: 2026-09-10T22:57:49+09:00
head: 79b4adb
kind: review
---

# Shell recovery, corpus understanding, and offline gate isolation

This records the uncommitted `feat/shell-connection-controls` working tree. It is
not a release or deployment receipt. Decision D-20260910-1e28d7 records the learning
boundary; the earlier shell opt-in decision remains unchanged.

## Implemented

- Shell restoration records initial ownership before publishing its script and
  startup hook. Receipt-less managed scripts are discovered conservatively.
  Reset/uninstall no longer silently leave that interrupted connection behind.
- Transaction replay checks ancestor links before any projection and again at
  writes. Only root-owned, exact macOS system aliases to `/private` are exempt;
  user/nested/leaf links are not. Installation repairs owned launcher executable
  permissions, removal validates installation metadata before changing shell state,
  and unavailable launchers preserve the native bypass path and its arguments.
- `understand!` groups effective corpus by coherent purpose/domain, pins its sources,
  and opens a scoped interactive learning session. The skill focuses questions on
  purpose, background, causal mechanisms, tradeoffs and limits, and respects stop.
- A personal discovery requires a native human turn, review of earlier tutor turns,
  and a later exact save confirmation. A successful requested-only note precedes
  the persistent trophy. Retries are idempotent; reset retires the active generation
  without deleting immutable learning history or allowing old awards to return.

## Verification

- Fresh full `gates/check-parity.sh`: exit 0, PARITY OK. Corpus suite: 222 tests,
  873.369 seconds. Slide suite: 24 tests, 15.440 seconds. Launcher/binding and
  tier/effort legs also passed. No skipped corpus tests were reported in this run.
- Package boundary and its 27 planted-violation controls passed. Ontology,
  lexicon, mirror, domain and whitespace checks passed.
- The four original regression tests fail against the pre-fix package and pass
  against the corrected source. Mounted shell navigation tests pass after waiting
  for the real screen mount/focus lifecycle before selecting an option.
- Independent Astra shell review exercised three initial SIGKILL points, interrupted
  updates, reset replay, parent-link substitution, direct rollback, and native fallback.
  Additional review findings were fixed and rechecked; no actionable issue remains.
- Independent Astra understanding review passed all 31 feature tests and real
  installer/store interruption, update, deletion, reset and stale-generation probes.
  Skill forward cases distinguished incidental ambiguity, tutor-first paraphrase,
  independent user criticism, unavailable provenance, and explicit stopping.
- A final development tarball was installed with npm in an isolated home. Its actual
  CLI passed help/install/verify, learning bundle pinning, shell restoration, reset,
  expired-session refusal and uninstall. Native global sentinels were unchanged.

The initial umbrella run exposed missing offline backend fixtures and the overly
broad rejection of macOS system aliases. Those were corrected before the fresh full
run above; the earlier failed run is not represented as successful.

## Shared main gate failure

On untouched main, golden capture inherits private-install detection from the
operator's HOME. Its inert `exit 0` backend then enters the private Codex app-server
path and closes before replying. This is test-environment contamination, not evidence
of a production transport fault. An isolated 126-cell differential reproduced the
reported controls with private state and passed with explicit legacy projection.

Capture now pins `AGENT_BIOS_PRIVATE_CORPUS=0`. Two real projection controls poison
installed state and inherited private mode; removing the pin makes both fail by name.
The offline receipt chain and shared launcher fixture also provide inert native
backend availability. `--real` remains outside that fixture, and fixture coverage is
labeled as such. The existing 126-cell golden is unchanged. `corpus_session.py` is
unchanged. A capture-only minimal patch was checked against main, not applied there.

## Evidence and limits

Author-side workbench evidence is retained in `shell-fixes.zl7KrO/` (full gate logs,
negative controls, final-package smoke and minimal main patch),
`shell-cross-review.hSBTvI/`, and `review-goldens-env.Jlrczo/`.

Native provenance tests use isolated host-format transcripts; dispatch tests use
inert backends. No new live provider learning conversation was run. Semantic
significance and originality remain tutor/user judgments, not machine proofs.
Local transcript checks are not authentication against the filesystem owner, and
ancestor validation does not claim immunity to replacement between validation and I/O.

The actual global Claude/Codex instruction files, `.zshenv`, and `.zprofile` still
match their pre-application fingerprints. No commit, push, live reinstall, main
checkout mutation, or publication was performed in this implementation turn.
