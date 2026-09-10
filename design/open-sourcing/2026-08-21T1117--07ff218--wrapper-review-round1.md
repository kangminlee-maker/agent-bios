---
created_at: 2026-08-21T11:17:00+09:00
head: 07ff218
kind: review
supersedes: none — first review round on the step-3 work
---

# Round 1 on PR #45 — nine findings, two of them blockers, and the fix delta found a tenth

Cross-family review of the step-3 change (wrapper + legacy removal), dispatched
after the PR was already open. The gates were green and the PR was written as if
that meant something; it did not. **Gates are not a review** — they are assertions
the author wrote, checked by a process the author ran.

## The dispatch

| | |
| --- | --- |
| Seat | `gpt-5.6-sol` @ effort `ultra` (openai — different provider, different family) |
| Route | `wrappers/codex-run.sh --profile hermetic` — temp `CODEX_HOME`, `--ignore-user-config`: no AGENTS.md, no corpus, no author instructions |
| Sandbox | `-s read-only`, `--cd` the core checkout |
| Receipt | `6abf6fbaaad84425b0bd255db1487ca4` — packet `f922fd92…`, result `aa3212bc…`, exit 0 |

The packet marked every intent statement as **the author's claim** and asked for
falsification, listed six invariants, and required the reviewer to state which
invariants it did NOT exercise. That last instruction earned its place: the
sandbox had no writable temp dir, so the self-tests and E2E could not run, and
the reviewer declined to report the stdin invariant as held rather than
inferring it.

## Findings, all nine confirmed against the code

| # | Sev | Finding |
| --- | --- | --- |
| 1 | blocker | The wrapper pinned `#83b8fd2` (pre-change core) while calling the post-change signature. A fresh install crashes in `setup` and, on the forwarding path, `\|\| true` swallowed it and ran the unvalidated core. |
| 2 | blocker | Warn-only provisioning left a PREVIOUS organization's slot in place and forwarded anyway — a machine changing orgs uploads to the old endpoint and settles the record. |
| 3 | high | Two independent `os.replace` calls installed the pair, so a failure between them left a new token against an old endpoint: complete enough for the core to accept and send. |
| 4 | high | The bash core-locator accepted any adjacent `../agent-bios`; the Python side had been fixed to require a `node_modules` parent. The two disagreed, and bash won. |
| 5 | high | The values-equal fast path returned `unchanged` without repairing modes, leaving a 0644 token under a 0755 directory. |
| 6 | high | The new gate leg's decoy hook dir was never handed to the resolver — the resolver takes a slot root and nothing else, so the fixture was unreachable **by construction**. The paired source scan matched `"hooks"` only in double quotes, and the single control tripped both assertions, so neither was isolated. |
| 7 | medium | "Editing `org.json` alone adopts this" was false: package name, bin name, README and diagnostics were day1-specific. |
| 8 | medium | `ontology/instances/graph.json` §lexicon (and the generated `LEXICON.md`) still declared the slot "wins over the legacy dashboard-owned hook dir" — the *declared authority* for the concept, contradicting the code, with every gate green. |
| 9 | medium | `invalid_base` accepted query/fragment while the request path is appended by concatenation, so `https://h.test?t=1` sends to `/?t=1/api/ingest/learnings`. Pre-existing, but newly load-bearing: it is the wrapper's only acceptance validator. |

## What the two blockers have in common

Both are the **instrument agreeing with the author**. #1 passed every local test
because `node_modules/agent-bios` was a symlink to the working clone rather than
the declared dependency — the E2E measured a core the wrapper does not ship. #6
is the same defect the PR body boasted of having caught elsewhere, re-introduced
in the same change: an assertion whose subject the code cannot reach.

The already-recorded personal learning covers exactly this ("a measurement that
AGREES with your expectation is the moment to test the instrument"). It did not
fire. Reading it is not the same as running it.

## The fix delta produced its own defect

Finding #6's fix added an E2E case asserting "the core never ran" by grepping the
output for `DEPLOYED`. `agent-bios status` never prints that word, so the check
passed unconditionally — a vacuous assertion written **within the hour** of
confirming a vacuous assertion. Caught by running `status` and reading its real
output. The check now greps `source:` and carries a positive control requiring
that same needle to be PRESENT in the case where the core does run.

That is the third instance of one pattern in this initiative, and the rule that
would have caught all three is mechanical: *before asserting a needle is absent,
prove the needle appears when the thing IS present.*

## Fixes, and what each is proven by

| # | Fix | Proof |
| --- | --- | --- |
| 1 | pin bumped; provisioning crash is caught and reported as a pin mismatch; the forwarder aborts on any non-zero | self-test case 15 plants a pre-change-signature core and requires exit 1 with nothing written |
| 2 | `Refusal.blocking`; the no-token case is benign only when no slot, or a slot already naming this org's endpoint | self-test 12/13 (both directions) + E2E case 6 through the bin |
| 3 | `write_pair` snapshots and restores on failure; url first, token last | self-test 11 breaks `os.replace` for the token file and asserts the old pair survives intact |
| 4 | bash requires a `node_modules` parent, matching Python | — (structural; no control) |
| 5 | `modes_correct()` is part of "unchanged" | self-test 14 |
| 6 | the runtime assertion moved to the DRAIN, which does receive the home; source needle is the bare word; two controls, each catching only one assertion | m68 (drain-only: fallback in `drain_uploads`, invisible to the scan) and m70 (source-only: a dead single-quoted mention) |
| 7 | README states both steps honestly | — |
| 8 | graph.json §lexicon rewritten, `LEXICON.md` re-emitted | `emit-lexicon --check`, `check-lexicon`, `check-ontology` |
| 9 | `invalid_base` rejects query/fragment | two new self-test rows in the collector |

**#4 has no negative control.** A bash string comparison is not worth a planted
mutation, and saying so is cheaper than a control nobody would trust.

## Open after this round

- The wrapper is not re-verified against a REAL fresh install of its pin until
  the pin's commit exists on the remote. Until then `test/e2e.sh` with an
  argument is testing a checkout — the exact blind spot that produced #1.
- Round 2 has not been run. Every fix above is a fix delta, and this repo's own
  record is that fix deltas are a defect source; the tenth defect in this very
  document came from one.
