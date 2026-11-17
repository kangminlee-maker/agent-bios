---
created_at: 2026-11-03T23:25:00+09:00
head: e6cb055
kind: design
supersedes: null
---

# A stage judges what a static contract cannot name, and one read sees both verdicts

Design §3.2 places the gate's steps 4 (references) and 5 (accounting) in the gate, read from the stage's static
`contract.json`. WP-08's second commit (4e08e5f) added a stage-check slot to `dispatch.Supervisor.item`, and S3 uses
it for the part of those steps that depends on the window a call was sent. The lead approved the slot with four
conditions (2026-11-03). This record says what moved, why, what did not, and how each condition is held.

## What moved, and why

For S3, the per-window part of steps 4 and 5 is computed by the stage's judge, `stage_read.judge`
(`answer_problems`):

- every quote names an entry the window shows;
- every evidence id and claim id resolves inside the same answer;
- every claim echoes the packet's CALL-ID;
- an event starts on an owned record that is not context, and an observation's occasion lies on an owned record;
- ids do not repeat;
- an observation is one due in the window;
- there is one decision for each of the window's own omissions, and none skips a forced one.

The supervisor asks the judge only of an attempt the gate accepted.

Why: `contract.json` is one file per stage. It cannot name which entries a given window shows or which omissions it
owns. Writing a contract per call would make the contract an artifact of each call rather than of the stage, which
the second commit's record already closed.

## What did not move

- The gate runs all five steps on every attempt, exactly as before, including the static references and accounting
  of `contract.json`.
- The judge can only fail an attempt. It never accepts one the gate refused, and it is not asked of one.
- A judge failure is retried exactly as a gate failure: once, with its lines in the correction.
- The gate stays generic. What it knows is that a stage may record a judgement beside an attempt
  (`gate.STAGE_CHECK`, `{"failures": [...]}`), not what any stage checks.

## The four conditions

1. **One read of acceptance.** `gate.accepted` refuses an attempt whose recorded stage check failed, on every read
   (STAGE_CHECK_FAILED). The reader reads with `judged=True`, which also refuses an attempt no judgement was recorded
   for (STAGE_CHECK_MISSING). So the gate and the judge have one answer between them, and no path reads a
   judge-failed attempt as accepted.
   - Controls, gate: four reads of a materialized call (failed, read plainly and judged; missing, judged; passed,
     judged).
   - Controls, dispatch: an attempt its stage check failed is never read as accepted.
   - Controls, stage_read: a supervisor that hands back the judge-failed attempt as the accepted one gets its unit
     quarantined with STAGE_CHECK_FAILED, and none of that attempt's claims is stored.
2. **One corrective retry, shared.** The item makes two attempts at most, whichever of the gate and the judge failed
   them. `gate.settle` already refuses a third attempt (RETRY_EXHAUSTED).
   - Controls, dispatch: a judge failure on both attempts fails the item; a gate failure and then a judge failure end
     the item at two attempts with the judge asked once.
3. **The judge is pure.** It reads its attempt's call directory (the answer and `call.json`) and nothing else. It
   makes no model call, uses no network and writes nothing. The supervisor, not the judge, writes the judgement into
   the call directory under the run.
   - Control, stage_read: asked of a read-only copy of an accepted attempt, the judge answers the same and the run
     directory's files are byte-for-byte unchanged. A copy is used because a judge that wrote during the run would
     write the same bytes again, and the run would show no change.
   - Dispatch's import-closure judge already refuses any executor in `stage_read.py`.
4. **Failures are named where they can be counted.** Each window's read record lists its attempts as
   `{call, stage_check}`: the lines when the check failed, `[]` when it passed, `null` when the gate failed the
   attempt first. The same lines are in the attempt's call directory (`stage_check.json`), so the C1 page can count
   judge failures from either.
   - Controls, stage_read: the read record and the call directory carry the same lines for the forced-omission
     window's first attempt, and that attempt reads as STAGE_CHECK_FAILED.
   - Controls, dispatch: the verdict is written beside each attempt it judged.
