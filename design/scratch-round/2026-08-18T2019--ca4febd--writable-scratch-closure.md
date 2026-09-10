---
created_at: 2026-08-18T20:19:00+09:00
head: ca4febd
kind: review
---

# Writable-scratch round — closure of all seven findings

Closes every finding of `2026-08-18T1858--bfcc567--writable-scratch-findings.md`.
Fixes landed in ca4febd on `scratch-round-closure` (off `bfcc567`, v0.12.0).
Every reproduction below used the reviewer's own mutation and control sequences;
every new control was then proven by faithful revert — the half of the fix it
guards was removed, the control failed BY NAME, and the fix was restored.

## Per finding

### 1. High — rollback left the active instruction surfaces at the current version

- **Reproduced**: the reviewer's two-commit probe, unmodified tree —
  `V1_BUNDLE=NEW LIVE BUNDLE`, codex region unchanged, `V1_STATUS=v1`.
- **Fixed at**: `compose/corpus-state.py` — `_assemble_at` materializes the
  target commit (`git archive` → tarfile) and runs *that commit's*
  `compose/assemble.py` in a sandbox against the live selection
  (`--domains/--claude-dir/--codex-dir/--state-dir`); `_locked_rollback`
  publishes the sandbox's `central/bundle.md` and merged Codex `AGENTS.md`
  inside the same undo transaction, after the corpus files. The sandbox codex
  home is seeded from the LIVE `AGENTS.md`, so the user's text outside the
  markers rides through the commit's own `merge_codex` untouched. Assembly runs
  BEFORE any live write: a failing assembly refuses with nothing to restore.
  Rollback also now refuses when no applied selection exists — a bundle cannot
  be assembled for a selection nobody made.
- **Control**: `corpus-state.py --self-test` — the fixture carries a RUNNABLE
  stand-in assembler with the real calling convention (two corpus commits, each
  stamping its own bundle and codex region); the clean-rollback leg asserts
  bundle `BUNDLE one`, codex region `CODEX one`, and the preserved personal
  line; the failed-rollback leg asserts the bundle and codex surfaces did not
  move. A `--help` probe pins the four flags against the REAL
  `compose/assemble.py`, so the stand-in cannot drift silently.
- **Revert-proven**: publishing loop emptied (`)[:0]:`) → FAIL
  "rollback moved the guides but left the live bundle at the current version"
  and "did not rewrite the codex AGENTS.md central region". Restored.
- **Mutation now**: reviewer probe re-run — `V1_BUNDLE=BUNDLE one`,
  `V1_CODEX_GLOBAL` holds `CODEX one` plus `MY OWN CODEX LINE`, `V2` all match.

### 2. High — concurrent rollbacks both succeed and leave a split corpus

- **Reproduced**: a rollback ran to completion (rc 0) while another process
  held an exclusive flock on the deploy-lock path; and the original probe's two
  sequential rollbacks in one second shared one backup directory
  (`corpus-rollback-20260818-192435` twice).
- **Fixed at**: `compose/corpus-state.py` — `_deploy_lock()` (a separate lock
  file, `corpus-status.json.deploy.lock`) held from target/backup calculation
  through the final status update; the status lock nests inside it on a
  different file, so no deadlock. Backup directories are per-transaction:
  timestamp + pid + uuid4 fragment.
- **Control**: self-test holds the deploy lock, spawns a real subprocess
  rollback, asserts it is still waiting after 1.5s with no file moved, then
  releases and asserts it completes to the target. The C3 leg asserts the two
  sequential rollbacks named DISTINCT backup directories.
- **Revert-proven**: `_deploy_lock` → `contextlib.nullcontext()` → FAIL
  "a rollback proceeded while another deployment held the deploy lock". Restored.
- **Known bound**: the 1.5s window means an extremely loaded machine could let
  an unserialized rollback finish before the poll; the assertion errs toward
  false-pass of the mutation, never false-fail of the fix.

### 3. Medium — rolling forward leaves files only the prior version deployed

- **Reproduced**: reviewer probe — `V2_LEGACY_EXISTS=True` after v1→v2, and the
  old self-test stayed OK with the removal loop replaced by `for rel in ()`.
- **Fixed at**: `compose/corpus-state.py` — the removal operand is
  `(deployed ∪ HEAD) − target`, where `deployed` comes from
  `_deployed_previously`: the `deployed_corpus` manifest the last rollback
  recorded into the status (new field, preserved by `cmd_project` like
  `rolled_back_to`), else the recorded rollback version's own commit, else
  HEAD. When the set cannot be established (unreadable status, a version the
  registry no longer carries, malformed manifest) rollback REFUSES, naming
  "cannot establish the deployed corpus", before any write.
- **Control**: self-test subprocess battery: rollback t1 → legacy present,
  fresh removed; rollback t2 → legacy REMOVED, fresh restored, status names t2;
  plus the refusal leg (ghost `rolled_back_to`, live files untouched).
- **Revert-proven**: operand reverted to HEAD-only → FAIL "rolling forward left
  a file that only the rolled-back version deploys". The reviewer's own
  `for rel in ()` mutation → the same FAIL plus "rolling back left a file the
  target version does not carry" — the previously vacuous removal control now
  fires in both directions. Restored.

### 4. Medium — locked status writes truncate; a later projection erases the state

- **Reproduced**: monkeypatched interrupted `write_text` — raw OSError escaped
  `record-apply` and left `b'{"current_version'` on disk, unreadable.
- **Fixed at**: `compose/corpus-state.py` — `_write_status` routes every status
  write (project, rollback's patch, record-apply) through
  `assemble.replace_atomically`, imported from the sibling module
  (D-20260818-d74b47); `record-apply` reports a write OSError as rc 1 with the
  prior status intact; `cmd_project` QUARANTINES an unreadable prior status
  (`corpus-status.json.corrupt-<ts>`) and reports it on stderr instead of
  silently discarding rollback/apply state.
- **Control**: self-test — truncate-then-raise write over record-apply asserts
  rc 1, valid unchanged status; a planted `{"current_version":` status run
  through subprocess `project` asserts the quarantine file holds the exact
  damaged bytes and stderr names it.
- **Revert-proven**: raw `STATUS.write_text` restored → FAIL "left the corpus
  status truncated" + "did not report failure (code=raised OSError)";
  quarantine reverted to `except ValueError: pass` → FAIL "silently discarded
  the damaged bytes" + "did not report the unreadable status". Restored.

### 5. Medium — the registration gate stays green without the second reader

- **Reproduced**: deleted `load_review_methods(trial_config)` from
  `_trial_registration`; `--only launcher_registration_wizard` stayed green.
- **Fixed at**: `gates/check_parity.py::launcher_registration_wizard` — a
  wizard-driven candidate with `instructions = "review {not_a_slot}"` parses
  clean through `load_config` and is refused only by `load_review_methods`;
  the control asserts the reader's own door ("unknown slot {not_a_slot}") on
  the refusal screen and a byte-identical user file.
- **Revert-proven**: same deletion → FAIL "the reader-specific refusal
  (unknown slot) never rendered — the trial ran only the first reader, not
  load_review_methods". Restored.

### 6. Medium — publication failure escapes raw and leaves its temp

- **Reproduced**: methods path made a directory; real wizard through
  confirmation → raw `IsADirectoryError`, completed
  `.review-methods.local.toml.<pid>.tmp` left behind.
- **Fixed at**: `launch/agent-launch.py` — `publish_atomically` generalized to
  bytes + optional mode (D-20260818-64e21e; receipt and preset callers
  unchanged), the wizard publishes through it, and an `OSError` becomes
  `verdict = "cannot write <target>: <exc>"` — rendered by the SAME refusal
  screen as a trial refusal, with the answers retained for another pass. The
  shared primitive owns the temp's lifecycle, so cleanup came with the reuse.
- **Control**: `launcher_registration_wizard` — directory-target fixture in its
  own sandbox asserts: no OSError escapes, "cannot write" on screen, no
  leftover temp, target directory intact.
- **Revert-proven**: inline unguarded write/chmod/replace restored → three
  FAILs by name (raw IsADirectoryError; no refusal screen; temporary left
  behind). Restored.

### 7. Medium — every registration trial leaks its temporary directory

- **Reproduced**: one narrow gate run grew ambient `agent-launch-register-*`
  dirs 166 → 168 (166 already leaked on this machine from earlier runs).
- **Fixed at**: `launch/agent-launch.py::_trial_registration` — one `finally:
  shutil.rmtree(trial, ignore_errors=True)` over everything after the
  `mkdtemp`: copies, candidate write, both readers.
- **Control**: the gate snapshots the temp area's trial-dir set before its
  first wizard run and asserts no new entries after all runs (happy, duplicate,
  bad-slot, publication-failure).
- **Revert-proven**: `finally` body neutered → FAIL "registration trials leaked
  their scratch director(ies): [four named dirs]". Restored; the four dirs the
  revert run leaked were removed by name.

## Decisions

- **D-20260818-23193e** — rollback assembles with the target commit's OWN
  assembler and publishes only its two owned surfaces; closed running the
  current assembler over historical source, and publishing the whole
  sandbox tree.
- **D-20260818-d74b47** — status writes reuse `assemble.replace_atomically` by
  sibling import; closed importing the launcher's primitive or adding a twin.
- **D-20260818-64e21e** — the wizard publishes through `publish_atomically`
  (bytes+mode); closed a wizard-local try/finally copy.

## What the reverts taught

- The reviewer's `for rel in ()` mutation — which the old self-test passed —
  now trips TWO controls, because the fixture finally carries a file that must
  be removed in each direction. A removal control is only real when the fixture
  deploys something the target lacks.
- The finding-5 revert failed ONLY on the screen assertion (byte-identity held,
  because the scripted run backs out at the confirm screen): the reader-door
  message, not the file check, is the discriminating half of that control.
- The finding-6 revert fired all three assertions at once; the leak control
  (finding 7) alone caught nothing about finding 6's temp file because the
  wizard's publish temp is not a trial dir — the two lifecycles need their own
  controls, which is why both exist.

## Verification denominator

`compose/corpus-state.py --self-test` green (~3s, now including the subprocess
battery); reviewer's finding-1/3 probe re-run green in both directions; full
`gates/check_parity.py` (62 checks) green in 41s with goldens unmoved;
`gates/check-lexicon.py` and `decisions/record-decision.py --check` green; the
pre-commit hook ran the full umbrella (check-package + check-parity) on the
commit. Not re-run here: installer E2E beyond the umbrella's scenarios, Textual
rendering, host CLIs — same bounds as the review round itself.

## Addendum (2026-08-18T22:10+09:00) — three P2 findings from the PR #40 bot review

Same procedure: reproduced with the reviewer's shape, fixed at the authority,
control asserting its own message, proven by surgical faithful revert (a
whole-file revert to ca4febd was tried first and taught its own lesson: the
controls live in the same file as the fixes, so reverting the file silences
the alarm with the defect — revert the fix half only).

1. **Codex region merged against a stale snapshot.** Reproduced: an AGENTS.md
   edit landed after `_assemble_at`'s snapshot was silently overwritten
   (rc 0, edit gone). Fixed: `_assemble_at` returns the codex CENTRAL TEXT
   extracted from between the sandbox's markers — never the merged file — and
   publication calls the current `assemble.merge_codex` against AGENTS.md as
   it exists at that moment (D-20260818-a67cf7, amending the mechanism of
   D-20260818-23193e; the region content still comes from the target commit's
   own assembler). Control: the clean-rollback attempt injects a MID-FLIGHT
   EDIT between assembly and publication and asserts it survives beside the
   rolled-back region. Revert (stale-snapshot publication restored) → FAIL
   "a user edit landing between the assembly snapshot and publication was
   overwritten".

2. **Permissions not preserved across the atomic replace.** Reproduced: a
   0600 AGENTS.md came out 0644. Fixed at `assemble.replace_atomically` — an
   existing target's permission bits are copied onto the temp before the
   swap (every caller inherits it: AGENTS.md, settings.json). Ownership is
   not copied: the process never has the privilege to change it. Control:
   the attempt chmods the seeded AGENTS.md to 0600 and asserts the mode
   after the merge. Revert (chmod line removed) → FAIL "publishing the codex
   region widened a user-restricted AGENTS.md from 0o600 to 0o644".
   Disclosed sibling, left open: the launcher's `publish_atomically` with
   `mode=None` (preset save) still gives a fresh temp umask mode — same
   class, not flagged, and an unasserted fix is not a fix.

3. **Selection revalidated under the deploy lock.** Reproduced: deleting
   `selection.json` while a rollback waited behind the lock escaped as
   `TypeError: can only join an iterable`. Fixed: validation moved INSIDE
   `_locked_rollback` (the pre-lock check is gone — one code path, validated
   where it is read); a missing/unreadable selection is the named rc-2
   refusal. Control: a subprocess rollback is held behind the deploy lock,
   the selection file is deleted, the lock released — asserts rc 2, the
   named refusal on stderr, and no file moved. Revert (validation restored
   to pre-lock only) → FAIL naming the escaped TypeError.

Branch state: `origin/main` (3ba80d5, spec-round-7 closure) merged first;
`decisions/decisions.jsonl` resolved by content-id union (109 records,
`--check` green). Full `gates/check_parity.py` green on the merged tree with
these fixes; corpus-state self-test green with the three new controls.
