---
created_at: 2026-11-16T09:44:00+09:00
head: b6770be          # the commit the content was true at; the change it describes is the next commit
kind: design
supersedes: none (it closes the scope 2026-11-15T2125--7a7752e--release-1-can-change-a-library-file-and-rr-1-changed-none.md describes, which stays as written)
---

# Release 1 changes no library file

The owner decided on 2026-11-16 that release 1 changes no library file, and that the write path's redesign
follows the npm publish (D-20261116-7853bc). It reverses D-20261115-9311c2, which kept the library-changing
dispositions open in release 1.

## Why

Codex's fourth review of the write path (S7 to S12), pinned at 2b901850 and granted with a design review
(D-20261116-7f1aab), returned rework: eight of round 3's nine answers met, and seven new major findings. Its
design review grouped the write path's sixteen reviews into five structural causes. The two that matter most here:
each stage reads what an operation changes for itself (D1), and the owner's decisions, keep releases and ledger
transitions do not travel as one transaction, so a confirmed merge could change files before S12 found the ledger
entry it needs missing (D2). The remedy the review names - one version-bound plan built before approval and read by
every later stage - is a redesign across S7 to S12. Release 1 cannot measure whether a library change helps (S8 is
deferred), and RR-1 applied none, so the risk is removed from release 1 and the redesign waits for the publish.

## What is closed, and where

One owner, `session-distill/runlib/placement.py`:

- `library_changing()` - §7.2's disposition vocabulary less the ledger-only set and `none`: today `place`,
  `correct`, `re-deliver`, `reduce`. It is derived, so a disposition added to the vocabulary is refused in release 1
  until someone decides otherwise.
- `release_problems(disposition, operations)` - `RELEASE_1_NO_LIBRARY_CHANGE` for such a disposition, and for any
  operation under any disposition.
- `release_packet_text(role)` - the section S7's and S7b's packets carry (`{{release}}`), naming the refused
  dispositions, the code and what is accepted, and asking that a change the evidence supports be named in the Korean
  reason instead.

It is applied at four points, so nothing approved can reach a write:

| Stage | Where | What it refuses |
| --- | --- | --- |
| S7 | `stage_propose.answer_problems` | every accepting path: answers in hand, the live check, a Korean regeneration |
| S7b | `stage_review_proposals.review_problems` | an alternative the owner could adopt with `수정` |
| S10b | `stage_confirm.final_set` | an approved item in F, before the owner confirms |
| S11 | `stage_apply.items_of` | a confirmed set holding a change, before the plan and before the effects |

Every row of the pairs table keeps a disposition release 1 accepts; placement's suite enumerates the combinations.
A keep release arises only from a `reduce` approval (`stage_render`), so the keep-record findings (C1 to C4) cannot
run either.

The owner's pages say what release 1 does: `owner_lines.RELEASE_1_APPROVAL_EFFECT` on S9's review and
`RELEASE_1_CONFIRM_EFFECT` on S10b's confirmation, in place of the design's sentences, which promise that applying
changes files. The guide's stage table and its "What a release 1 run produces" paragraph, in English and Korean, and
the driver's help for `apply` say the same.

## The scope switch, and why the closed path keeps its controls

`placement._SCOPE` is `release_1` as shipped. `placement.scoped(scope)` is its only writer; the suites of S7, S7b,
S9, S9b, S10, S10b, S11 and S12 run their bodies under `scoped("all")` - the contract as designed - and those of S7, S7b,
S9, S10b and S11 add release-1 controls inside it under `scoped("release_1")`. Placement's suite holds, by an AST walk of `runlib/*.py` and
`distill.py`, that no call of `scoped` stands outside a self-test function, and plants one to see it named.

The reason is the redesign: it starts from a write path whose controls still run, rather than from code that rotted
while closed. The cost is that the closed path's defects stay in the code; F-45 names them. A driver subprocess
cannot enter the scope `all`, so the driver's own suites run at `release_1`: S10b's process legs now assert the
refusal at the build and at `--decide`, and build and confirm a set that changes no file.

## What else this commit holds

- C8: sequencing's empty-suffix controls and the two section-merge controls before them compare the verdict typed
  and exactly (`same`), with a control that tells `False` from `"false"` and from `0`.
- F-45 in `FINDINGS.md`: the write path's findings, their reach in release 1 (none) and the two alternatives for the
  redesign.

## What is not claimed

- No real run has met the refusal. RR-1 proposed no change, so it would have passed unchanged.
- The closed path's correctness is not claimed by its green controls under `all`: round 4's C1 to C7 stand in it.
- A cross-family review of this narrowing is the owner's one confirmation round (option 1 of the decision request);
  its result is recorded separately.

## Revisit when

The redesign after the publish reopens the dispositions through one plan of every file effect and ledger
transition (F-45). Until then, a change to `library_changing()` or to any of the four call sites is a change to
release 1's contract and needs the owner's decision.
