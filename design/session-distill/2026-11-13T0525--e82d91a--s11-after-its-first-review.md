---
created_at: 2026-11-13T05:25:00+09:00
head: e82d91a
kind: review
supersedes: none (it amends the S11 part of 2026-11-13T0445--247e100--what-an-operation-does-and-where-release-1-s11-writes.md)
---

# S11 after its first review

The first cross-family review of S11 (pinned at `f21ba77`) returned **rework**: three blocking findings, eleven
major, one minor. This record says what each became. The review file is the lead's
(`work/lead/s11-x-r1-review.json`); nothing here restates a value the code owns.

## Blocking

1. **A plan on disk was trusted because it was there.** A re-run read `apply/plan.json`, checked its
   confirmation id and each effect's bytes against the plan's own hash, and applied it; a planted plan wrote an
   unapproved file. S11 now has two parts. The **plan** part writes `apply/plan.json` as its recorded output. The
   **effects** part names that file as an input, so the shared record check refuses a plan that is not the one
   recorded (`INPUT_INVALID`) before it is read, and then holds what the plan says to the confirmed set
   (`plan_problems`: item, approval, operation, a path that operation names, bytes, operation id, each file's
   chain). A plan is never written over a journal (`PLAN_AFTER_EFFECTS`).
2. **A metadata write confined its path and then opened it by name.** `records.write_text` and `stagelock.hold`
   resolved the destination, then called `mkdir`, `mkstemp` and `replace` on the pathname, so a directory swapped
   for a link in between took the write outside the run. Both now reach the leaf from the run directory's own
   descriptor, one component at a time, none through a link (`stagelock.beneath`). This is the shared writer, so
   every stage's records are covered, not only S11's.
3. **The target was checked before the new bytes were staged.** The temporary is now written and synced first;
   then the target is held to the plan's before-state through its descriptor, the temporary's name is held to the
   file that was written, and the rename is made; then the name is checked to hold that file. One interval cannot
   be closed on POSIX, which has no compare-and-rename: between the last check and the rename, a concurrent writer
   of the target is overwritten, and a swap of the temporary is installed and then reported
   (`APPLY_AFTER_MISMATCH`). The module says so, and it is why nothing else should write the checkout during S11.

## Major

- **An amendment could land while the effects ran.** The declaration is read again before every write and held
  to the one the part was admitted under (`DECLARATION_MOVED`). An amendment landing during a single write is
  seen before the next one, not during that one.
- **`path#heading` took a file out of its layer.** The file of a target has one owner, `targets.file_of`, which
  `drift.target_identity`, `drift.target_problems`, `sequencing` and `operations.split_target` ask. A section of
  the always-loaded file is in the global layer.
- **Headings and fences.** Read as CommonMark reads them: up to three spaces of indent, closing marks only after
  a space, a fence closed only by its own character at least as long with nothing after it, `\r\n` as a line end.
- **Merge.** Its content is placed as an edit's is, anchor included, and the unit that is the target is recognised
  by the section it names, not by how its heading is spelled.
- **A newline was added to a section's replacement.** Nothing is added to `content` now. A replacement that would
  run into the text after the section is refused (`SECTION_CONTENT_UNTERMINATED`), and S7's check of a call asks
  the operation contract before the answer is accepted (`OPERATION_WOULD_NOT_APPLY`), so the model's retry is told
  and the owner is not asked to approve an operation S11 would refuse. The contract moved to
  `runlib/operations.py` for that reason: S7 and S11 read one module.
- **Overlapping anchors** count as two occurrences.
- **A FIFO blocked the open.** Leaves are opened non-blocking in the target contract and in S11, and anything that
  is not a regular file is refused by name.
- **Case aliases.** Planned paths that spell one name differently are refused before any write
  (`APPLY_SPELLING_CONFLICT`), and each write checks every component it reached against its directory's own entry
  (`APPLY_SPELLING_ON_DISK`).
- **A corrupt journal was ignored on a finished re-run.** The journal is read whole before any decision and
  refused if it does not parse or holds a record the plan does not.
- **Sequencing modelled every delete as the file's.** An anchored or section delete leaves its file, and a
  section-qualified target shares its file's identity.
- **The proposal schema fails the strict-provider projection.** Not fixed here: it predates this work and does
  not reach a Claude seat. Queued as F-34 in `FINDINGS.md` with its two alternatives.

## Minor

- The journal's order control compared a comma-joined string by substring; it compares the list.

## What this does not claim

The controls for the staging interval and the directory swap replace a function inside the process to act at the
instant in question; no second process races the write. The case-alias control on disk asserts the refusal only
where the test's filesystem folds case.
