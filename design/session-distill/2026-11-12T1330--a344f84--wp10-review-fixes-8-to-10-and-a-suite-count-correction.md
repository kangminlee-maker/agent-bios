---
created_at: 2026-11-12T13:30:00+09:00
head: a344f84
kind: review
supersedes: 2026-11-12T1210--5a18ebd--wp11-review-closed-and-wp10-review-fixes.md
---

# WP-10 X round 1, findings 6 to 10, and a correction to a measured count

Lane E, branch `wp/20-review`. This record continues
`2026-11-12T1210--5a18ebd--wp11-review-closed-and-wp10-review-fixes.md`. The earlier record covers
findings 1 to 5. Findings 6, 7 and 8 are commits of their own, and each message carries its
controls and revert trial. This record carries the correction finding 10 asks for, and says where
finding 9 is answered.

| # | Finding | Commit | What the code does now |
| --- | --- | --- | --- |
| 6 | A SCRIPT_RUNS row matched any value ending with its path | `b838512` | a run is admitted only for a path proven from the site's own `pathlib.Path(__file__).resolve()` (`_proven_path`) |
| 7 | A bulk or computed read of controls.json was invisible to the name scan | `a344f84` | S6 runs with the file sealed at `open` (`controls.sealed`) |
| 8 | A commented-out leg still counted as a leg | `e3aa8fb` | the leg gate reads the umbrella as shell (`commands`) |
| 9 | S5's module doc called all three outputs counts-only | this record's commit | each output's boundary stated and held on its own |

**DYNAMIC_LOADS keep the suffix rule (finding 6).** Six of their nine sites prove their path the
way script runs now must. The inventory's three loads of compose/ modules take a computed checkout
root, so they cannot. Binding them needs a declared root form, which is open.

**Finding 9.** `checks.json` and `controls.json` hold names, ids, hashes, scores and counts.
`checked-candidates.json` is the population S6 builds its packets from, and it holds the candidates
whole and the evidence records S6 shows beside them, redacted text included. The control now holds
the three outputs separately, against the texts the run's own stores hold.

## Correction: 37 suites, not 38

`2026-11-11T1325--94f6f77--every-suite-that-offers-a-self-test-has-a-leg-and-live-delivery-assembly-waits-for-its-first-consumer.md`
(its Measured table, the row "Self-tests") says "every session-distill module with a self-test:
38, 0 not rc=0". The measurement selected files by grepping for the text `--self-test`. At
`94f6f77`, 38 files under `session-distill/` and `session-distill/runlib/` contain that text. Only
37 of them define a `self_test` function and accept the flag. The 38th is `runlib/entry.py`, which
names the flag in its documentation only. Its exit code 0 is the exit of a module that ran no suite,
not a suite's evidence. So the row should read: 38 invocations, 37 suites, none not rc=0. Codex's
independent enumeration found the same 37, and so does a syntax-tree count over the commit's own
files.

The tool that made the row (`run-all-st.sh`, author-side, uncommitted) now counts a file as a suite
only when the file's output carries its own verdict line (`<name> --self-test: OK (` or a `[FAIL]`
line), and its summary names invocations and identified suites separately. Any later summary of
"every self-test" should be read with that distinction.
