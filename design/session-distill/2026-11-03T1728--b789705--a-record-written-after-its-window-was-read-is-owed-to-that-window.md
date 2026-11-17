---
created_at: 2026-11-03T17:28:00+09:00
head: b789705
kind: review
supersedes: null
---

# A record written after its window was read is owed to that window, and a unit follows parent links, not statuses

The first Codex review of the wp/c0-fixes package (commits 4018cef and b789705) returned
`fix_then_accept` with five major findings. Each one was reproduced before it was fixed. The probes ran on
fixtures only (`work/impl/c0fix/r1/repro.py`, outside the checkout). All five reproduced on b789705, and
none reproduced after the fixes.

## 1. Records appended after their window was run were owned by no run

D-20261103-8facee gives the records a host appends after a census to the next run. But the next run reads
another window, and a record is owed only to the window its timestamp is in. So a record stamped inside a
window that had already been run was owed to nobody. This happens in two ways: a line the host was still
writing at that window's census and completed later, or a complete line written late.

- **Reproduced.** Window 1 (10-01 to 10-08) ran with a line dated 10-07 still being written. After the
  line was completed, the census of window 2 moved `record_count` from 10 to 11 and still judged the
  session `nothing_new`, with no work and no backlog. `processed[w1]` stayed `[0, 10)`.
- **Fix.** When the census sees an append (the prefix holds and the count grows), it checks the timestamps
  of the appended records against every window the state has already run, other than the current one.
  It reads those windows back from their ids with `coverage.bounds_of`. A record of such a window goes
  into the run's backlog under that window, with the new backlog status `appended`
  (`coverage.carry_appended`). The next run then reads it and processes it under its own window, the
  way it reads a carried backlog. Two kinds of record are not owed again: records the window already
  processed, and records the backlog already holds. A record without a timestamp takes its
  predecessor's, as in `coverage.Ownership`.
- **Targeted runs.** A targeted run returns the periodic base, so the backlog it adds lives only in the
  census's work. `coverage.observed` now lays that backlog over the base as well as the versions. A
  targeted reconcile can then credit those records, and periodic coverage stays byte-identical.
- **Decision.** D-20261103-71a195 (lead, 2026-11-03) took the status `appended` and the counted field
  below.
- **Schema.** The backlog entry's `status` enum gains `appended`. The other three statuses name the S3
  result that left records unread. No result left these records, because they had not been written when
  their window was read.
- **How the windows are judged.** One pass judges every record against all the windows already run
  (`coverage.Owners`), by the same rule as `coverage.Ownership`. A timestamp is parsed once. The windows
  are searched by their start, and the search goes back only while an earlier window still reaches past
  the record. So windows that do not overlap cost a comparison or two per record. With no window run
  before, nothing extra is done.
- **Not handled, but counted.** Two other ways a record can be owned by no run are not handled.
  - A version rewritten since its window was run. Between runs, S1 starts the new version
    (`coverage.observe` returns `rewritten`). S2 compares only with the version the census read, so
    nothing stops with `SOURCE_CHANGED`, which is raised only for bytes that change between S1 and S2.
    The earlier windows processed the old version's bytes. Which records of the new version they still
    owe is a question about rewrites, not about appends.
    A backlog entry left on the old version stays owed under that version, and no later run can clear
    it. The session is eligible in every run, because its work still lists the entry. But S2 copies only
    the newest version and views only that version's backlog (`views.view_transcript`), so S3 never sees
    the old bytes. A result that reports `read_complete` is refused by name (`RESULT_INCONSISTENT ...
    earlier-window ranges are still unprocessed`). A carried result keeps the entry, so the window is
    accounted but never fully read. This was probed on these bytes and is left as it is.
  - A file never read before whose records are stamped in a window already run (moved in, restored or
    synced late). There is no earlier version to be owed through.

  They must not vanish silently, so the census document carries a new required field, `unowned`:
  `earlier_windows` (how many windows already run it judged against) and, for `rewritten` and
  `first_seen`, the number of files and of records that such a window owns. The census summary prints it
  as one line. `earlier_windows` tells "nothing to judge" apart from "judged, and none". A first run
  against an empty coverage state judges no window, so it reports 0 by construction.
  **Revisit** when a C0b or a real run reports `rewritten` or `first_seen` above zero.
- **Controls.** Census: a two-window run covering both a completed partial line and a late complete
  line, a line of the current window that stays in the current window, processing under the original
  window, a targeted run, and `read_full` taking only the appended records. The same run counts one
  rewritten session (10 records) and one session never read before (8 records), and the first run
  reports `earlier_windows` 0 with no records. Coverage: `Owners` over windows that overlap, with a
  record that has no timestamp and one whose timestamp does not parse; `bounds_of`; `carry_appended`
  (it does not add again what the backlog holds or what the window processed); and `observed`.

## 2. A member whose read failed cut its descendants off from the root's unit

`root_of` walked the parent chain only through rows whose status was `child_of`. A member whose full
read failed became `unreadable` but kept its parent, so the walk stopped there. The rows below it then
formed a unit of their own with no eligible root.

- **Reproduced.** In a chain root → mid → deep where only mid's full read fails, the census read deep and
  gave it seven owned records. `units()` then returned `mid → [deep]`. Reconcile reported `accounted` and
  `fully_read` with deep unprocessed and absent from the backlog, and S2 did not read deep either.
- **Fix.** The chain is now the parent links, whatever the status. A failed member is still not a member
  (`units_of` lists only `child_of` rows), but the rows below it stay in the root's unit. A member whose
  head cannot be read names no parent, and its rows are judged under it, as before. That failure is
  named on the member's own row.
- **Controls.** Census: the chain above with a planted full-read failure (the descendant stays in the
  root's unit, is processed with the root, and a result that leaves it unprocessed is refused by name).
  Views: a unit whose middle member S1 could not read still has its member below read as the root's.

## 3. Targeted views took the record count from the wrong state

`views.census_version` paired the census's sha with the record count from the run's coverage state. For
a targeted run, that state is the periodic base, which never holds what the census observed.

- **Reproduced.** Over an empty base the version was refused (`VERSION_MISMATCH`). Over a base that had
  seen 8 records, the census's sha for 10 records was paired with a count of 8, and the copy was refused
  as `SOURCE_CHANGED`.
- **Fix.** Both the sha and the record count now come from the census: the version the file's work names,
  among the versions the census recorded for it.
- **Controls.** Views: a targeted run over an empty base and over a base that saw fewer records copies
  both files of a split thread with no quarantine.

## 4. Views made before their unit was quarantined stayed in the manifest

When one file of a unit failed, `records.run_items` moved the unit's finished files into the quarantine.
But `views.run` built the manifest from its own record of every view it had made.

- **Fix.** The manifest and its totals come from what the stage still reports done.
- **Controls.** Views: the existing case where a member fails after the root and another member have
  their views now also requires an empty manifest and zero totals.

## 5. A result could resolve another unit's pending event

`coverage._fold` checked unit membership for readings and for new pending events. But it removed
`resolved_events` by id alone.

- **Fix.** A result may resolve only events that are pending on a file of its own unit. A result that
  names any other event is refused before anything is removed (`RESULT_INCONSISTENT ... it resolves`).
  This includes an event pending on another unit and an id that is not pending at all.
- **Controls.** Coverage: resolving another unit's event is refused, resolving an id that is not pending
  is refused, and the unit that holds an event resolves it.

## Verification

The pretrial reverts each fix in a disposable copy and requires its suite to fail with every expected
label. Rows:

- the appended carry, and the cut to the appended records;
- the held and processed subtractions;
- the observed backlog (coverage and census);
- the count of records owned by no run: skipped, taken from appends too, and with the windows judged
  left unsaid;
- the window search stopping early;
- the parent-link walk (census and views);
- the census version, the manifest source, and the resolution check.

The unmutated suites must pass.
