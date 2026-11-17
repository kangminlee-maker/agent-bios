---
created_at: 2026-11-11T21:30:00+09:00
head: 5252171
kind: design
supersedes: 2026-11-11T2045--8e6987f--s6-derives-every-candidate-both-judges-judged-and-names-the-ones-it-cannot.md
---

# WP-11 J4a follow-ups: what S6 cannot determine it names and counts, and a run without its budget is refused

The lead's five items on J4a (2026-11-11), before J4b. No model call is made.

## 1. For C3: the S6 sample is sized by spend

This replaces the two figures in the J3c record's "For C3" with one proposal.

```
budget.per_stage.S6 = 3500000          declared explicitly; C2 declares none
judge.candidate_kinds = {"formed": "all", "g_cluster": "all", "legacy": 4, "redundancy_hint": 4}
```

- **Why spend.** Dispatch reserves a stage's budget as spend, which is input plus output. Each call is reserved at
  its spend at most before it is made (BUDGET_EXHAUSTED otherwise). So the sample is sized by spend:
  - a call's input, `ceil((payload bytes + 9,000) / 2.27) + 3,795`;
  - plus output at J0's upper median of 10,933 tokens a call, for two judges per candidate;
  - leaving room for the last reservation (234,670: the largest call's spend at most at the 20,000 cap, one retry).
- **The figures.** On C2's medians that gives 4 legacy and 4 redundancy_hint candidates beside every formed and
  g_cluster one, a total of 3,224,276.
- **Before the declaration.** The final sizes are recomputed from C3's own `judge --dry`, with the same formula,
  before the declaration is written. That uses the per-source median payload bytes the dry run reports.
- **Not used: 6/6.** Six of each is the input-only figure (3,384,892). It leaves no room for output or for the last
  reservation, so its last calls would be recorded `not_done`.

## 2. A run without `budget.per_stage.S6` is refused before any call

- **The code.** `Supervisor.reserve` reads `run["budget"]["per_stage"].get(stage)`. When it is None, it raises
  `BUDGET_UNDECLARED S6: run.json declares no budget for the stage`.
- **What happens.** That is a refusal, not `Exhausted`, so `Supervisor.item` does not turn it into `not_done`. It
  leaves S6, and every reservation precedes its call, so an undeclared budget refuses S6 by name before the first
  call. Absence is not "no ceiling", so nothing needed fixing.
- **The control.** A golden run through S5 with no S6 budget is refused BUDGET_UNDECLARED S6 and holds no S6 call
  directory. Reverting dispatch's check to an unlimited budget fails the control.

## 3. The reconsiderations' receipts

- **The reader.** `stage_receipts` is the check that reads every accepted call's receipt: N#1's one payload per key,
  and one packet per receipt.
  - Controls build their own rows from the kept reconsiderations' receipts. The pair passes, and the same pair with
    one payload hash changed is PACKET_DIVERGENCE.
- **What it cannot see.** The check cannot see a receipt missing from its list, because it does not know which
  receipts should be there. So the run now records the receipts it held to N#1 by kind (`receipts_checked`, from
  `receipt_counts`).
  - A control requires the reconsideration count to equal the accepted reconsideration calls.
  - Leaving the reconsiderations' receipts out of the list fails that control.
- **A renamed key.** The sweeps' receipt key is now `sweep/<group>/<shard>`, so every kind is named by its prefix.

## 4. The arc confirmation is undetermined, not false (D-20261111-f122c0)

- **No producer before S6.** Design §7.4's only producer of an arc confirmation is "an arc retrospective the owner
  confirms in the review". That review comes after S6 and S7, and no run declares an arc question. S4's evidence bar
  says the same.
- **What derive is given.** It is still given `arc_confirmed` false, since it takes a boolean. The substitution is
  named and counted:
  - every type G verdict carries `arc_confirmation: undetermined`;
  - `derivations.json` counts the G candidates and those below the lineage bar of three.
- **The consequence.** At S6 a type G candidate is eligible by its lineage count alone.
- **Revisit** when a run's declared question names an arc, or when the review records an owner's arc confirmation
  and the derivations are computed again with it.
- **Closed.** Passing false silently was closed. So was refusing to derive G candidates: their other derivations do
  not depend on the arc.

## 5. No unit outcome, said by name

`derivations.json` and the run summary carry `unit_outcomes: {state: none, candidates, why}`. Unit outcomes are read
at the release reference point (§6.4), and S6 judges only the current point until S5 retrieves at a release point
(D-20261111-c4fa71). S7 (WP-12) receives no unit outcome in release 1.

## Controls

stage_judge's self-test goes from 165 to 172 controls. Pretrial ran seven revert rows over these items. Six were
caught on the first pass. The seventh, `RECEIPT_KINDS` without `reconsider`, raised inside a control and is caught
by name after the fix. Two J4a rows were run again after their line moved, and both were caught.

## Next

J4b: design §3.2's ten gate controls on copies of one accepted Judge A call and one accepted Judge B call (D5).
