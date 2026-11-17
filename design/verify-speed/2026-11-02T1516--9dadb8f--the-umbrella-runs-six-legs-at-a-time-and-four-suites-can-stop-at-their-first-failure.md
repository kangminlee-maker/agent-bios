---
created_at: 2026-11-02T15:16:00+09:00
head: 9dadb8f
kind: design
---

# Verify speed: the commit umbrella runs its legs six at a time, its two heaviest suites stop re-reading what did not change, and four suites can stop at their first failure

This record closes the verify-speed package (decision D-20261102-3284cc): cut the verification time every later
work package pays, without removing or weakening a check. It has three commits on `wp/verify-speed`, based on
`43dc4bf`: S1 `765af6c`, S2 `9dadb8f`, and S3, the commit this record lands in. `head` is the commit the S1 and S2
figures were true at; S3's own figures were measured on `9dadb8f` with the S3 changes laid on it.

## Starting point (43dc4bf, 2026-11-02)

`gates/check-package.sh` took 1 s and `gates/check-parity.sh` 1370 s, every external leg run one after another
(clean clone, real HOME and venv, load about 4). The heaviest legs: `session-distill/runlib/dispatch.py
--self-test` 331 s, the compose `test_instructions*` unittests 283 s, `session-distill/runlib/inventory.py
--self-test` 225 s, `gates/test-install-guides.sh` 82 s, `gates/check-publish.sh --self-test` 81 s. Profiles
(cProfile): dispatch was CPU in `closure_violations`, which re-parsed every module of the import closure for each
of its 106 planted controls; inventory was CPU in the emitter (`_emit_value`, 38 million calls), in
`projection.disclosure_rules` (19 million calls) and in `schema_enum`, which read and parsed the schema file on
each of about 243,000 calls; the compose tests were flat (real install calls, subprocesses, per-test fixture
copies; sleeps 4.5 s in all).

## S1 — `765af6c`: the legs run six at a time

- `gates/check-parity.sh` records each external leg (`leg`) with its command line verbatim, its working directory
  and a digest of `export -p`; `gates/run-legs.py` runs them `AGENT_BIOS_PARITY_JOBS` at a time (default 6),
  prints each leg's output whole in declaration order, names each failing leg by its `FAIL:` line, refuses a leg
  whose environment changed since it was recorded, counts a crash or a signal as a failure, and fails unless the
  legs it ran equal the legs declared. Checks the umbrella makes in its own shell are unchanged. The runner's
  `--self-test` (23 controls) runs in the umbrella's main shell before any leg is recorded.
- Shared state was read leg by leg (tree writes, fixed temp names, HOME paths, the venv, sockets, git config) and
  measured by running every leg alone with a before/after inventory of the tree. Two legs write into the source
  tree while they run and so run alone, before the others (`-a`): `gates/test-install-guides.sh` (its scenario I13
  plants `claude/skills/repo-charter/gate-i13-probe.md`) and `session-distill/runlib/bound.py --self-test` (two
  files under `session-distill/runlib/`).
- The compose unittests run as four groups (ui, setup, store, rest) through `gates/compose-tests.py`, whose
  `--self-test` (6 controls) requires the groups to cover the 615 discovered test ids exactly once.
- The venv legs receive `AGENT_LAUNCH_VENV` per leg; a venv that cannot be provisioned skips them and fails the
  umbrella.
- `compose/test_instructions_setup.py`'s TTY apply test waited a fixed time before typing; it now waits until the
  review screen has drawn its Apply setup button with Back focused. Higher load is when the fixed wait failed.
- The umbrella and the hook unset `AGENT_BIOS_SELF_TEST_STOP_AT_FIRST_FAILURE` (S3's variable).
- Measured on a clean clone of 43dc4bf with the S1 files, real HOME and venv, load 8-10: 475 s, 472 s, 486 s in
  three consecutive runs, each 90 legs declared, 90 run, 0 failed, the tree's status the same before and after,
  no temp left by the runner. The commit's hook took 483 s. Pretrial: 28 revert rows of the runner's and the
  grouping's controls, each failing by its control's name, and both unmutated self-tests clean.

## S2 — `9dadb8f`: two suites keep a parse until its text or its file changes

- `dispatch.py` keeps each module's parse under its exact source text, two texts per file (the live one and a
  planted variant), with the walks its judges repeat (`_Parsed`). Controls:
  `the-parse-cache-answers-as-a-fresh-parse` (with a planted variant kept beside the live text, the closure,
  shape and rebinding judges answer as with the cache emptied) and
  `a-stale-kept-parse-is-told-from-a-fresh-one`.
- `inventory.py`'s `schema_enum` answers from a parse kept while the schema file's inode, size, mtime and ctime are
  unchanged (`kept_schema_enum`); `inventory_schema` still gives each caller a fresh parse, and a stand-in reader
  is asked directly. Five controls (fresh-parse answers for every shape; rewritten file re-read; same-size rewrite
  with the mtime put back re-read; removed file refused; stand-in asked).
- No control was removed or merged. Each suite's counted names (its own `ran` list, read from its `self_test`
  frame) before and after, in each of three passes: dispatch 520 -> 522, inventory 1140 -> 1145, nothing
  missing, the additions exactly the seven new controls, no name's count changed.
- Three passes of six suites at once (dispatch and inventory before and after, distill, projection; fake HOME,
  load 6-13 with one spike to 39): dispatch 345/367/369 s -> 112/121/125 s; inventory 233/253/259 s ->
  184/203/204 s; all 18 runs passed. Pretrial: 7 revert rows, each failing by its control's name.
- Not sped up: inventory's remaining time is the emitter and the disclosure judge, which this package leaves
  alone (the disclosure rules are a product judge); the compose tests' time is real install calls, subprocesses
  and fixture copies the tests write into, and as four groups they no longer bound the umbrella.
- The commit's hook took 293 s (90 legs, 0 failed), bounded by inventory's self-test (202 s), then dispatch
  (120 s) and `gates/check_parity.py` (98 s).

## S3 — stop at the first failure

- `runlib/entry.py`: `self_test_failures(label, publish=None)` gives a suite its failure list. With
  `AGENT_BIOS_SELF_TEST_STOP_AT_FIRST_FAILURE=1` it is a `FailuresThatStop`: a failure added by `append`, `+=` or
  `extend` is recorded, a line says the suite stopped, and `StoppedAtFirstFailure` (a `SystemExit` with code 1)
  leaves. Section guards catch `Exception` and let it through; `guarded` (inventory, distill) and dispatch's
  `main_boundary` publish the recorded failure as the suite's usual `[FAIL]` line; projection, which prints its
  own report outside the boundary, passes `publish`. The variable is read once and removed from the environment,
  so a suite started inside a stopping one (inventory runs one in-process) and every child run in full. Unset,
  the list is a plain list.
- The four suites change one line each, where the list is made. Where a suite catches `BaseException` or
  `SystemExit`, the try wraps a command run or an inner suite, never one of the outer suite's own controls; the
  threads dispatch's suite starts run product code, and its controls are judged in the main thread.
- Six controls in distill's suite drive a planted miniature suite through the real `entry.guarded`: set, it
  stops at its first failure with that failure's `[FAIL]` line and no later one; set, a suite with no failure
  runs to its end with its OK line and count although each control added an empty list (projection has a `+=`
  of a comprehension); unset, it runs on and reports every failure; a suite started inside a stopping suite runs
  in full; a failure added with `+=` stops it; a suite outside the boundary is handed its failure to print.
  Distill: 131 -> 137 controls.
- Pretrial (`s3-revert.py`, disposable copies): each of the four suites passes with the variable unset and set,
  and the two logs are byte-identical (inventory 190 s / 162 s, dispatch 116 s / 104 s, distill 20 s / 20 s); with
  a failure planted right after the list is registered and another right before the report, unset reports
  exactly both, set exactly the first, says it stopped and exits 1 (inventory in 0.3 s instead of 190 s, dispatch
  0.2 s instead of 116 s, distill 0.6 s instead of 20 s); and each of six faults planted in the mechanism fails
  its control by name.
- Adoption in the revert harnesses (outside the repository: `p2-revert.py`, `p1-revert-cuts.py`): a row with
  edits and no `also_fail` expectation runs first in stop mode; if the run stopped and its first failure is the
  row's named control, the verdict stands; otherwise the row runs again in full. A row with an `also_fail`
  expectation, and a BASE row, run in full only, because the rule's answer for them is known before a run.
  The sample (the lead's ruling: about 36 rows, not all 402; fixed seed 20261102) was 31 rows of
  `p2-revert.py` (BASE, 10 of the 53 rows with an `also_fail` expectation, 4 of the 9 rows that cut a section at
  `c71af0e`, 16 others) and 5 of `p1-revert-cuts.py`, run on `9dadb8f` with the S3 changes laid on, each row that
  stopped also run in full for comparison (`--measure`). One p1 row, M2c, was not run: its anchor no longer
  exists, and it is not among the 37 rows the last phase-1 sweep ran. Of the 23 rows that ran stopped first, the
  verdict stood for 14, and in all 14 it agreed with the full run's; 9 ran again in full because their first
  failure was another control (7 of them stopped within 3.1 s); 12 rows (11 `also_fail`, BASE) ran in full only.
  Every verdict was "yes", and BASE "unmutated: clean". The 14 standing rows took 1012 s stopped against 2715 s
  in full; the whole sample under the rule took 5329 s against 6752 s with every row in full (21% less, and 32%
  over the 23 rows the rule may stop).

## Left as they are

- Skipping legs by the paths a commit changed (deferred by the package's brief).
- Found while measuring, outside this package's scope, on the lead's list: `gates/check-endpoints.py`'s CLI probe
  reads an inherited `AGENT_BIOS_CORPUS_DIR`; an npm cache and `claude plugin validate` touch the real HOME; legs
  leave about 120 names in TMPDIR per run; the reachability extractor reads `<<< word` in a comment as a heredoc;
  scenario I13 plants into the source tree rather than a copy; `gates/check-publish.sh --self-test` writes loose
  objects into the repository's object store.
