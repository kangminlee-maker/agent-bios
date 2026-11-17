---
created_at: 2026-11-04T07:35:00+09:00
head: fc999c9
kind: review
supersedes: null
---

# A carried event is the unit's, a late occasion its own window's, and a store line ends only at a newline

Review W round 1 (on `487dd16`) returned rework. Commit A (`fc999c9`) closed the two `stop.py` findings. This is commit
B, the other four majors and two minors. Each section states the finding, what changed, and the control. Every control
was shown to fail by name with its fix alone put back (pretrial `wB-pretrial`, below).

## stage_read.py:1075 (major): a carried event on a file with no new work never reached the stitch

**The finding.**
- S2 made a view only of a file that owes the window something.
- S3 picked carried events only from the unit's views.
- So an event pending on an unchanged parent or an old segment was never stitched, though its outcome was in another
  member.

**The change.**
- S2 also views every file of an eligible unit (root or member) that holds an event an earlier run left pending, even
  when it owes the window nothing. The view has a copy and a projection, and no window. It is marked `carried_only`.
- S3 picks carried events from every file of the unit, as S2 chooses them. A carried-only file reads as windowless with
  its own reason.
- A carried event whose file has no view in the run is named in the stitch record: "its file has no view in this run".
  It stays pending and costs no call.

**The controls.**
- `W r1: an event pending on a file the run owes nothing is shown from that file's view, joined to the outcome another
  member holds, resolved, and no longer pending once folded`. It runs two runs:
  - Run N leaves the event pending on the parent.
  - Run N+1 sees the parent unchanged and a new record in the child that holds the outcome.
- `W r1: an event pending on a file of the unit with no view in the run is named not stitched, with no call`. It drives
  `Reader.stitch` with the event's file absent from the views.

**Not decided by a control.** Picking from every file of the unit, rather than from the unit's views, matters only for
a member file S2 cannot view. Since S2 views every file that has a path and holds an event, that is a member with no
path. The golden runs have no such member, so reverting that selection alone fails no control. The stitch's naming of
such an event is held by the second control.

## stage_read.py:390 (major): an occasion on a backlog record counted in the current window

**The finding.**
- `answer_problems` accepts an occasion on an owned `backlog(w1)` record.
- `keep` dropped its window role, and `follow_up` counted it toward window w2's resolution.
- Design §5.2: backlog ranges are "read as late evidence of the window they belong to and are tagged with it".

**The change.**
- `keep` records, for this run only, the window role of the record an occasion lies on, and whether an expansion read
  it.
- `follow_up` keeps a `backlog(w)` instance apart:
  - It writes it to `observations/<w>.jsonl` with basis `incomplete`, since this run cannot say window w's scope is
    complete.
  - It names the file under `late` in `resolutions.json`, with its line digests.
  - The instance derives no resolution of the current window.
- `stored_resolutions` checks the late digests too.
- This is D-20261104-6e324e. The basis was the default put to the lead.

**The controls.**
- `W r1: an occasion on a record the window owns is this window's`, paired with `W r1: an occasion on a backlog record
  is late evidence of its own window, kept apart with basis incomplete, and derives nothing of this one`. The two are
  one instance whose role alone differs.
- `W r1: an occasion on a backlog record is stored as late evidence of its window and not as this window's` runs it
  through the whole stage, on the Codex session's backlog record.

## stage_read.py:781 (major): a window and its expansion judging one occasion stopped the stage

**The finding.**
- An unsplit clipped entry and its unsplit expansion share an entry id.
- Both answers may report an occasion there, and each is valid alone.
- `follow_up` then failed RESOLUTION_INPUT ("occasions repeat") after it had written the instances. A resume repeated
  the same failure.

**The change.** `settle_occasions` leaves one instance per occasion of an expected observation, for each file:
- The same judgement (verdict and exposure) is kept once, with the evidence of both.
- A different judgement is the expansion's, since it read the entry whole. The window's is named `superseded` in the
  file's read record.
- Expansions that judge it otherwise among themselves keep none of it. It is named `conflicting`, and the unit is
  `read_partial`.
- `follow_up` now checks every row and derives every resolution before it writes any file.
- This is D-20261104-d4dead. The supersede rule was the default put to the lead.

**The controls.** Two stage runs on `late_clip`, the clipped record whose expansion shows it whole under the same
entry. Each control also requires that both readings judged the occasion.
- `W r1: an occasion its window and its expansion judge the same is one instance`.
- `W r1: an occasion its window and its expansion judge otherwise is the expansion's instance, the window's named
  superseded`.
- `W r1: every resolution is derived before any instance is written: a follow-up that cannot derive one leaves no file`.

## views.py:1432 (major): the decision log was read by str.splitlines

**The finding.**
- `record_decision` writes JSON with `ensure_ascii=False`.
- Its read-back and `order_decisions` split lines with `str.splitlines`, which also breaks at U+0085, U+2028 and
  U+2029.
- A reason holding one of them is valid JSON, but its line was split into pieces that do not parse.

**The change.** The JSONL stores this package added are now read by the one splitter, `records.jsonl_read`:
- both decision-log reads;
- the observation instances in `stored_resolutions`;
- the golden host's packet blocks (`records.jsonl_lines`);
- the self-tests' thirteen reads of the claim, event, decision and instance stores.

Three older self-test reads of the redacted projection are outside this package and were left as they are.

**The controls.** For each of U+0085, U+2028 and U+2029:
- `W r1: a reason holding U+2028 is appended once, ordered, and read back whole`. It covers the first decision, the same
  decision again (not doubled), another decision, the order, and the order again unchanged.
- `W r1: two runs deciding the same with a reason holding U+2028 leave the same bytes`.
- `W r1: an instance holding U+2028 reads back as the line recorded`.

## stage_read.py:2481 (minor): the resume comparison left out the results and the read records

**The change.**
- The `stores` comparison used by the repeated-run and kill-and-resume controls now holds `read-results.json`,
  `read.json` and every `read/<unit>.json`.
- The only fields left out are the reuse and interruption metadata: `reused`, `not_reused`, `interrupted`.
- The kill-and-resume comparison maps the re-read window's call id and the digest of every stored line that names it.
  The read records list those digests.

**The control.** `W r1: the resume comparison holds the results too: a resumed run whose processed range differs fails
it`.

## records.py:632 (minor): a reason claimed a lock the dispatcher does not take

`declaration_state`'s reason in DECLARATION_READERS now says what is true:
- It takes no lock itself.
- `run_stage` and dispatch's stop stamp call it under the declaration lock.
- The dispatcher's other reads hold the supervisor's lock alone, and a read landing mid-amendment is refused by name
  (DECLARATION_DRIFT).

## Evidence

The pretrial `wB-pretrial` (development tool, not committed) ran in disposable committed copies, in a fake env, with
TMPDIR under `/tmp`. There were 11 rows, and each fails its control by name with one rule put back:
- the decision log's two reads, and the instances' read, by splitlines;
- S2 not viewing a carried-only file;
- the stitch assuming every carried file has a view;
- a backlog occasion read as in-window;
- the late evidence not kept apart;
- the occasions not settled;
- the window's judgement kept over the expansion's;
- the instances written before the resolutions are derived;
- the results left out of the resume comparison.

The unmutated views (569 controls), stage_read (145), records, census, coverage and distill suites pass. Every TMPDIR
ended empty.
