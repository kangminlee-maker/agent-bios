---
created_at: 2026-11-04T18:20:00+09:00
head: 4432262
kind: design
supersedes: null
---

# A reader copies an entry from a line that holds only it, and the live apart session keeps its outcome out of earlier windows

WP-08 commit 7. apart-live1 stopped at its call cap (`2026-11-04T1742--1cb256d--…` is the schema record before it).
The owner answered on 2026-11-04 (D-20261104-e9019d, through the lead):
- fix the apart fixture and run the apart leg alone live again, cap 7; then C1, cap 7;
- WP-08 stays within 31 calls in all;
- the twin is not run live; it is asked again together with DW5;
- before any rerun, fix the two places in the packet text where readers miscopied an id.

## Reproduction

Three live answers were refused by the stage's check. Their structure, ids and codes only:

| Call | Refused | What the packet offered |
| --- | --- | --- |
| apart-live1 w1 a1 | `RECORD_INTEGRITY entry '7/message/content/0' at quotes/q6 is no entry this window shows` | `[7/message/content/0/text]`, once, as an overlap entry's heading |
| apart-live1 w2 a1 | the same entry at `quotes/q4` | the same heading, once |
| dw2-live2 x1 a1 | `RECORD_INTEGRITY call id 'CALL-ID: <id>' …` at claims c1 and c2 | `CALL-ID: <id>`, the packet's first line |

The form without `/text` appears nowhere in either packet: the readers shortened the value. Both retries (w1 a2, w2 a2,
x1 a2) were accepted.

After the fix, `work/impl/wp08/c7/repro-check.py` put the three stored answers through the tree's `answer_problems`
again, against the window or expansion document each call read. All three are still refused, with the same codes and the
same counts (1, 1, 2).

## The wording

**The heading.** `views.header_of` writes an entry's heading on two lines:

```
entry: 7/message/content/0/text
assistant 2026-10-03T02:05:00.000Z in_window
```

The first line holds nothing but the value, under the answer field's own name. Before, the value stood in brackets
before the kind, time and role. The heading is 5 bytes longer per entry, and S2 measures it as it cuts, since S2 sizes
every entry by `render_entry`.

**read.md.**
- An entry starts with two lines; the second ends `(overlap)` on an overlap entry.
- A quote's `entry` is the rest of that entry's `entry: ` line, every character to the end of the line, without the
  label. `at_record` and `occasion_locator` are written the same way.
- `call_id` is the rest of the packet's first line, `CALL-ID: <call id>`, without the `CALL-ID: ` label.

The payload still holds no call-specific text, so two calls of one judgment still share a payload hash.

**stitch.md.** Each id is written as the value of its field in the lines above (`event_id`, `claim_id`, `evidence_id`),
whole and without the field name. No live stitch answer was refused, and this states the rule the read packet now states.

## The fixture

apart-live1's session had five long turns. A long turn's spans count as one turn, so the five-turn overlap of every
window before the outcome's reached the outcome. Every live window then quoted it. The golden control checked owned
records only, and so it passed.

- **`stage_read.fx_apart_live_records(turns, outcome)`.** The request, `turns` short turns, then the outcome turn. A short
  turn is one entry of about 130 bytes.
- **The shape.** `work/impl/wp08/c7/apart-shape.py` cut the session under the measured allowance, as `fx_reader`
  declares it, for each turn count:
  - fewer than 454 turns: S2 puts the tail into the fourth window, which leaves four windows;
  - from 454: five windows, the fifth starting at line 451;
  - 460, the value chosen: the outcome follows eleven turns of the fifth window, six past the fourth window's reach.

  The golden window bytes, overhead aside, are 15,753, 15,840, 15,840, 15,840 and 2,427.
- **The twin.** It is the same function with 449 turns and no outcome: the records before the apart's fifth window. S2
  cuts it into the apart's first four windows exactly.
- **`fx_apart_records`.** It returns to its form before 7c5b801, since the live legs no longer use its added parameters.
  It is still done-when 3's golden session. Its docstring now states what this record found: its windows are apart in
  what they own, not in what they show (see "What is still open").

## The controls

`stage_read` has six new controls, 153 to 159:
- **apart (a).** No window before the outcome's owns the outcome or shows it in its overlap, shown or named. No packet of
  those windows holds the outcome's text.
- **apart (b).** The outcome's window neither owns nor shows the cause, and its packet does not hold the cause's text.
- **twin (c).** No window of the twin owns or shows an outcome, and no packet of the twin holds the outcome's text.
- **The heading line.** For each live leg's window packets, the values on `entry: ` lines are exactly the entries the
  stage's check takes as shown.
- **The two live shapes.** An entry written without its last part, and a call id written with its label, are each
  refused by name. The same answer as the packet offers it is accepted.
- **No later keyword** (the lead's request after 1cb256d). No schema S3 hands a host carries a keyword that draft 2019-09
  or 2020-12 added. Claude Code's `--json-schema` check is a draft-07 Ajv in strict mode, and it refuses such keywords as
  unknown.
  - The control walks keyword positions only; a property's name is not a keyword.
  - The policy admits one such keyword, `dependentRequired`, and this control's pretrial row plants it.

Two existing controls changed with the heading:
- **D-20261103-8bfd69 condition 2** needs an overlap row on a record the run does not owe. That row came only from how a
  side's overlap budget happened to fill, and 5 bytes per entry changed the fill.
  - `views.fx_main_records`' record before the window is now longer than an overlap item, so the first window's overlap
    cuts it, and the row exists by construction.
- **views' "a quote of what the overlap cut off is not located in the overlap"** now picks a cut overlap entry that a
  window owns. The record before the window is cut too, and no window owns it. If no owner is found, the control fails
  by name instead of raising StopIteration.

**The pretrial.** Each row is one mutation in a fresh copy of a clone carrying the change. The unmutated
`views`, `stage_read`, `packet`, `evidence`, `claims` and `measures` suites passed first.

| Mutation | Caught by name |
| --- | --- |
| the bracketed heading restored | the heading-line control (and the apart window controls, whose cuts the 5 bytes move) |
| apart back to long turns (`fx_apart_records` without its last turn) | apart (a) and apart (b) |
| the twin with its outcome turn | twin (c) |
| `dependentRequired` planted in read's `claim` | the no-later-keyword control |
| the check accepting a prefix of a shown entry | the two-live-shapes control |
| the check accepting a call id with its label | the two-live-shapes control |
| the record before the window short again | D-20261103-8bfd69 condition 2 |
| views' cut entry chosen without an owner | views' "a window owns the cut overlap entry" |

No row raised a traceback. The decision is D-20261104-beee02.

## What changes elsewhere

- **The C1 candidate's views.** S2 cut `c1-cand-20261103-0708`'s windows with the bracketed heading. S3 renders them with
  the new one, which adds 5 bytes per entry.
  - The dispatcher measures the real packet against the bound, so nothing passes unmeasured.
  - A window cut close to the bound may be refused, though. C1 should run over views S2 makes with this code.
- **The live legs' cost.** apart-live1's w2 a2 made two requests in one call:
  - the first ended `end_turn` with text and no `StructuredOutput` call;
  - the stream then carries a user-role text event (its text not read);
  - the second request answered through `StructuredOutput`.

  So this was the host asking again within the call, not the dispatcher's retry. It cost 24,272 input tokens (mostly
  cache reads on the second request) against about 11,300 for a single request. It happened once in the 17 calls that
  made requests, and the next legs' estimates carry one such call each.

## What is still open

- **done-when 3's golden session (`fx_apart_records`)** shows the outcome in the overlap of windows 1 to 4, and the cause
  in window 5's overlap. Its golden reader answers from the owned records alone, so its controls hold. But "four windows
  apart" is true only of ownership. The lead decides whether it moves to the short-turn shape; that would recalibrate
  the shard control, which uses the same session.
- **Whether live readers now copy both ids correctly** is apart-live2's question. The packet text is in ⑦'s X review.
