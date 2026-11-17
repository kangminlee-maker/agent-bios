---
created_at: 2026-11-03T12:50:00+09:00
head: 4070468
kind: design
supersedes: null
---

# A run reads the census's complete-line prefix, and the unit is a root with every descendant

Checkpoint C0 ran S0–S2 on the owner's sessions of 2026-11-01 and 2026-11-02 (run `c0-20261103`, outside
the checkout). Two of its findings changed what S1 and S2 do, and the owner took both decisions on
2026-11-03:

- **D-20261103-8facee.** Inside a run, a transcript's version is the census's complete-line prefix. S2
  copies the first `record_count` complete lines and accepts them when they hash to the census's sha. What
  the host appends after the census is the next run's. A prefix that changed is `SOURCE_CHANGED`.
- **D-20261103-85f3e8.** The unit S1 judges and S2 reads is a root session with all its descendants. A
  root is eligible when it or any descendant at any depth has records in the window. S2 reads every depth.

The findings, measured on run `c0-20261103`'s census and file metadata:

- S2 stopped at its first item with `SOURCE_CHANGED`. Four sessions were still being written while the
  run read them: the lead's, two other Claude sessions and one Codex session. S2 compared a copy of the
  whole current file with the census's whole-file hash, so any line appended after S1 failed the copy. A
  development run cannot finish S2 while anyone works, and a production run would quarantine the session
  the operator runs it from every time.
- 449 Codex child transcripts written in the window, 0.89 GB, would never have reached S3. 356 lay under
  four roots S1 had judged `nothing_new` from the roots' own records alone. 93 lay two or more levels
  under an eligible root, and S2 read only children whose direct parent was eligible.

This record states which sentences of the design (`2026-10-20T1942--9684f05--mechanism-design.md`) and
the plan (`2026-10-20T2119--cc0498f--implementation-plan.md`) the two decisions change, and how. Both
records stay as written. Read their sentences below through this record.

## What changes

1. **Design §5.4, "Each transcript version is copied immutably into the run."** The version copied is the
   census's: the transcript's first `record_count` complete lines, which must hash to the census's sha.
   Lines the host appended after S1, and a line it was still writing, are not copied. A copy with fewer
   complete lines than S1 read, or other bytes in them, is refused as `SOURCE_CHANGED`, because the
   transcript was rewritten or truncated after the census.
2. **Plan WP-07, Goal, "immutable hash-named copies of every eligible transcript version", and the copy
   controls of its done-when 1** (`views.py`, "the copy is where tampering is caught"). S2 copies every
   transcript of an eligible unit that owes the window something: the root and members at any depth.
   "Owes the window something" means records the window owns, or a backlog. `SOURCE_CHANGED` now means
   the census's prefix changed, not that the host appended. A member that owes the window nothing is not
   copied: it would cut no window. An eligible root whose whole unit owes nothing contradicts S1 and is
   refused as `SET_MISMATCH S2`.
3. **Design §5.2, `versions {sha, record_count, prefix_sha}`.** The sentence stands. What `sha` hashes is
   now defined: the complete lines. Before, the code hashed everything read, including a line the host was
   still writing. `sha` and `prefix_sha` are equal for the version S1 reads. `prefix_sha` stays the anchor
   of the append-only test against the next run.
4. **Design §5.2, "A session is fully covered for window w when its processed ranges for w cover every
   record of its latest version that w owns."** It is the unit that is fully covered. The root's processed
   ranges, and each read member's, cover every record of their latest versions that w owns. One S3 result
   answers the unit. A reading that names a member credits that member. A reading naming a transcript
   outside the unit is refused. A `read_complete` or `nothing_new` result that leaves a member's window
   unprocessed is refused, naming the member. A carried result (`read_partial`, `failed`, `deferred`)
   keeps each member's unread ranges in the backlog under the member. A window is accounted when that
   holds for every member.
5. **Design §5.1, "Child transcripts … are linked to their parent session and read as part of the parent's
   evidence", and "eligible ends as … `nothing_new`".** Both sentences stand. The implementation now
   follows them at the unit:
   - The parent whose evidence a child is part of is the root its chain of parents reaches, at any depth.
   - Every member of an eligible root is read in full like the root.
   - A root is `nothing_new` only when neither it nor any member owes the window anything.
   - A member that cannot be read, or carries no timestamp, is named the way a root would be
     (`unreadable`, `unknown_provenance`). It keeps its parent, leaves the unit, and the unit is judged on
     the rest.
   - Parents that loop reach no root. Such a child is `unknown_provenance` (`orphan_child`).
6. **Design §4, failure posture, "items sharing its unit".** The unit is the root with every member. Under
   the production posture a failing member quarantines the root and every other member with it.
7. **Plan WP-05/WP-06 interfaces, `window_overlap ∈ {inside, straddles_start, straddles_end,
   context_only}`.** `straddles_both` is added, for a transcript with records before the window's start
   and after its end. Such a transcript read as `straddles_start` before, so a session still running past
   the window looked as if it had ended in it.

The counting rule of §5.3 reads the unit too. A component is active in the window when any unit in it owns
a record of the window, so a root whose only activity in the window is a member's counts, through the
root, once.

## Not changed

- The status vocabulary of §5.1 and its contract check. Members keep `child_of`.
- Identity (`<host>:<id>`), coverage keys, and the shape of an S3 result. A reading
  only gains an optional `transcript`, the member it reads.
- The inventory reads whatever the census binds. It now compares the census's version hash with the
  complete lines it reads, so a line still being written leaves the binding intact.

## Not in this record

Split Codex threads, Guardian review sessions and Claude workflow journals are a separate commit with its
own record. Those are D-20261103-a7128a and D-20261103-b1989d, plus the journal finding of the same
checkpoint.
