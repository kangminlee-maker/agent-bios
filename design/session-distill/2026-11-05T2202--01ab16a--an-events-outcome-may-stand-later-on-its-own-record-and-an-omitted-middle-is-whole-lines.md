---
created_at: 2026-11-05T22:02:00+09:00
head: 01ab16a
kind: design
supersedes: null
---

# An event's outcome may stand later on its own record, and an omitted middle is whole lines

WP-08c, commit A (items 1 and 2 of the package). It amends §5.4 of the mechanism design
(`2026-10-20T1942--9684f05--mechanism-design.md`) in two places: what "later" means to the stitch, and where a clip
cuts a tool result. Both come from dw2-live1 (record `2026-11-05T2113--0546a25--...`): its open cleanup event was a
line the expansion cut, and the stitch did not offer the claim that showed the outcome, because that claim stood on the
event's own record.

## 1. "Later" inside the event's own record (§5.4, Stitching)

**Before.** The stitch offered an event the claims "recorded after it": a quote counted as after when its record stood
after the event's record, by (segment, line) within a session and by instant across members. A quote on the event's
own record never counted. A tool result often holds both: its beginning sets something off and its end reports how it
went. In dw2-live1 the window's claim quoting the result's end stood on the event's record, so the stitch was shown
only the next record's claim and left the event unresolved.

**Now.** An event's anchor is where it stands inside its own record: the latest end, in (block, character) order, of
the quotes its own claims place on that record (`stage_read.anchor_of`). Blocks order by their JSON pointer, a numeric
segment by value, so `/10` follows `/9` (`block_order`). A quote on that record stands after the event when it begins
at or after the anchor (`joinable_claims`). The other conditions stay: the quote is one the run processes (in-window or
backlog, never context), and it is not a quote of the event's own claims.

What stays as it was:
- An event whose own claims place no quote on its record has no anchor. Only its record is known, and no quote on that
  record stands after it.
- A carried event names no claims of its own in this run, so it has no anchor.
- Across records the rule is unchanged.

**Overlap is not after.** A quote that begins before the anchor does not count, even when it ends after it. The lead
chose this conservative reading in the WP-08c design review: such a quote shares text with what the event's own claim
quotes, so it cannot show only what followed.

The stitch's stage check reads the same `after` lists (`stitch_problems`), so the packet and the check agree.
`packets/stitch.md` says it in one clause: quotes stand after the event "on its own record too when they follow what its
own claims quote there".

## 2. A clip cuts on line boundaries (§5.4, the reading view)

**Before.** A tool result over 4,000 characters showed its first 1,200 and last 800 characters, plus its error lines.
The cut was by characters, so it could fall inside a line. That line was then split between a shown side and the
omitted middle, and an expansion of the middle began or ended mid-line. In dw2-live1 the expansion ended at
"cleanup 028", and the line's "done" sat in the tail.

**Now.** `views.clip_bounds` moves each cut to a line boundary:
- The head ends at the last line end at or before 1,200, when that keeps at least 600 characters of head.
- The tail starts at the first line start at or after `len - 800`, when that keeps at least 400 characters of tail.
- Otherwise the cut stays by characters, as in a block that is one long line.

The omitted middle is then whole lines. `clip_parts` and `error_lines_of` (the view check's own reading of the error
lines) take their bounds from this one function.

**Measured on the fixtures.**

| Fixture | Block | Cut by characters | Cut on lines |
| --- | --- | --- | --- |
| dw2 (line 3) | 8,144 characters | 1,200 to 7,344 | 1,176 to 7,377 |
| dw5 (line 26) | 9,332 characters | 1,200 to 8,532 | 1,200 to 8,538 |

**What moves.**
- An omission's id and its span's sha256 are computed from the span, so both change for every clipped record whose
  cut moves.
- A window shows a few characters fewer (dw2: 57). Windows are cut on the rendered text, so a boundary between windows
  can move.
- An answer stored by an earlier run carries a payload sha256 that no longer matches. Resume does not reuse it, so
  those run folders are not resumable with this code.

The golden pins that depend on window bytes still hold: the shard rule's 3,000 bytes of room, and the live apart and
twin fixtures' turn counts (548, 537).

## 3. Controls

Each control below was shown to fail by name when its subject is bent (pretrial `pt8c-a`, a work tool outside the
repository).

| Control | Bent subject |
| --- | --- |
| `views`: "WP-08c: a clipped tool result's head ends at a line end ..." | the cut by characters restored; the head's half rule dropped; the tail's half rule dropped |
| `stage_read`: "WP-08c: on the event's own record a processed quote stands after the event ..." | the within-record rule dropped; overlap counted as after; the anchor at the earliest end |
| `stage_read`: "WP-08c (golden): an event on dw2's clipped result ... is joined ... and resolved" | the within-record rule dropped; the anchor not passed to the stitch |
| `stage_read`: "WP-08c, live leg dw2 (golden): the clipped result's omitted middle is whole lines ..." | the cut by characters restored |

The golden event control runs dw2's fixture with one more event. The window's event sits on the clipped result and
rests on a quote of its head, and the expansion's claims quote the decisive line in the result's middle. The stitch
resolves the event with those claims. With the rule by record alone, it lists no joinable claim for that event.

Decision: D-20261105-2731ac.
