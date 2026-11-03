---
created_at: 2026-11-03T16:33:00+09:00
head: 4018cef
kind: design
supersedes: null
---

# A Codex thread in several files is one session of segments, and Guardian reviews and workflow journals are not the owner's transcripts

Checkpoint C0 (run `c0-20261103`, outside the checkout) found three more ways the census misread the
owner's sessions. The owner took two decisions on 2026-11-03, and the third finding falls under the same
package's scope:

- **D-20261103-a7128a.** A Codex thread written across several rollout files under one id is one
  session of ordered segments. S1 reads every segment, and each segment has its own sha, record count,
  prefix and coverage. The window owns a segment's records by their timestamps, wherever they lie. S2
  copies each segment that owes the window something.
- **D-20261103-b1989d.** A Codex session whose `session_meta.source.subagent.other` is `guardian` is
  excluded, with reason `guardian`. This is Codex's automatic risk review of a session's actions, the
  same kind of automated session as `exec`.
- **Workflow journals.** Under a Claude session's `subagents/`, only `agent-*.jsonl` files are subagent
  transcripts. A workflow's `journal.jsonl` records the workflow's steps, not a conversation.

The findings below were measured on run `c0-20261103`'s census and on the files' first records. Only
record types, ids and counts were read.

- **Split threads.** The census met 31 Codex identities in more than one rollout file: 105 files with
  distinct names and no same-name copy among them. (32 rows had more than one file. The 32nd is a
  Claude row of 2 files, so 107 files in all.) The census kept the first file in (source, path) order
  and listed the others in `alt_paths`, which nothing reads, so a thread's later records were never
  seen.
  - **Later segments.** All 74 later segments start with `session_meta` followed by
    `event_msg/thread_settings_applied`: the host applies the thread's settings again when it opens the
    new file. 70 of them carry `history_base` in their `session_meta`.
  - **First segments.** 29 of the 31 continue with `event_msg/task_started`. The other 2 also start with
    `thread_settings_applied` and carry `history_base`. Their earlier files are not on this computer.
  - **Totals.** 72 of the 105 files carry `history_base`, and 69 contain a `compacted` record. 27
    later-segment `history_base` values name the thread itself. Of the 45 that name another thread,
    44 name one that is not on this computer.
- **Guardian reviews.** The 449 Codex child transcripts written in the window are 272 Guardian reviews
  and 177 `thread_spawn` subagents. The Guardian reviews were classified as children and would have been
  read as part of the sessions they review.
- **Journals.** 4 workflow `journal.jsonl` files under `subagents/workflows/` were read as subagent
  transcripts.

The design (`2026-10-20T1942--9684f05--mechanism-design.md`) and the plan
(`2026-10-20T2119--cc0498f--implementation-plan.md`) stay as written. So does this package's first record
(`2026-11-03T1250--4070468--a-run-reads-the-census-prefix-and-the-unit-is-a-root-with-every-descendant.md`).
Read their sentences below through this record.

## What changes

1. **Design §5.3, "Identity is (host, full session id)."** The sentence stands. A session may now be
   written in several files.
   - **Census row.** A Codex session's row holds its files in `segments`, in file-name order, which is
     the order the host wrote them in. Each segment carries `stem`, `source`, `path`, `sha256`,
     `versions`, `owned` and `work`.
   - **Coverage key.** The coverage state names each Codex file `codex:<id>@<stem>`, where `stem` is the
     file name without `.jsonl` and `.zst`. This holds for a thread of one file too, so when a thread is
     reopened into a new file, the keys its earlier files already have do not change. A Claude
     transcript's key stays `claude:<id>`.
   - **Session identity.** A result's `transcript`, lineage and the counting rule still use the session
     identity `codex:<id>`.
2. **Design §5.3, "Resume is not a lineage edge … each continues the same file under the same id
   (probe 8)."** The sentence was true of the CLI. It is not true of Codex Desktop, which continues a
   thread in a new file under the same id. The new file's `session_meta` carries `history_base`, and
   the file opens with `thread_settings_applied`.
   - **Edges.** Resume is still not an edge. A thread's kind and pointer come from its first file. A
     later file's `history_base` names where the thread continues from, which is no edge to another
     session.
   - **Evidence.** The lineage evidence of the later files is added to the thread's: record ids, turns,
     and whether any file was compacted. So a compaction in any file keeps the thread's lineage pending.
3. **Design §5.2, the coverage state and S3's result.** The unit of the first record is the files of
   the root and the files of its read members.
   - **Readings.** A reading names the file it read by its coverage key. Only a session of one file under
     its own identity may leave the name out, and a reading that leaves it out of a session of several
     files is refused.
   - **Completion.** A `read_complete` result that leaves any file's window unprocessed is refused, naming
     the file.
   - **Pending events.** A pending event names its file the same way. By default it names the session's
     last file.
4. **Design §5.1, eligibility.** A thread is eligible when any of its files has records in the window,
   and the window owns each file's records by their own timestamps.
   - **`window_overlap`.** The row's `window_overlap` combines all of its files.
   - **Unreadable files.** A file that cannot be read makes the session `unreadable`, naming the file.
   - **What a segment holds.** A segment carries only what a reader uses. It has no `window_overlap`
     or first timestamp of its own: the row's overlap covers all files, and a thread's first file is
     the first in name order. The host names a rollout file `rollout-<start time>-<id>`, with the time
     it opened the file, so name order is the order the files were written in.
   - **`no_timestamps`.** A session whose files together carry no timestamp is `unknown_provenance`
     (`no_timestamps`).
   - **Vanished files.** The coverage state can owe work on a file that is no longer here while the
     session's other files remain. The session is then `unreadable` with reason `SEGMENT_ABSENT <key>`,
     and the file is listed with no path. Its work stays owed in the backlog. The real data has no such
     case yet, because no production run has filled a Codex coverage state, so only a control holds this
     rule.
   - **Copies.** A file found again under its own name is a copy, not a segment, and stays in
     `alt_paths`. This covers a compressed copy in `archived_sessions` too.
5. **Design §5.3, provenance.** A Codex session is `indexed` when the threads index names any of its
   files, or a copy of one in `alt_paths`. Before, only the first file was compared, so an index naming
   the newest file, or the archived copy, made the session `not_indexed`. Run 1 had 29 `not_indexed`
   Codex sessions. Rerun C0b will measure how many of them each half of this change resolves.
6. **Design §5.1, children, and the plan's WP-07 inventory.**
   - **Guardian reviews.** A Guardian review is `excluded` (`guardian`) and is no member of any unit.
   - **Journals.** A `journal.jsonl`, or any other file under `subagents/` that is not `agent-*.jsonl`, is
     no child. It is counted with the files the census does not read (`unrecognized`).
   - **Inventory.** The inventory reads each file under its own binding: its own complete-line prefix,
     its own lines and its own timeline. Its row for a Codex file is referred to by `<id>@<stem>`, which
     is the `session_ref` of its record, its events and its timeline. The row's `id` stays the session's,
     and the file's own `session_meta` is judged against it. A pin is the session's, so every file of a
     thread answers under the thread's one pin. A child's `parent_ref` names its parent's first file.
     Per-file timelines match the data, because each new file opens with `thread_settings_applied`, where
     the host applies the thread's settings again.

## How the shape is held

- **Shape rule.** A Codex row carries none of `path`, `sha256`, `versions`, `owned` or `work` on the row,
  only in `segments`. A Claude row carries them on the row and has no `segments`.
- **Why no row-level copy.** A row-level copy of one file's fields would be read as the session's by any
  reader that forgot the other files. That is the defect this package removes. With no such field there
  is nothing to misread: a reader that indexes one gets a `KeyError` on the first Codex row.
- **Why not scan for readers instead.** The alternative was to keep row-level fields pointing at the last
  file and scan for readers of them. It was not taken. Outside `census.py`, 57 functions read those five
  names in 68 (function, field) pairs, and most of them read instruction files or dispatch records, not
  census rows. A name scan cannot tell those apart, so its exception list would have been some sixty
  entries, most saying "not a census row".
- **Shape checks.** The schema cannot state a shape that depends on the host: the repository's schema
  lint admits no conditional keyword (`validate.SUPPORTED_KEYWORDS`). So `census.account` checks each
  row's shape and names a departure as `SET_MISMATCH shape`. Every census check runs `account`.
  `census.rows`, the one way into a document's rows outside the census, refuses the same departures as
  `CENSUS_MALFORMED`.
- **Reader guard.** `census.reader_bypasses` is a structural control over `distill.py` and
  `runlib/*.py`.
  - Outside `census.py`, the census file may be named only at the sites `READER_EXCEPTIONS` lists, each
    with its reason.
  - A document taken from the census's loaders is never indexed for its `transcripts`; its rows are read
    through `census.rows`.
  - A listed site that no longer names the file is a stale exception, and fails like any other.
- **Readers.** Every reader of a row's files reads them through `census.segments_of`: views, the
  inventory, reconcile and `distill.py census --reconcile`. `gate.py` reads no census row.

## Not changed

- The status vocabulary of §5.1, and `child_of` for members.
- Claude rows, Claude coverage keys, and the session identity a result names.
- The first record's version rule and unit rule. Each now applies per file.
