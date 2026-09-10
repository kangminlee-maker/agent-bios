---
created_at: 2026-09-09T07:37:28+09:00
head: c6fcf8e84580e72c3f707f2ad941fa03b0732799
kind: review
supersedes: none
---

# Branch integration evidence

This is the pre-commit evidence record for the merge containing this file, not a
live branch-status page. Re-derive current state with `git status --short --branch`,
`git log --graph --oneline --all`, and `git worktree list --porcelain`.

## Pinned inputs and organization

- Published baseline: `841a5ba6b6aa7cfe2718a56c53488cced67290dc`.
- Selectively reapplied tier work: source `99ee46a95799b14e2c15896454b7c6b0697b269c`;
  integration parent `c6fcf8e84580e72c3f707f2ad941fa03b0732799`.
- Incoming experiment: `e204ebe013d382aa9de7e213fce76edf1bd084bd`, merged with its
  original ancestry rather than squashed. Its common base with the published
  baseline is `ed5b00f20381fd70e7a4f9bc3dd5c8c83216158a`.
- Reviewed merge candidate before adding this record: tree
  `989afb721d879b4867af5c382780b2c8a97e43d7`.

The census found twenty remote working branches already contained in the published
baseline. `spurious-captain` was not an ancestor, but its tip's entire tree equals
the already-contained squash `52d2a9563419bffa0d59fdfe29741976be9aaa11`. It requires
no re-merge. All four original worktrees were clean and no open GitHub PR used a
branch. These were point-in-time checks; cleanup rechecks exact remote tips.

The selected tier patch fixes the HELM wrapper's stale emitted seats and adds
owner-derived output checks. It also carries the separately approved REVIEWER
`gpt-5.6-terra` / xhigh template. Approval was checked in the actual Claude session
`cbc55eb2-4a34-4555-9a70-eae968dd77e3`: user message
`bd834b1c-e403-4816-8688-e871d25c568d`, at `2026-09-08T20:22:58.462Z`, immediately
follows the reviewer-upgrade proposal. This corrects the earlier audit's assumption
that the branch's reviewer change lacked user authorization. The four-tier table
alone did not establish it; the transcript did.

All six source-branch decision rows were preserved as history with their original
IDs and timestamps. They do not overwrite the current profile. Integration choice:
`D-20260909-73d7f5`.

## Preservation checks

- All 50 tracked baseline files selected under `compose/`, `launch/`, `learn/`,
  the installer, package manifest and four global instruction files remain
  byte-identical to `841a5ba`.
- The six incoming instrument modules `budget`, `cards`, `live`, `registry`,
  `stage` and `trigger` remain byte-identical to `e204ebe`.
- The measured rule sections in both canonical workflow guides are exact copies
  of the incoming sections. Current tier bindings remain alongside them; generated
  Codex mirrors were checked rather than hand-merged.
- The ledger is the exact ID/content union of both merge parents: 244 rows, no
  same-ID/different-content conflicts. Only Git conflict markers were removed.
- The implementation map has one current tier table. Its single SVG is unchanged
  and parses; obsolete workhorse and unmerged/unbuilt spawn-status claims were removed.

## Verification performed before the merge commit

The tier parent passed the complete pre-commit package/parity gate, including 123
corpus tests, tier-effort paths and the wrapper assertions. The merged candidate
then passed:

| Check | Result |
| --- | --- |
| Budget self-test | 72 passed, 0 failed |
| Registry self-test | 100 passed, 0 failed |
| Cards self-test | 189 passed, 0 failed |
| Trigger self-test | 223 passed, 0 failed |
| Full tier self-test | 341 passed across 11 slices, 0 failed |
| Generated mirrors | 39 match, no rewrite needed |
| Review routing golden | 126 cells match, 0 control failures |
| Decision records, lexicon and ontology | Passed |
| Original experiment replay | Discovery and confirmation output byte-identical before/after merge |

Self-tests exercise synthetic and failure-path fixtures; they are not new model
trials. The separate replay uses the original recorded experiment: four discovery
cells select T-E@5, and both confirmation claims retain parity and CONFIRMED over
five paired blocks each. No new model request was made for that experiment. All
3,838 source files still matched the pre-replay archive afterward.

A fresh Astra/max review of the tier patch found an existence-only assertion that
accepted a correct role declaration together with a stale one. The patch now rejects
contradictory structured bindings; ten real-output controls cover five replacements
and five additive contradictions. Astra independently reproduced rejection of its
original example and sibling cases on tree
`76bb8e6c0f58f028e76f40ed3c16914200e9cf9a`, which is the tier parent's tree.
The resulting scope had no medium-or-higher behavioral findings. This is not a
general prose classifier or proof of native model behavior.

The complete merged staged tree still goes through the normal commit hook. Its
successful commit, not this pre-commit record, is the evidence that gate completed.
Further merge review and remote cleanup are likewise established by their execution
receipts, not claimed completed by this record.

## Boundaries and recovery

Python 3.13.7 exposed a pre-existing `Path.is_file()` permission exception in
`learn/collect-learning.py`; the unchanged file passes all 54 controls on the
already-verified Python 3.14.5. The issue is retained as F-18. All integration
commit gates pin Python 3.14.5; none are skipped. Claude authentication is unavailable
even outside the sandbox, so cross-provider independence is not claimed.
No package release or live installation is part of this integration.

Before any branch removal, the original refs and external experiment evidence were
backed up under the primary checkout's `.git/integration-backups/2026-09-09.QF7oAS/`:

- `refs-before.bundle`: complete history, verified with `git bundle verify`;
  SHA-256 `290496235da4633c67f04dd01da928cc586650c102a28a5e2097a9fe5d73b6cf`.
- `spawn-evidence.tar.gz`: original trigger root and the scratchpad launch script;
  SHA-256 `4acbcf64e2645f94f274ce623d8dc85cb28c18bca701aba5084c8274d7b2025c`.
  All 3,838 source files match their archived bytes; additional AppleDouble entries
  are filesystem metadata, not missing source files.

`git bundle list-heads <bundle>` lists the original names and tips for targeted
recovery. A selectively integrated branch tip must retain a durable ref before its
working branch is removed. Tool-owned refs, native configuration, live experiment
roots and unrelated ignored data are outside cleanup scope.
