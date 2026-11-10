---
created_at: 2026-11-11T00:40:00+09:00
head: 062b76d
kind: design
supersedes: null
---

# Release 1 ships distill without S8, and the proof of help follows in release 2

This amends the implementation plan (`2026-10-20T2119--cc0498f--implementation-plan.md`) and the checkpoint
amendment (`2026-11-03T1102--f7aa36e--…`). Owner decision D-20261111-818391: the earliest npm publish comes first,
so the first release carries every stage but S8, and S8 with its harness and rehearsal is release 2's. Lead decision
D-20261111-e321c8 takes C2's checkpoint answers at their offered defaults. The design itself is unchanged: S8 stays
the mechanism's proof of help; this record moves it, and the rehearsal that depends on it, to the second release.

## Why

S8 is in every production run, not only in the rehearsal: a run tests its proposals on (cases × strata × repetitions
× configurations) actor episodes before the owner's decision and again on the final set after it. The rehearsal at
the contract scale is 165-298M input tokens (§8.2) and a production run is of the same order. Dropping the rehearsal
alone would halve the spend and save no calendar, because the harness (WP-16 to WP-19) and the 1,978-episode
matrices are needed by the first run anyway. Only deferring S8 removes them. Two of the redesign's three goals
(desktop sessions counted, one answer per checkout, delivery evidence) need no S8. A change applied without an effect
test is bounded by the owner's per-item approval (S10), the two-family judges (S6, S7b), the write-ahead journal
with revert (S11) and the 20 KiB global ceiling (WP-14). The measured scale of release 1's real proposals and episode
sizes re-bases §8.2's symbols before release 2 builds S8 at a scale chosen on measurements rather than assumptions.

## Release 1: what each package delivers without S8

| Stage | Package | Change from the plan |
| --- | --- | --- |
| S5 | WP-10 | none |
| S6 | WP-11 | none |
| S7, S7b | WP-12 | none: the behavior contract and the expected observation are still written (S12 seeds them; S8 tests them in release 2) |
| S8 | — | not run; every row carries the named test state `untested: s8_deferred`, never a blank |
| S9, S9b, S10 | WP-20 | the test column shows `untested: s8_deferred`; the §7.5 order falls back to the judges and S7b, and the header names the fallback; S10b is the owner's confirmation of the final set in one pass, with no confirmation episodes |
| S11, S12 | WP-21 | none; delivery verification reads WP-15's receipt |
| cutover | WP-22 | the runbook marks S8 deferred by name; the `AGENTS.md` §10 sentence stays, because WP-24 makes it true |
| shipping | **WP-24** (new) | the driver ships: `session-distill/` enters `package.json` `files[]`, the guide drops `audience: author`, no author-side import remains in the driver, every runtime dependency (the jsonschema pin, any host binary) is declared in `DEPENDENCIES.md`, and `gates/check-package.sh` holds the new boundary with a planted violation |
| authorization | **WP-23-lite** | replaces the two rehearsal runs: see below |

**WP-23-lite.** The plant table (`tables/plants.json`) is kept whole; every plant whose realization is golden or
replay runs, every live plant of S3 to S7 runs within the declared budget, and every S8 plant is listed with the
named state `deferred: s8_release_2`, never skipped silently. One real run, RR-1, runs S0 to S7 and S9 to S12 on a
recent window (RH-2's source scope, about three days) with the legacy intake, under the owner-destination guard:
S11 applies first to a copy of the owner's destinations, the copy is verified and reviewed, then the real
destinations receive the same operations. The authorization record cites §4.3 items (a), (b) restricted to the
non-S8 rows, (e), (f), (g) and (h), and names (c) and (d) as release 2's. A missing item is still a missing
authorization.

**Early release (WP-15 and F-22).** `compose/instructions_install.py`'s installation receipt (WP-15) and the fix of
F-22 (option 1: the activation records the rollout the host actually writes beside the thread id) ship in a patch
release before WP-21, so receipts and joinable Codex pins accumulate in the owner's state from that installation
on; without it, delivery verification and RR-1 would find no evidence for any past session. The F-22 option takes
its own decision record when the package lands.

**Release 2.** WP-16 to WP-19, S10b's second pass, and the rehearsal (RH-1 and RH-2 with S8) at a scale re-derived
from release 1's measurements, then the first production run with the proof of help.

## Checkpoints

- C3 stays after WP-11 (S5 checks and S6 judgments believable). WP-12's code work proceeds during C3; only its
  live done-when and its merge wait (the D-20261110-c2f013 pattern).
- C4 runs S7 on C3's run directory, adding only S7's calls; it does not re-read the window.
- C2's answers (D-20261111-e321c8): WP-10 starts now; an S3 follow-up package (WP-08e) fixes the expansion skip
  of a truncated record and replaces the 1.94 bytes-per-token assumption with per-host measured density; S4's
  placement is re-measured at C3.

## Ordering and lanes

- Lane E (evidence): WP-08e → WP-10 → WP-11 → (C3) → WP-12 → (C4) → WP-20 → WP-21.
- Lane L (shipping): WP-15 → F-22 → early release → WP-24 → WP-22.
- Lead: the merge of `main` (v0.19.4) into the integration branch before the early release; the checkpoints;
  WP-23-lite; the release commits. Push, merge to `main` and `npm publish` are the owner's commands.
- WP-20 and WP-21 take WP-12's proposal schema as an interface edge and are built on golden fixtures while WP-12's
  live done-when waits for C3; their own live done-whens follow C4.

## Budget of release 1

Development tests as §8.1 for WP-11, WP-12, WP-20 and WP-21 (about 0.3M input); C3 and C4 about 0.3-0.6M; RR-1
about 20-25M input (RH-2's table without S8, its scoring and the actor warm-ups: S3 about 3M, S4 0.6M, S6 3.5M,
sweeps 2.6M, S7 and S7b 4.4M, S9b 1.6M, Codex threads about 7.5M). Under 30M in all, inside the owner's usage
windows as measured so far (seven-day utilization 3% on 2026-11-10 23:22 after C2); every live step still declares
its budget and waits for the owner's go.

## What release 1 does not establish

- That an applied change helped: S8 is the only measure, and release 1 has none.
- The live plants of S8 and the usage-window and p95 measurements (§4.3 (c), (d)).
- A first apply to the real destinations rehearsed on a seeded corpus: RR-1's copy-then-real sequence stands in.

## Not changed

Two review rounds at most per package, a pretrial per fix, fixtures only in development, no live call before the
owner's go, the 20 KiB global ceiling, the dated-record rule, and the checkpoint pages as local files.
