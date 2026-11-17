---
created_at: 2026-11-05T20:03:00+09:00
head: 303372d
kind: design
supersedes: null
---

# A label pattern ends where its string ends, for every reader of the schema

WP-08b, a fix to commit 1 (`303372d`, record `2026-11-05T1900--6ee4a22--a-packet-names-what-its-reader-writes-by-labels-of-its-own.md`).
Review X round 1 accepted commit 1 with two minor findings. This commit answers both. The packet text, the label maps
and the stores do not change.

## 1. The end of a label pattern

**What was wrong.** Each label pattern ended in `$`, for example `^e[1-9][0-9]*$`. The schema has two kinds of reader,
and they read `$` differently:
- Python's `re`, which `jsonschema` uses, lets `$` match just before a final line break. So `e1` followed by a line
  break passed.
- The host checks the answer with Ajv, a JavaScript validator. There `$` matches only at the end of the string, so the
  same answer was refused.

Nothing wrong could be stored. A label with a line break is not in the packet's label table, so `Labels.resolve` and
`StitchLabels.resolve` refuse it as `UNKNOWN_LABEL`. The defect was that the code and the host disagreed on what the
schema accepts.

**Reproduction.** The test answer had one value at each of the 8 label fields: 5 read fields (`quotes/entry`,
`events/at_record`, `observations/occasion_locator`, `observations/expected_id`, `decisions/omission_id`) and 3 stitch
fields (`event_id`, `claim_ids`, `evidence_ids`). Each field was bent three ways: `e1` plus a line break, `e12` plus a
line break, and `e1` plus a carriage return and a line break, each with the field's own prefix. That makes 24 bent
answers, judged four ways offline: the schema as written under 2020-12, the host form under 2020-12, the host form
under draft-07, and Ajv configured as Claude Code 2.1.317 configures it.

| Readers | Bent answers accepted, at `303372d` | After this fix |
| --- | --- | --- |
| The three Python readers | 16 of 24: every field, both line-break shapes; the carriage-return shape refused | 0 of 24 |
| Ajv | 0 of 24 | 0 of 24 |

All four readers accept the valid answer, before and after.

**The fix.** Each of the six label patterns now ends in the assertion `(?![\s\S])`: no character of any kind may
follow. Three patterns are in the read schema (`entry`, `omission_id`, `expected_id`); `entry` is defined once in
`$defs` and used at three fields. Three are in the stitch schema (`event_id`, and the items of `claim_ids` and
`quote_ids`). The assertion means the same thing in ECMA-262 and in Python. `\Z` would not work: JavaScript has no
such escape.

**What is left with `$`.** The patterns of an answer's own ids keep their `$`: `quote_id`, `claim_id` and `event_id`
of the read answer, and the items of its `quote_ids` and `claim_ids`. The model makes these ids up itself; it does not
copy them from a packet. They are keys inside one answer, and code replaces them with stored ids before anything is
written. A line break in one of them can only make the answer's cross-references match or fail. The same reader
disagreement holds for them, and the same one-token change would remove it.

**Controls.** The schema control (`stage_read` self-test) adds `e1` plus a line break to its near copies. It now
requires 12 refused shapes at each of the 5 read and 3 stitch fields, so 60 and 36, under the written schema and the
host form alike.

## 2. A quote two claims cite

A stitch packet lists each claim with its quotes. A quote that two claims cite has one label (`StitchLabels`), and it
is listed under each claim. The rendering stays as it is. The rule is: **when a label's definition appears more than
once, every appearance is the same bytes.**

The stitch packet control now holds that rule. It writes every listing of a quote again from its parsed form and
requires one text per label. It also requires at least one label listed more than once, so it cannot pass on packets
where no quote is shared. Before this commit, none of the stitch packets the control reads (those of the live legs'
golden runs) listed a quote under two claims. The golden reading of done-when 2's session now claims twice on its
decisive quote (`fx_decisive_answers`), so the dw2 stitch packet lists that quote under two claims. This changes the
fixture's answers, not code.

## 3. Sizes

The new assertion is 11 bytes longer than `$` in the schema's JSON. The host form inlines `entry` at its three fields.
So the fixed part of a read packet grows by 55 bytes and a stitch packet's by 33. The room under
`bound.PACKET_OVERHEAD` (12,288) is now:
- read: 730 bytes, down from 785;
- stitch: 4,536 bytes, down from 4,569.

`packet`'s self-test holds both. The windows are cut against `PACKET_OVERHEAD`, not against the fixed part, so no window
boundary moves. Each live read call's driver bytes grow by the same 55 bytes, and each stitch call's by 33.
