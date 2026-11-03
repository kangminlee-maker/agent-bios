---
created_at: 2026-11-03T19:19:00+09:00
head: c3e16ad
kind: review
supersedes: null
---

# An event's id is made with its file, and an instant is placed in one file

The first Codex review of wp/c0-fixes-2 (commit c3e16ad) returned `fix_then_accept`. It confirmed that the four
problems the second checkpoint run stopped on are gone in every case it was asked about: three files, a native event
at line 2, no native event, an unreadable or unbound later file, and files found in reverse order. It found two
places where the file was still missing from the decision recorded in
`2026-11-03T1849--7077fd5--a-line-is-one-files-coordinate-so-a-split-threads-segments-are-judged-within-each-file.md`.
Both were reproduced on fixtures before they were fixed (`work/impl/c0fix2/r1/repro.py`, outside the checkout).

1. **Major: an event id was made without its file.** It hashed the kind, the host, the thread id, the binding and
   the line. Two files of one thread that hold the same bytes have the same binding, so their events shared an id.
   Three files under distinct stems with identical bytes gave three events one id, and the run stopped on
   `CROSS_EVENT_DUPLICATE`, `CROSS_EVENT_UNLISTED`, `CROSS_EVENT_ASTRAY` and `CROSS_SEGMENT_EVENT`. The id is now
   made from the file reference (`ref_of`) in place of the thread id. A Claude row's reference is its session id,
   so a Claude event's id is unchanged; a Codex file's is `<id>@<stem>`.
2. **Minor: an instant was placed across files.** `event_at_instant`, which places an instant without a line and
   is called only by the self-test, filtered by owner and kind. Given two files' events, it answered an instant
   before the later file's first event with the earlier file's event, while that file's segment says
   `no_event_yet`. It now requires the file reference, refuses a call without one, and filters by it.

Each fix has its own control, and each control was shown to fail when its fix alone is reverted.
