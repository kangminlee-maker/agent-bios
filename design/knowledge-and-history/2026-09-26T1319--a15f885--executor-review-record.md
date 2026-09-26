---
created_at: 2026-09-26T13:19:33+09:00
head: a15f885
kind: review
plan: 2026-09-25T1636--6fa562f--development-plan.json
amends: 2026-09-24T2124--0fe13da--conformance-adapter-design.md
corrects: 2026-09-26T1010--911350d--world-features-record.md
decisions: D-20260926-769231, D-20260926-dc5ca2, D-20260926-e2998c, D-20260926-540dcf, D-20260926-239c74
---

# The executor, read by another provider: what it passed that it should not have

The owner asked for a cross-provider read of V1's preparation work, steps 3a and 3b, before any
V1 code is written on it. The executor is the verdict path of every later stage, so a pass it
gives wrongly would carry into each acceptance. This records what the read found, what changed,
and what the [10:10 record](2026-09-26T1010--911350d--world-features-record.md) stated that was
not so.

## How it was read

Three read-only-by-default passes of `gpt-6-astra` at effort max, each in a hermetic Codex home
on its own copy of the tree at `a15f885`, with the network off and leave to run the code:

- **core:** can the executor pass a case it should fail, or report a defect as blocked;
- **world:** is the world the driver builds the one each scenario states;
- **controls:** do the tests and the figures establish what the records claim.

The records and decisions went to the reviewers as claims to test. The first core pass ran for 23
minutes and was stopped by the provider's cyber-risk filter with no result. It was sent again
with its isolation question reworded to "what is the code under test given, answered by
reading", and that pass completed. Packets, results and dispositions are kept outside the
repository, in `team-env-20260920/review-executor-20260926/`.

The passes returned 28 findings: 7 core, 9 world and 12 controls. Several named the same defect.
Each was reproduced on the unmodified tree by running the reviewer's own probe before anything
changed, and each probe was run again after the fixes. One finding is disputed. One is accepted
as a stated limit.

## What the executor passed that it should not have

| Defect | Found as | Now |
| --- | --- | --- |
| A restart that lost a commit, answered afresh on resubmission, passed: the driver never saw the committed answer | W5 | At `after_commit_before_return` the code under test hands the point the answer it committed (`call.point(name, answer)`). The driver judges that answer, which the caller never receives, and the resubmission or later query must show it. CMP-SELECT, DC-ASK and DH-PENDING now fail under the reviewer's mutation |
| A process exiting with status 70 counted as killed at the armed point without reaching it | W6, T3 | The host says which point it reached before it exits; without that line the step fails |
| A value pending at the end of a run was never checked. N17's disconnect record could say the repository was deleted and pass | C1 | The withheld answer judges the faulted step. At the end of the run, a digest learned before its record is held to the record, and a record no answer ever shows blocks the case by name. N17-DISCONNECT-NEG is now `blocked`: its settled query names the partial carrier state only by digest |
| A file digest the owner mints was learned from the answer, not tied to the file the driver wrote | W1, C2 | Before a step, the digest of each file a record it carries or returns reads is known from the checkout, and the answer must state it. A given answer states it too |
| An observation made after a file edit set the checkout's first state. N09-C07-NEG started with the edited file and the draft already present | W3 | A record is dated by the first step that sends, carries or returns it. A fact about a path an edit changed by then belongs to the edit. N09's rules revision, whose source states no home, counts because an observation reads the same path from the tree |
| Stand-ins were replaced by value everywhere, so an operation name or a branch equal to a stand-in was rewritten | C3 | A stand-in is replaced only under a field of its kind: `checkout`, `commit`, or a digest field |
| A layer in scope could change a given answer unseen | C4 | A value the driver already knows is held, never learned again, so a changed given answer fails where it differs |
| A refusal that also carried a result passed | T2 | An answer is a result or a refusal alone |
| An implemented entry raising `NotWritten`, or code corrupting the driver's signing keys, was reported `blocked` | C5, C6 | Only a callable missing before anything runs blocks. The keys are checked after every reply |
| N27-SELECTION-NEG's checkout lacked the sibling its narrative names, so a reader matching by prefix passed | W2, T1 | The scenario states it: a `file_edit` writes `docs/adr-private/notes.md` before `bind_alice`, adding 6 spec lines. A prefix reader now fails |

## What was blocked that could run

- **SRC-02.** Its refused capture names a neighbouring repository, and that path was counted as a
  second checkout (W8). Checkouts now come from source selections only, and SRC-02 passes.
- **Manifests the code under test writes.** They were read as the checkout's first state, which
  blocked N07's successive memory manifests as conflicts (W7). A manifest member whose size the
  owner mints is now a file the code writes. It is left out of the first state and checked
  against the file after the step. The test double writes those files. CMP-ORDER's decision
  memory, a V1 case, is now checked this way instead of being pre-created with invented bytes.

## Disputed and accepted

**W4, disputed.** The reviewer read CMP-QUALIFIED's "bytes not held on this device" as the body
missing from HEAD too. The same case edits `rules/deploy.md` in the working tree and expects
`object_digest_mismatch` for it. An implementation reading HEAD, or a snapshot it kept, cannot
produce that expectation. The case already fixes the working tree as the repository home, so
removing the working file is the faithful statement, and it stands.

**C7, partly accepted.** The host's root is the whole repository. Importing `gates` or anything
under it is now refused inside the host, whatever path would find it. Reading files by absolute
path is not isolated: the driver judges this repository's own code, not an adversary. Revisit
at PK, when a candidate is judged from an installed package; the host should then run from the
package root.

## Controls

- **Positive.** Every scenario is run against the scripted owner with the runtime rules its
  registry row names (T8: the earlier tally applied none). 87 of 162 pass and 75 are blocked by
  name; none fails. The 10:10 figure of 90 is not comparable, because it applied no rules and
  counted the false passes above. V1: 21 of 22 pass; TUI-ENTRY-UNKNOWN waits on
  `event_reply_lost`.
- **Negative.** Every finding above has a test that fails on the defect it names. The reviewers'
  own probes were rerun against the fixed tree, and each false pass now fails or blocks by name.
  Four weak controls were tightened: the lost-commit control requires the difference at
  `/outputs/0/digest` (T4), the outside-edit control requires `failed` (T4), the context control
  requires the selection's digest (T5), and the judge-import control runs on a root holding a
  `gates` package (T9). The rule-block control now runs where the owner is found (T10).
- **Reverts.** Each rule of 3a, 3b and this round was reverted in a copy of the tree, one at a
  time, and every control guarding it was required to fail. There were 75 reverts in 85 pairs,
  and all were caught; the untouched copy passes. The first run of the new list found four
  survivors. Two were one fact checked twice, in the host and in the fault feature, so the host's
  check was removed. The layer test changed a value no one mints, and now changes one. The
  selection check's revert did not restore the old behaviour, and now does.
- **Tests.** `test_executor.py` runs 73 tests and `test_driver.py` 17; ruff is clean.

## What the 10:10 record stated that was not so

- "90 of the 162 pass": the tally applied no registry rules, and several of those passes were
  the false passes above.
- "14 scenarios, 22 paths" with two contents: the author's script shifted member indices after
  removing entries and invented three paths (W9, T7). The paths now blocked as conflicts are
  `tables/rates.csv` in four scenarios and `rules/review.md` in the N27-C01 pair, all bound at V3
  or later. SRC-10 still needs three checkouts, and SRC-11 two branches.
- "Against the code, all 22 are still blocked on `workenv.journal:layer_journal`": 21 are.
  TUI-ENTRY-UNKNOWN blocks earlier, on `event_reply_lost` (T12).
- `D-20260926-353f0e` says "14 of V1's 22" use a checkout; it is 13 (T11). The same row says
  "seven others" state `rules/review.md` as present; the 10:10 record already corrected that to
  nine. `D-20260926-421d82`'s "54" was a count of statement pairs. The ledger is append-only, so
  these corrections live here.
- "A restart that loses what was committed fails" held only for a fault a later step observes;
  with automatic resubmission it passed (W5). It holds for both now.

## Next

Unchanged: the plan successor for `workenv/roles.py`, then V1's slices. The slice that writes
the code committing a step must call `call.point("after_commit_before_return", answer)`.

Nothing here is pushed.
