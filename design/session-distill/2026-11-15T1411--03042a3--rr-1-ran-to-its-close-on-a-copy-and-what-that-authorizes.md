---
created_at: 2026-11-15T14:11:00+09:00
head: 03042a3
kind: review
supersedes: none (it reports the run D-20261113-855ad2 names as release 1's authorization)
---

# RR-1 ran to its close on a copy, and what that authorizes

RR-1 is the one real run D-20261113-855ad2 puts in place of the plant table for release 1: S0 to S7 and S9 to S12
on a recent window of the owner's sessions, applied to a copy of the checkout. It ran between 2026-11-14 and
2026-11-15 as run `rr1-20261114b` and every stage it has a record for ended `complete`, except S10, which is
`partial` because the owner decided five rows and left forty-nine undecided. This record says what the run did,
which of the plan's §4.3 items it gives, and what it leaves open. The figures below were read from the run
directory and the logs on 2026-11-15; re-derive them from there before acting on any.

## What ran

- Window 2026-11-12T21:00 to 2026-11-13T00:00 (Asia/Seoul), posture production, declaration sequence 10 at the
  review. The owner approved the run, the three-hour window and a total of 30M tokens.
- S1 to S2: 13 sessions eligible, 32 children, 146 windows. S3 read them with one unit left `read_partial` when
  its budget ended with 13 windows unread, and one unit quarantined; both are disclosed in the run.
- S4 formed 16 candidates; the lifecycle intake brought 142 legacy entries, 5 clusters and 177 redundancy hints.
  S6 judged every formed candidate and cluster and a declared sample of one legacy entry and one hint.
- S7 proposed for the five candidates both judges admitted; S7b agreed with all five. Every candidate's kind is
  `unclassified`, whose only allowed disposition is `none`, so no proposal carries an operation.
- S9 rendered 54 rows (5 proposed, 15 disputed, 27 defaulted or left out, 7 rejected). S9b marked the Korean of
  all five proposals as still failing after one regeneration; the page shows that mark.
- S10: the owner approved rows 1 to 5 and left the rest blank. S10b: the owner confirmed the set (0 items that
  change the library, 5 ledger-only).
- S11 wrote nothing: 0 items, 0 file changes. S12 appended the window row to the copy's ledger and promoted the
  coverage state; it ran no git and no installer, and the copy's two changed files are uncommitted.
- Tokens: S3 15.97M, S4 1.04M, S6 4.20M, S7 2.07M, S7b 0.61M, S9b 0.39M; 24.29M of the 30M. S10 to S12 made no
  model call.

The run did not stay on one commit. Defects it met were fixed on `wp/11b-inventory` between stages, each fix under
the full commit hook, and the run's clone was moved to the new commit before the next stage: the window measure
(e4363257), the legacy call and the route rule (fc18cb14), the bar names in S7b's packet (d7e58f21), the review's
document of unjudged legacy entries (1bef21d8), and S9's input rule for an earlier S9b review (e09bfcfb). A run
of the released package will not have that help; what the fixes changed is what a first run would have stopped on.

## Against §4.3

| Item | What RR-1 gives |
| --- | --- |
| (a) preflight with receipts on the pinned hosts | The run's calls carry their own receipts in the run directory. No separate preflight record was made for this run. |
| (b) every plant failed by name | Not given by RR-1. Moved to release 2 with the plant table (D-20261113-855ad2); per-stage self-test controls and revert trials stand in. |
| (c), (d) the rehearsal at contract scale, measurements with denominators | Not release 1's (the 2026-11-11 amendment). RR-1's per-stage token use is the only measurement, with n = 1 run. |
| (e) the X review receipt | Each package had its capped review rounds before the run. The reviews of S7, S7b and S9b as they ran live, and the second rounds of five packages, are still to be sent. |
| (f) the owner's authorization and the S0 budget | Given: the owner's go for the run, the window and 30M; the declaration carries each stage's budget and its amendments. |
| (g) clean checkout, umbrella green at the named HEAD | Given for the code: the hook ran 131 legs with 0 failed at 03042a3 and the tree is clean. The copy is not clean by design: it holds S12's two uncommitted files. |
| (h) the owner-destination guard equal before and after | Given: the three roots under the owner's home were compared before and after every step and never differed; every declared destination is the copy or a directory inside the run. |

## What RR-1 does not establish

- **The write path with a real change.** No proposal had an operation, so S11's journal, drift check, order
  check and file writes ran on nothing. In release 1 this is the expected outcome of every run until a kind other
  than `unclassified` can be derived; the path's evidence stays its fixtures and its three review rounds, all of
  which returned rework (2026-11-13T0652).
- **The apply to the real checkout.** D-20261113-855ad2 names it as the owner's step after the copy. It has not
  been run, and F-41 should be settled first: S12's printed command would commit a coverage file keyed by 7,398
  transcript ids.
- **That a person can review the page.** The owner could not: 54 rows in 656 KB, with no statement of what a
  non-proposal row is about (F-39). The decisions were taken from a summary the lead wrote by hand from the run's
  files, with the same row numbers.
- **That an approved `none` is kept.** S12 reports five decided items as recorded in the ledger; the ledger gained
  only the window row (F-40).
- **Anything S8 measures.** No change was tested, and none was made.

## Open before the publish

Queued defects from this run: F-36 and F-37 (the window measure and its retry), F-38 (a Codex usage limit read
as an unrecognised stop, with no command to end it), F-39, F-40, F-41; from before it, F-34 and F-35. The lead's
recommendation to the owner is to fix F-39 and F-41 before the publish, because the first is the screen a user
meets and the second puts session identifiers into a tracked file, to fix F-40's wording with them, and to ship
with the others disclosed. That choice, the remaining reviews, the push, the merge and the publish are the
owner's.
