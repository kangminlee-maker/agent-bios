---
created_at: 2026-11-05T21:13:00+09:00
head: 0546a25
kind: design
supersedes: null
---

# dw2's open cleanup event is a line the expansion cut, and done-when 2 holds by its own words

This record adds to WP-08b's live result,
`2026-11-05T2105--a933acb--under-the-short-labels-no-copy-was-refused-and-dw5-judged-as-its-fixture-intends.md`.
The lead asked for these analyses after reading the pair's log. That record was committed before the request arrived,
so this one carries them. It does not replace it. No model call was made for them; both legs are fixtures, so their
text is quoted.

## 1. The unresolved event in dw2

**Judgement.** The event `v-63849835b10b83a2` is not open in the fixture. The cleanup it waits for is complete in the
source. The reader left it open because the expansion's text ends in the middle of a line.

**Where it came from.**
- The fixture's tool result (`fx_decisive_log`) ends with 45 lines, `cleanup 000 done` to `cleanup 044 done`.
- The record is clipped, and its omitted range is characters 1,200 to 7,344. That range ends inside the line
  `  cleanup 028  done  ----`, after `cleanup 028  ` and before `done`.
- **The expansion.** It shows the omitted range alone (`overlap=False`). So its text ends `cleanup 027  done`, then
  `cleanup 028` with nothing after it.
- **The event.** The expansion's reader wrote a pending event of kind `cleanup run` on that record: "A cleanup phase
  after the restore and copy reached step 027 done and was cut off at step 028, so whether it completed is not shown."
  - Its one claim says the same.
  - Its uncertainty says that the output may simply be cut off.
- **The window.** It shows the kept tail, which starts with the rest of that line (`done  ----`) and continues to
  `cleanup 044 done`. One of the window's claims quotes `cleanup 044  done`.
- **The stitch.** It offered the event, as joinable, only the claims whose quotes lie on records after the event's
  record. The event is on line 3, the tool result.
  - The window's claim quotes the same record, line 3, so it was not offered.
  - The one claim offered quotes line 4, the agent's closing turn, which says nothing of the cleanup.
  - The stitch left the event unresolved, and the fold carries it as pending.

The reader judged its own text faithfully. Nothing in the run could join the two halves of the cut line.

**Two gaps meet here.**
- **The expansion gap** of `2026-11-05T2047`, in a second form: the meaning of the expanded text depends on what lies
  just outside it, here the rest of a line rather than an exposure. Two facts make it possible:
  - The omitted ranges are measured in characters, so a range can end inside a line.
  - The expansion shows nothing around its range.

  The first fix candidate (giving an expansion the original window's surrounding records as overlap) would show the
  rest of the line. Ending each omitted range on a line boundary would also remove this form.
- **"Later" is by record.** The stitch's later claims are ordered by record (segment order and line). An outcome later
  in the same record as its event, as in a long tool result, cannot be joined to it.

WP-08's dw2-live2 left the same event unresolved, with the same id and the same description: the cleanup cut off at
step 028. Its record had the same omitted range, 1,200 to 7,344, and its expansion packet also ended at `cleanup 028`.

## 2. Done-when 2, by its own words

Plan WP-08, done-when 2 (`2026-10-20T2119--cc0498f--implementation-plan.md`) says:

> Mandatory expansion: a window whose manifest carries a forced record must have a matching `expand` decision before
> the window's record is accepted; control: a result that skips it → `EXPANSION_SKIPPED`; the decisive outcome in the
> omitted middle of a successful tool result after a pending event is found after expansion and not found without
> (O2, live through the real seat once).

It sets no condition on other events. The pair report's line "not met" required that no event be left pending after
the fold. That condition is the report script's own (`work/impl/wp08b/pair-report.py`), not the plan's. WP-08's
result record judged dw2-live2 by the plan's words ("the decisive line was in the expansion's packet only, and the
carried event resolved on it"), with the same event left open.

**Judged again by those words, on live1:**
- **The forced record was expanded.** The window was accepted at its first attempt, which the stage check would have
  refused (`EXPANSION_SKIPPED`) without the expand decision. The expansion was read.
- **Not found without expansion.** The decisive line is in no window packet; the window `w1` packet does not contain
  it.
- **Found after expansion.** The expansion's packet has the decisive line. The carried event `pe-1` is resolved on two
  claims, and its evidence on line 3, the clipped result's record, quotes the decisive line.
- **Through the real seat.** Yes: Claude Code 2.1.317, `claude-sonnet-5-5/high`.

Done-when 2 is met.

## 3. The extra DW5 instance

The instance outside DW5's intent is on line 15. It reads "I still don't follow - simpler again please?", the person
asking a second time after ask 3's answer.
- **The occasion criteria fit.** P-1's criteria are "the person asks the agent to say something it said more simply",
  and line 15 is such an ask.
- **The judgement is right.** The reader judged it eligible and observed: the guide's read is before it, and line 16
  answers in plain words.

The fixture counted one occasion too few. This is not an over-match by the model. P-1's resolution does not change.

## 4. What the labels did

**Under the `entry:` line**, before WP-08b, one of 10 window calls near-copied, as the commit 1 record says
(`2026-11-05T1900`):
- apart-live2: 5 windows;
- C1 `0708c`: 3 windows;
- C1 `0708d`: 2 windows. In one of them, six quote entries were written as `N/message/content`, an entry the window
  did not show (RECORD_INTEGRITY, six failures in its stage check). The refused answer cost a retry, which ran out of
  budget.

**Under the labels**, none of the 7 calls was refused (5 window and expansion calls, and 2 stitches).

The comparison in the 2105 record counts only the refusals WP-08's result record lists. It leaves out `0708d`, so its
"none" under the `entry:` line is corrected here to one of 10.

## 5. What remains

- **Merge.** Merging `wp/08b-labels` (`303372d` to this commit) is the lead's, after the owner's answer.
- **The expansion gap.** Both of its forms (an exposure outside the expansion; a line cut at the omitted range's end)
  wait in the lead's backlog with their fix candidates. The owner is to say when they are taken up.
- **"Later" by record.** An outcome later in the event's own record cannot be joined to it (§1). This is a candidate
  for the same backlog.
- **Ask 1's rule.** read.md and D-20261104-6df529 give different rules for an occasion shown before its exposure. This
  is in the lead's backlog.
- **DW5's intent.** The intent omits line 15's occasion. Adding it would change the golden counts (P-1 eligible 3,
  observed 2) and no resolution.
- **The answer's own ids.** The read schema's patterns for ids the answer makes up itself keep `$` (`2026-11-05T2003`).
- **The pair report.** Its dw2 line checks a condition the plan does not have. The script is outside the repository
  and is fixed before its next use.
