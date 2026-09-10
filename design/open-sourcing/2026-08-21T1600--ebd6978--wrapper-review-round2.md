---
created_at: 2026-08-21T16:00:00+09:00
head: ebd6978
kind: review
supersedes: none — round 2 on the step-3 work, after the root-cause round
---

# Round 2 — the fix delta had twelve defects, and the mechanism built to prevent them was falsified

Two dispatches, same seat (`gpt-5.6-sol` @ ultra, `codex-run.sh --profile hermetic`,
read-only), different questions. Provider independence is a REPEAT of round 1;
what varies here is the question, which is what this repo's record says actually
finds new things.

A third framing was rejected by the provider before dispatch — a packet asking
the reviewer to "defeat" the mechanism was flagged as a cybersecurity risk. Same
substance, re-worded as a test-quality assessment, went through. Worth knowing:
the classifier reads intent from vocabulary, not from the repository it points at.

## R2-A — the fixes, reviewed as new code

Twelve findings, no blockers, seven high. All twelve confirmed. The three that
matter most were **controls I had written that did not control anything**:

| Fix | What its "control" actually proved |
| --- | --- |
| `write_pair` rollback | Nothing. The monkeypatched `os.replace` failed every token write, so `verify_through_core`'s disposable copy raised FIRST and the production write never ran. Proven by logging the attempts: only the staging directory was ever touched. A revert of all rollback logic passed the same way. |
| the wrapper's pin | Nothing about the pin. `test/e2e.sh` used whatever sat in `node_modules` without checking its revision — the exact blind spot that produced the blocker it was written for. |
| the source-scan needle (m70) | Nothing about the fix. The mutation planted BOTH `'hooks'` and `'dashboard-url'`, so reverting the quote-specific needle still failed on the other one. |

The generator behind all three: **a control that asserts an outcome without
asserting the path was taken.** "The slot is unchanged" is satisfied by a run
where nothing happened; "the E2E passed" is satisfied by any core; "the leg
caught it" is satisfied by any assertion in that leg.

A second generator repeats a lesson this repo already paid for: **falsy is not
absent.** `parts.query` is `""` for `https://h.test?`, so the new query/fragment
rejection accepted exactly the delimiters that corrupt the selector; an
unreadable slot returned `None` and was handled as "no slot"; an empty `legs`
selection returned a green partial run having judged nothing. The core fixed this
same shape at this same seam one session earlier (`is_file()` answering False for
absent AND unreadable) — and it came back in the wrapper and the gate.

Also real, and mine: the fail-closed handover was **command-blind**, so a stale
slot with no token locked the operator out of `install`, `verify`, `status` and
`help` — a safety measure that removes the recovery path. And `CANDIDATES` as a
space-joined string word-splits on any prefix containing a space.

## R2-B — the mechanism, assessed rather than trusted

Verdict: **the claim is false.**

> The new oracle proves reach at the granularity of a LEG; the audit proves
> dependency at the granularity of an AST STATEMENT. Several real checks share
> each unit, so individual rows, predicate clauses, subjects and input classes
> can disappear invisibly.

Nine blind-spot classes with one-line demonstrations. `ANY_URL` narrowed from
`https?://` to `https://` hides every plain-HTTP endpoint and both oracles stay
green, because every planted URL is HTTPS. `for rel in subjects[:-1]` drops the
last shipped file from the scan while the count still claims all of them. A
predicate clause can die behind a sibling assertion in the same leg.

**Root cause: granularity mismatch — the oracle's unit is coarser than the thing
being asserted.** The reviewer's proposed repair is per-assertion failure IDs,
with controls declaring expected IDs per leg.

## What this round changed

Closed, each with a control shown to fire:

- rollback control now asserts the production write was ATTEMPTED (`attempted`
  list); reverting the rollback produces the mixed pair and fails by name.
- `test/e2e.sh` reads `node_modules/.package-lock.json`, holds the resolved SHA
  against the declared pin, and prints the revision under test; a mismatch exits
  2 rather than testing something else.
- m70 plants one needle; the quote-specific revert now fails by name.
- `_expect` takes a needle PER LEG. This immediately exposed all eight two-leg
  controls: `anchors` was failing for a different reason than the `wire` needle
  in every one of them, so none pinned either assertion. They now declare both.
- `_copy_tree` asserts the scratch subject set equals the real one.
- `collect()` materializes `legs` and refuses an empty selection.
- The CLI-level zero-egress probe: the SHIPPED command, a home with no slot and
  a dashboard-shaped hook dir in the config home, must send nothing — with its
  own control (a provider re-added between the CLI entry and the drain, which
  neither the source scan nor m68 can see). Writing that control found the probe
  had planted its decoy in `$HOME` rather than the config home, where nothing
  reads it.
- `invalid_base` asks the RAW value for `?`/`#`; empty delimiters are rejected.
- `classify_status` is checked EXHAUSTIVELY over 100–599 against the declared
  sets. Planting the reviewer's 202 carve-out fails with the divergence named.
- The wrapper: tri-state `slot_state` (absent / complete / unusable), a slot
  lock, a rollback whose failure is loud, permissions repaired even with no
  token, command-scoped blocking (only `learn` refuses), quoted candidates.

## Open, and honestly open

- **Per-assertion IDs are not built.** The per-leg needle is the cheap half of
  that repair; rows, predicate clauses and input classes remain below the
  oracle's resolution. R2-B's other examples (`subjects[:-1]`, the `ANY_URL`
  narrowing, TOML skipped) are unfixed and would still pass today.
- The audit's grammar misses `.extend`, returned message expressions, and
  fail-open scalar returns; it also counts `_mutate`'s self-test-only raise as a
  gate statement. Its denominator is therefore approximate in both directions.
- 15 checks in the endpoint gate remain uncovered, unchanged from the previous
  round's disclosure.
- Round 3 has not been run, and this round's changes are themselves a fix delta.
