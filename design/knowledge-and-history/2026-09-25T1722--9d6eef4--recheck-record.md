---
created_at: 2026-09-25T17:22:00+09:00
head: 9d6eef4
kind: review
status: review-fixes-rechecked-machinery-fixed-p00-accepted-p01-stale-no-stage-implemented
plan: 2026-09-25T1636--6fa562f--development-plan.json
supersedes: 2026-09-25T1639--6fa562f--review-fix-record.md
decisions: D-20260925-90ecdf
---

# The review fixes, re-checked: the documents hold, and the machinery needed six more fixes

The [review-fix record](2026-09-25T1639--6fa562f--review-fix-record.md) published the fixes for
the cross-provider review of the stage bundle and owed the reviewer's check of them. This record
carries that check and what was changed for it. The bundle members stamped
`2026-09-25T1636--6fa562f--` are unchanged; the fixes are in `gates/workenv/` and one sentence of
`CURRENT.md`.

## The re-check

The same reviewer (provider `openai`, model `gpt-6-astra`, effort `max`) read commit `9d6eef4`
in two passes from 16:56: documents until 17:08, machinery until 17:15. Each pass had its own
earlier result and was asked to re-run every finding against the successor, with the review-fix
record given as claims to test; the rationale ledger and the repository's working rules were
withheld. Packets, tree, results and receipts are in
`~/.local/share/agent-bios-workbench/team-env-20260920/review-stage-bundle-20260925-r3/`.

| Pass | Earlier findings | Resolved | Partly | New |
| --- | --- | --- | --- | --- |
| Documents | 16 | 16 | 0 | 1 (low) |
| Machinery | 6 | 4 (F1, F3, F4, F6) | 2 (F2, F5) | 5 (2 high, 3 medium) |

The documents pass checked all 162 required cases against the placement rule as stated and found
none misplaced; it found the list of 21 cases with driver-answered steps complete and correct. It
upheld the rejection of machinery F4. The machinery pass found no false acceptance through the
cover rule, and caught all 99 named reverts and the six reverts the review-fix record claimed.

## New findings and what was done

Each was reproduced in the tree before it was fixed.

| Id | Sev | Finding | Fix |
| --- | --- | --- | --- |
| documents N01 | low | `CURRENT.md` said P01 was unchanged, although its eighth completion clause now freezes the re-run rule | The sentence says P01 changes that one clause |
| machinery N1 | high | The driver required a `selects` row, so R0, whose four cases are the catalog's alone, could not run any (the rest of F2) | The driver asks only that the profile is a catalog profile that is not carried; R0's four cases now reach their family module and report `blocked` because it is not written yet |
| machinery N2 | high | A skipped test, or one marked as an expected failure, reported its case `passed` | Both report `failed` and say why |
| machinery N3 | medium | A rule counted as checked where a node in scope listed its contract, even if the case's steps of that contract were served by a node out of every binding scope (the rest of F5) | A rule counts only where a profile binding the case serves one of the case's steps of that contract in its own scope (`D-20260925-90ecdf`) |
| machinery N4 | medium | When two layers stated one refusal, only the last declared counted, so a legitimate placement could be refused depending on order | A case is refused only when no layer stating the refusal is in scope |
| machinery N5 | medium | The driver-equivalence test built its expectation through the function it tested, and left R0 out, so dropping atomic cases kept it green | The expectation is read from `case_map` alone over every open profile, R0 included, and a new control drops all atomic cases but one and requires the comparison to fail |

## Controls

Each fix was reverted in a copy of the tree, one at a time, and its test was required to fail:

| Revert | Test that failed |
| --- | --- |
| The driver requires a `selects` row again | R0 runs its catalog cases; the equivalence test |
| A skipped test counts as passed | the skipped-test case |
| An expected failure counts as passed | the expected-failure case |
| A rule counts where any implementation node in scope lists its contract | the unreached-contract-steps case |
| The last declared layer wins | the two-layer case, in both declaration orders |
| The equivalence expectation is filtered through the driver and empty pairs are skipped | the dropped-atomic-cases control |

The first attempt at the last revert left out the skip of empty pairs, and its control still
failed for the wrong reason, on the driver's refusals; the revert above is the faithful one.
`gates/workenv/test_driver.py` runs 24 tests (19 before) and `gates/workenv/test_cases.py` 74;
the workspace gate passes its unit tests and static analysis, and every profile's binding holds
(`CASES OK`). The evaluator still reads `run-7` as accepted `[P00]`, ready `[P01]`.

## Not done

- **This round's fixes have not been read by the reviewer.** The two review rounds are closed by
  this record; a further read is the owner's call.
- **P01 re-freezes** over the regrouped registry once V1's cases can be run.
- **V1** is next: the family modules its cases need, then V1 implemented, used here and tested.
