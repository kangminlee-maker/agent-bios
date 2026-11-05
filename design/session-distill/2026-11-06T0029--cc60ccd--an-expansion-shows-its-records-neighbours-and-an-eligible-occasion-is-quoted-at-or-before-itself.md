---
created_at: 2026-11-06T00:29:00+09:00
head: cc60ccd
kind: design
supersedes: null
---

# An expansion shows its record's neighbours, and an eligible occasion is quoted at or before itself

WP-08c, commit B (items 3, 4 and 5 of the package). It amends §5.4 of the mechanism design
(`2026-10-20T1942--9684f05--mechanism-design.md`) on what an expansion shows, and §11 on what counts as an instance.
The owner moved both observation-path gaps into this package (D-20261105-43f93d). Before this commit they were to be
fixed before WP-21 at the latest (D-20261105-eabb9b).

## 0. A correction to commit A

Commit A's record (`2026-11-05T2202--01ab16a--...`) and its report said pretrial `pt8c-a` ran 11 rows, 9 of them
bending. It ran 10 rows: 2 `none` rows and 8 bending rows. Two rows of the approved design were left out. They ran
afterwards on a copy of `cc60ccd` (`pt8c-a2`):

| Row | What it bends | Result on `cc60ccd` |
| --- | --- | --- |
| `later_unprocessed_admitted` | drops the condition that a quote after the event is one the run processes | caught by name (2 of 2 named controls) |
| `clip_error_lines_old_bounds` | the view check's `error_lines_of` back on the character bounds | missed |

**Why the second row was missed.** On text whose lines end in `\n`, the two bounds give the same error lines. The line
cut only moves a bound to the start or end of the line it falls in, and an error line is always a whole line. Over
20,000 random blocks with `\n` line ends, the bounds moved in 12,289 and the error lines differed in 0.

The view check splits lines the way Python's `str.splitlines` does. That also ends a line at `\r`, U+2028 or `\x0c`.
On such text the two bounds differ: with those line ends mixed in, the error lines differed in 1,323 of 20,000 blocks.
A tool's progress output uses `\r`. With the bounds reverted, the check would not look at an error line that ends on
`\r` between the line-aligned head end and the 1,200th character.

Commit B adds a control for it (§4, the "error lines between the clip's own bounds" row). The comparison script is a
work tool outside the repository.

## 1. An expansion shows its record's neighbours (§5.4, Views and expansion)

**Before.** An expansion window held the omitted middle alone, cut with no overlap. A reading of it saw no record
before or after the clipped record. So an exposure shown just before the clipped record was not shown to the
expansion. In DW5 the test run's only occasion lies in its omitted middle, so the occasion was judged
`exposure_unknown` and T-1 stayed pending. Recorded as a gap in `2026-11-05T2017--4f34ae3--...` and
`2026-11-05T2047--e54cfe8--...`.

**Now.** `views.expansion_windows` cuts the middle as S2 cuts a view:
- **The sequence.** `views.expansion_entries` rebuilds the view's sequence from its projection, with the lines and
  roles the view's windows own, the way S2 built it (`build_sequence`).
- **What the expansion owns.** It owns the middle.
- **What it shows as context.** Up to `OVERLAP_TURNS` (5) turns on each side of the clipped record, owned by no one.
  The per-side budget is the one a window has (`OVERLAP_SIDE_BYTES`, 4,800).
- **The check.** The windows are checked as S2's are (`check_windows`), and a violation is refused by name.

`views.expand` writes the windows and logs the decision, as before.

**The record's own head and tail are left out.** The lead chose this in the design review. An entry for the head or
tail would carry the same label key as the middle, and the head and tail are already the window's.

The limit this leaves: when the exposure is shown only in the clipped record's own head, the expansion does not see
it. The window and the expansion then judge the exposure differently, and `settle_occasions` makes the occasion
`exposure_unknown` (pending). That is the safe direction.

**Labels and roles.** Labels follow `entry_labels`: e1 is the first overlap entry before the middle, then the middle,
then the overlap after it. An overlap entry keeps its record's own role and reads `(overlap)`. A reading may quote it as
evidence. It may not place an event, an occasion or an owned claim there: `RECORD_INTEGRITY` holds as it did, and so
does `OBSERVATION_INVALID` for a stored occasion.

**Overlap rows.** An overlap entry the budget cuts or drops becomes an `origin: overlap` row in the expansion's
manifest, as in a window. The expansion decides nothing about it.
- `stage_read.overlap_accounting` now takes the view's expansion windows too.
- Each of their rows is credited through the window that owns its record, under the same conditions: that window was
  accepted, and it shows the interval or lists it as its own omission.
- Otherwise the row is uncredited, or refused by name as `OVERLAP_INTERVAL_UNSHOWN` or `OVERLAP_OWNER_MISSING`.

**A middle too long for one window** is split into spans and cut across several expansion windows. Each window owns
only spans of the middle, and the spans tile it with no gap and no overlap. Each window's overlap is the turn slice
the sequence puts around it, so a later window's overlap begins with the middle's earlier spans. The golden "split"
run checks this over a middle of 68,853 characters cut into 10 windows, whose overlap holds 112 rows.

**What it costs.**

| Fixture | Overlap the expansion shows |
| --- | --- |
| dw2 | lines 1-2 before, line 4 after: 384 B |
| dw5 | lines 18-25 before (the test guide's read at 22-23), line 27 after (the report): 1,160 B |

Under the golden bound, the bound a fixture sets with a 100,000-byte packet overhead, a window's ceiling for one entry
is 5,905 bytes once the overlap's reservation is taken. So dw2's and dw5's middles (6,201 and 7,338 characters) are
shown in two parts within one window. With a real packet's overhead the ceiling is far above these sizes.

**`settle_occasions` is unchanged.** An expansion that now shows the exposure judges it as its window does more often.
The §11 rule stays: an eligible occasion not observed outweighs `exposure_unknown`, and an eligible observed one alone
does not.

## 2. An eligible occasion cites a quote at or before itself (§11)

D-20261104-6df529 holds that an occasion the records show before its exposure is no instance. Until now read.md said
otherwise: such an occasion went in as `exposure_unknown`.

**read.md now says:**
- `eligible` when the window shows the exposure before the decision or action, and then "a quote of that entry or an
  earlier one shows it";
- `exposure_unknown` when the window does not show the exposure, or not which came first;
- "Leave out an occasion the window shows coming before its exposure: it is no instance."

**What code can check, and does.** The check is `EXPOSURE_ORDER`, in `answer_problems`, the stage's check of the
reader's answer. An eligible observation must cite at least one quote on its occasion's record or on an earlier one.
- An occasion is a record (its entry label names no block or character), so a quote on the occasion's own record
  counts as not after it.
- The answer is refused only when every quote it cites stands on a later record. It is then retried once with the
  line, like any stage-check failure.

The check is necessary, not sufficient. Code does not know which quote shows the exposure, so it cannot tell that an
exposure came after the occasion.

**Where the check applies (§11, re-read for the lead's condition).** §11 lists exposures that rest on records outside
the transcript: delivery at the surface's level (§6.3), the session's pin, an invocation's path and hash, the host's
loading record. In S3 today an instance's exposure comes only from the reader's answer. The reader judges it from the
window, as read.md asks: "if the window shows its exposure rule held". The table-driven exposure predicate that will
read the out-of-transcript records is WP-21's (`claims.py` names WP-21 as the consumer of `exposure_rule`).

So no path to eligible bypasses the window today, and none is exempted. The check sits in the reader's answer check.
An exposure code derives later from those records will not pass through it.

## 3. DW5 reads as its intent now says

The fixture's intent (`FX_DW5_INTENT`) changes in three places:
- **The first ask has no row.** It comes before the guide's read, so it is no instance.
- **The asking again on line 15 is an occasion of its own**, eligible and observed. The fixture counted one occasion too
  few (`2026-11-05T2113--0546a25--...`, §3).
- **The test run's occasion is eligible and not observed.** Its expansion now shows the test guide's read before it
  and the report after it, and the reading cites both beside the line that did not pass.

What code derives:

| Item | Before | Now |
| --- | --- | --- |
| P-1 counts | eligible 2, observed 1, not observed 1, exposure_unknown 2 | eligible 3, observed 2, not observed 1, exposure_unknown 1 |
| P-1 resolution | not_observed | not_observed |
| T-1 counts | exposure_unknown 1 | eligible 1, not observed 1 |
| T-1 resolution | pending | not_observed |

## 4. Controls

Each was shown to fail by name when its subject is bent (pretrial `pt8c-b`, a work tool outside the repository).

Pretrial `pt8c-b` ran 15 rows: 2 `none` rows passed and 10 bending rows were caught by name. The other 3 crashed the
suite. Each bent something the product's own window check refuses by name (`OVERLAP_MISSING`): the expansion's overlap
turned off (in a `views` row and a `stage_read` row) and the clipped record itself among its neighbours. The refusal
ends the suite at its first expansion, before any control reports. `pt8c-b2` judged those rows as product refusals and
added rows that drop the neighbours with the overlap kept, which the window check cannot see. One of the new rows was
caught by only one of its two controls, so the golden-run control was strengthened to require every expansion window to
name a record other than its own, and `pt8c-b3` re-ran the three rows aimed at it.

| Control | Bent subject | Run |
| --- | --- | --- |
| `views`: "the view check reads a clipped result's error lines between the clip's own bounds" | `error_lines_of` back on the character bounds | b |
| `views`: "a middle too long for one window is cut across several expansion windows ..." | the neighbours dropped (overlap kept); the neighbours owned by the expansion | b2, b |
| product: `check_windows` in `expansion_windows` (`OVERLAP_MISSING`) | the expansion's overlap turned off; the clipped record itself among its neighbours | b2 |
| `stage_read`: "WP-08c, DW5 (golden): the test run's expansion owns its omitted middle alone ..." | the neighbours dropped | b3 |
| `stage_read`: "WP-08c: the golden run's expansions show their records' neighbours ... and the read record accounts their overlap rows" | the neighbours dropped; the expansions' rows left out of the accounting; the expansions not passed to it | b3 |
| `stage_read`: "WP-08c: an expansion's overlap row is accounted through the window owning its record ..." | the expansions' rows left out of the accounting | b, b3 |
| `stage_read`: "answer_problems: an eligible occasion citing only a quote on a later record" | the check removed | b |
| `stage_read`: "answer_problems (WP-08c): an eligible occasion citing a quote on its own record holds ..." | a quote on the occasion's own record counted as after it | b |
| `stage_read`: "WP-08c, DW5 (golden): the first ask ... is no instance ..., and the person asking again ... is one" | the first ask reported; the asking again dropped | b |
| `stage_read`: "DW5 (golden): every intended judgement ..." | the test run's reading citing its middle alone | b |
| `stage_read`: "DW5 (golden): code derives P-1 not observed ... and T-1 not observed ..." | the test run's reading citing only the report, which the order check refuses | b |

## 5. Decisions

- D-20261106-da2ec7: the order check, and where it applies.
- D-20261106-469bf7: what an expansion shows, and what it leaves out.
- The owner's decisions this commit rests on: D-20261105-43f93d (the observation-path gaps move into WP-08c) and
  D-20261105-82fdee (the live check and its budget).
