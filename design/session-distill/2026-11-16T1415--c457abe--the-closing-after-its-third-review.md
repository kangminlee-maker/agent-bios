---
created_at: 2026-11-16T14:15:00+09:00
head: c457abe          # the commit reviewed; the answers are the next commit
kind: review
supersedes: none (it follows 2026-11-16T1128--79477c2--the-closing-after-its-second-review.md, which stays as written)
---

# The closing after its third review

The owner granted a third cross-family round on the closing as an exception to the two-round cap
(D-20261116-bdad83). Codex, pinned at c457abee, returned rework: round 2's three major findings are met, its minor
one partly, and four major findings are new. Review file: the lead's `work/lead/release1-x3-review.json`.

## What each became

- **The npm package could not start the driver** (major, reachable, since 2026-11-11). `package.json` `files[]`
  lists the driver's tables one by one and never gained `session-distill/grammar/` or five tables the driver reads
  (`controls.json`, `delivery_evidence.json`, `delivery_evidence_fixtures.json`, `unit_outcome.json`,
  `unit_outcome_fixtures.json`). A tarball packed from c457abee and run from its own files stops every command at
  startup (`STARTUP_FAILED`, a missing `unit_outcome.json`); the review found `grammar/` the same way. No gate asked
  what a shipped module reads, and every clone has the files. They are shipped now. `stage_delivery_fixtures.json`
  is read by its module's suite alone and cites the mechanism design under `design/`, so it is declared author-side
  instead. `gates/check-package.sh` gains two legs:
  - **classified tree members**: every tracked file under `session-distill/` is shipped by `files[]` or declared
    author-side with its reason (`UNCLASSIFIED` otherwise). What a module reads is not decidable there; whether
    every file was decided is.
  - **payload driver modules**: from npm's own expansion, copied alone beside a scratch home, the driver's
    `--help` runs and every shipped driver module imports (`PAYLOAD_DOES_NOT_START` otherwise). A read made only
    once a command runs is not reached; the classification is what asks about those files. An interpreter without
    the pinned jsonschema skips the leg and says so.
  Two self-test cases plant each: `grammar/` dropped from `files[]`, and `unit_outcome.json` withheld while
  declared author-side, which the classification accepts and the start refuses.
- **A host home moved by its variable** (major once the package starts). `drift.library_place` named a `.claude`
  or `.codex` component and a checkout's trees, so a skill under `CLAUDE_CONFIG_DIR` or `CODEX_HOME` with an
  ordinary name, or under a default home that is a symlink, was a writable run directory and S12 destination.
  `drift` reads no configuration, so it now takes the homes as given and compares them case-folded, and
  `inventory.instructions_place` gives it every home `inventory.host_homes` resolves for the environment - the
  installer's rule, not a copy of it - with symlinks followed. The driver's admission and S12's destinations ask
  `instructions_place`. A first version resolved the homes inside `drift`; a revert trial showed drift's suite
  naming the environment read only once the call to it was gone, so its own audit had not seen it. The run
  directory refusal now comes before inventory's own protected-root check, so the driver's host-home control names
  `RUN_DIR_IN_INSTRUCTIONS`.
- **A standalone inventory's `--to`** (major once the package starts). It enters no run, so `run_dir_of` never
  judged it, and another checkout's skill was a destination. `distill.outside_instructions` is now the one
  admission for a run directory and for `--to` (`INVENTORY_TO_IN_INSTRUCTIONS`), before any root is resolved or
  read.
- **A parent replaced after admission** (major once the package starts): not changed, and stated. The admission
  reads the destination as it resolves when the command starts; a parent directory another process replaces with
  a link before S11 takes its first lock redirects that lock and what follows. Holding it means binding admission
  to directory descriptors through the first lock and every later write, a change to `stagelock` and every writer.
  The actor this needs can already write the instruction file itself, so the property release 1 holds is that
  distill's own decisions and commands write no instruction file; this race is the owner's to accept or to have
  fixed before the publish (the decision request after this review).
- **The scope control's subject** (round 2's minor, partly met). The AST walk now reads the driver's `grammar/`
  package as well as `runlib/` and the driver, held by a control that names them.
- **Found on the way: the effect audit's blind spot** (FINDINGS F-46). `destinations._effect_reachable` reads a
  function that only its own module's suite calls as suite code, though other modules call it at runtime, so
  drift's audit never saw `library_place`. drift's docstring now states the one filesystem question that function
  asks; widening the audit is left open, because it widens every module's audit at once.

## Verification

Revert trials in `work/lead/pretrial-release1-r4.py` and `pt-release1-r4.log`: each Python answer reverted fails a
named control of its own suite, and each gate leg reverted lets its planted violation through, while the fixed gate
names c457abee's own `package.json` as `UNCLASSIFIED`.

## What is not claimed

- A table or file a shipped module reads only once a command runs is held by its classification, not by a run.
- No real npm install of this tree has run a distill command; the start leg runs the package's files in place.
- The late-parent race above.
- No real run has met the closing's refusals.
