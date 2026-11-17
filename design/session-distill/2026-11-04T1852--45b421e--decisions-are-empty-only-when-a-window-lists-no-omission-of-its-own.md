---
created_at: 2026-11-04T18:52:00+09:00
head: 45b421e
kind: design
supersedes: null
---

# Decisions are empty only when a window lists no omission of its own

WP-08 commit 7. ⑦'s X review, round 1 (`work/lead/wp08-x7-r1-review.json`), accepted 45b421e with one minor finding:
- `read.md` said "An empty list is a valid answer for any of the five."
- The `decisions` bullet above it asks for one decision per omission the window lists.

So for a window that lists an omission of its own, the sentence allowed an answer the stage refuses (`SET_MISMATCH`).
C1's child window lists one, so the sentence could cost C1 a retry. The lead closed X at round 1 and checks this commit's
diff directly.

## Reproduction

`work/impl/wp08/c7/repro-empty.py` ran on 45b421e over the dw2 leg's golden window, which lists one omission forced by
a pending event:
- its packet's only sentence about empty lists was the one above;
- an answer with `decisions: []` was refused `SET_MISMATCH omission manifest`.

After the fix, the window's packet holds only the qualified sentence, and the same answer is still refused the same way.

## The change

`read.md`'s last line now reads:

> An empty list is a valid answer for `quotes`, `claims`, `events` and `observations`. `decisions` is empty only when
> this window lists no omissions of its own (`none` above); otherwise it holds one decision for each.

**The control** (stage_read, 159 to 160): "a window that lists an omission of its own is refused with no decisions, and
no sentence of its packet allows an empty `decisions`". For every live-leg window packet whose window lists an
omission of its own:
- every sentence about an empty list that names `decisions` must carry the condition;
- no such sentence may speak of every list at once;
- the premise is held too: the dw2 window's answer with empty decisions is refused `SET_MISMATCH`.

**The pretrial.** The unmutated `stage_read` and `packet` suites passed.

| Mutation | Caught by name |
| --- | --- |
| the old sentence restored | the new control |
| `decisions` listed among the lists that may be empty | the new control |

## A note the lead asked to be recorded

done-when 3's golden apart session (`stage_read.fx_apart_records`) keeps the cause and its outcome four windows apart
in what the windows own only. In the overlap, the outcome shows in windows 1 to 4 and the cause in window 5. The live
apart session (`fx_apart_live_records`) is the one that tests the real property.

This is in the lead's backlog (decided 2026-11-04, option (가) of the 45b421e report). The revisit condition is when the
shard control's reference bytes are next recalibrated, and at the latest before WP-08 merges.
