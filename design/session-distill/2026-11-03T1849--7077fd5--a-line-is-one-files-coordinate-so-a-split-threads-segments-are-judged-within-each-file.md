---
created_at: 2026-11-03T18:49:00+09:00
head: 7077fd5
kind: design
supersedes: null
---

# A line is one file's coordinate, so a split thread's segments and intervals are judged within each file

## What the second checkpoint run found

The second C0 run (`c0-20261103b`, on 7077fd5) passed S1 census and S2 views and stopped in S2 inventory at its
cross-record validation: 77 problems, all on the 31 Codex threads the census wrote in several files (105 files).

| Code | Count | What it was |
|---|---|---|
| `CROSS_INTERVAL_OVERLAP` | 74 | a native interval overlapping the next in its lane, the next always another file of the thread |
| `CROSS_SEGMENT_DUPLICATE` | 1 (31 ids) | a segment id naming segments of 2 to 12 files, all starting at line 1 |
| `CROSS_SEGMENT_UNLISTED` | 31 | the same ids, listed by several session records |
| `RELEASE_EVENT_NOT_IN_FORCE` | 74 | release rows whose segment, looked up by its duplicated id, resolved to another file's segment |

D-20261103-a7128a made the inventory's row the file: every file of a split thread has its own binding, its own
session reference (`session_ref(host, "<id>@<stem>")`) and its own line numbers. The owner stayed the thread's
(`owner_ref(host, id)`, step 0 S-4), as it should. But a segment id was made from the owner and the segment's
first line, and the interval check grouped events by owner and kind. Two files of one thread therefore gave one id
to two segments, and put intervals in two files' coordinates into one lane.

Why the self-test missed it: the a7128a inventory control checked each file's references and timeline as
`transcript_events` returns them. No fixture took a split thread through the run's cross-record checks of
`sessions.json` and the release index, which are where segment ids and interval lanes are judged.

## What every file records

A structural probe over the same census, through the same readers (line numbers and counts only): each of the 105
files was read under its census binding, and each records exactly one native event, at its line 1 (31 first files,
74 later files). Each later file opens with the thread's own `session_meta`, written by the process that reopened
the thread. A Codex row's `session_injection` is never sought (`id_space`: Codex session ids and pins are different
id spaces), so native is the only kind recorded in these files.

## Decision (lead, 2026-11-03; D-20261103-536a52)

The owner stays the thread's. A position is a file and a line, the file being the session reference every event and
segment already carries. So:

- a segment id is made from the file, the owner and the first line (`segments`);
- the intervals of one owner and kind are judged within one file (`sessions_cross_problems`);
- no interval carries into the next file. Lines of a later file before its own event are `no_event_yet`.

The run discloses how many later files this decides anything for: `split_threads` in the transcripts notes
(`manifest.json` `inputs.transcripts`, and `current.json` `produced_by.notes.transcripts`), with `threads`,
`later_files`, `later_files_unread` and `later_files_without_native_at_line_1`. The last is the number of read
later files whose line 1 records no native event, which is where this choice and carrying would answer differently.
Nothing in the schema changes: `notes` is the producers' own shape.

## The alternative it closed

Carrying an interval into the next file, with positions of the form (file order, line) and one lane per thread. It
was closed for three reasons:

1. On the real data it gives the same answer on every line: every file's lines are governed by that file's line-1
   event either way (105 of 105).
2. Its scope is several times larger. An event's interval end and certainty cut would need the file order (new
   fields in `sessions.json`), a new rule would have to say where certainty ends across a middle file that could not
   be read, and `CROSS_SEGMENT_EVENT` would have to admit a segment naming another file's event.
3. It would claim a body is in force that the file never recorded: each later file is a new process writing its own
   `session_meta`.

## When to look again

- Codex `session_injection` becomes sought. An injection the first file records and a later file does not would then
  show `no_event_yet` in the later file. If the reopened thread replays the earlier injection as history, that answer
  is short of the truth. Carrying was not closed for this case: it was never observable here.
- The S0 native-capture package, or any run, reports `later_files_without_native_at_line_1` above zero.

Either way, carrying would be re-examined against what the later files record then. Until then, the counts say
whether the question has arisen.
