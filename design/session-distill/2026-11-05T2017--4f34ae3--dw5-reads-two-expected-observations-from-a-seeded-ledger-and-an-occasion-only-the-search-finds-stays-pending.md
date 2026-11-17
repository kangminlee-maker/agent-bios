---
created_at: 2026-11-05T20:17:00+09:00
head: 4f34ae3
kind: design
supersedes: null
---

# DW5 reads two expected observations from a seeded ledger, and an occasion only the search finds stays pending

WP-08b, commit 2. WP-08's done-when 5 asks that a run judge an expected observation that an earlier run left. No
product path writes expected observations yet, because S4 to S12 are not implemented. D-20261105-40184d therefore runs
only the follow-up half: a run reads a ledger that an earlier run is taken to have written. It runs on a fixture
session, live, after the short labels (`303372d`, `4f34ae3`), so that one run checks the final copying form.

This commit adds the fixture, its golden controls and the plan for its live leg. The live run is the owner's, within
D-20261105-7dbc98's budget: at most 9 Claude calls, 80k input tokens and 20k output tokens across the dw2 and DW5 legs.
The leg's result goes in a record of its own.

## The fixture

**The ledger.** `fx_dw5_ledger` seeds a schema 2 ledger with two entries. Each holds one expected observation, decided
by a run `r0` and due through 2026-12-31.

| Id | Occasion | Exposure rule | Expected behaviour | Retrieval term |
| --- | --- | --- | --- | --- |
| P-1 | the person asks the agent to say something it said more simply | the agent read `guides/plain-explanation.md` in this session before the ask | the agent's next answer is in everyday words, and the person does not ask again | `more simply` |
| T-1 | a test run's output reports a test that did not pass | the agent read `guides/test-reporting.md` in this session before running the tests | the agent's next message names the test that did not pass and does not call the change done | `did not pass` |

**The session** (`fx_dw5_records`). It is the main session only, 27 records, and every line is the fixture's own;
nothing is read from a real session. A long assistant turn in the middle (160 release-note lines) splits it into two
windows:
- **Window 1** holds the first three asks and the read of the plain-explanation guide. The first ask comes before the
  read. The second ask is answered plainly at once. The third is answered plainly only after the person asks again.
- **Window 2** holds the fourth ask, the read of the test-reporting guide, a test run and the agent's report that the
  change is done. It does not show the plain guide's read, either as its own record or in its overlap.

**The test run.** Its output (161 lines) is long enough to be clipped. Only the omitted middle names the test that did
not pass, and no line reads as an error (`views.ERROR_LINE`), so the clipper keeps none of the middle. S2 does not force
this omission: its manifest row has `forced_by` none. S3's search does: T-1's retrieval term matches the omitted text,
so the omission is expanded and read (`searched.forced`). The packets list P-1 as `x1` and T-1 as `x2`, without
retrieval terms.

The leg makes three calls: two windows and one expansion, with no stitch. Their driver bytes in the golden run are
27,846, 18,773 and 19,701, under the view-window cap of 116,205.

## What a careful reader judges, and what code derives

The fixture's intent (`FX_DW5_INTENT`), as exposure and verdict for each occasion:

| Occasion | Exposure | Verdict | Why |
| --- | --- | --- | --- |
| ask 1 | exposure_unknown | observed | it comes before the guide's read |
| ask 2 | eligible | observed | answered plainly at once |
| ask 3 | eligible | not_observed | the person had to ask again |
| ask 4 | exposure_unknown | observed | window 2 does not show the guide's read |
| the test run | exposure_unknown | not_observed | found in the expansion, which shows neither the guide's read before it nor the report after it; the verdict is the fixture's choice and does not change T-1's resolution |

From these, code derives (§11, `FX_DW5_RESOLUTIONS`):
- **P-1: not observed.** One eligible occasion that is not observed decides it. Its counts are eligible 2, observed 1,
  not observed 1 and exposure_unknown 2.
- **T-1: pending.** Its only occasion is exposure_unknown, so nothing decides it. The verdict the expansion gives does
  not change this.

**T-1's intended result** (lead, 2026-11-05): the occasion is found in the expansion. If the window and the expansion
judge it with different exposures, it is exposure_unknown (D-20261104-a9e2d2), so T-1 is pending. The live leg reports
T-1's instances and resolution. It does not pass or fail on them.

## Controls

These are in the `stage_read` self-test:
- **Placement.** DW5 golden is the main session in two windows, with the records placed as above. Window 2 shows the
  plain guide's read neither owned nor in its overlap. The test run's one omission is not forced by S2, is forced by
  the search, and is expanded and read. That makes two window calls, one expansion and no stitch.
- **Instances.** Every intended judgement, four on P-1 and one on T-1, each read in labels, is an instance on its own
  record. T-1's instance comes from the expansion that read the output whole.
- **Resolutions.** Code derives P-1 not observed and T-1 pending, with the counts above.
- **Packets.** Every packet of the leg lists the two due observations as `x1` and `x2`, with their occasion, exposure
  rule and expected behaviour, and without their retrieval terms.

The live legs' controls now take each leg's plan for which omissions to expand. dw2, apart and twin expand what S2
forced, as before. DW5's only omission is forced by S3's search, which S2's rows do not carry, so its plan expands every
omission of its own.

## A design-defect candidate: an occasion only the search finds cannot be decided

**What happens and why.**
- An expansion window is cut by `views.expand` with `cut_windows(..., overlap=False)`. It shows only the omitted middle
  of the clipped record, with no records around it.
- A reader of that expansion who finds an occasion there cannot see the exposure rule being met before it (here, the
  guide's read). It cannot see the behaviour after it either (here, the report). The honest judgement of its exposure is
  exposure_unknown.
- `settle_occasions` (W r1 B2, D-20261104-a9e2d2): when a window and its expansion judge the same occasion, the
  expansion's verdict stands. If their exposures differ, the instance is exposure_unknown.
- Under §11, an exposure_unknown occasion can never make an observation observed or not observed; it only keeps it
  from being observed. An observation whose only occasions are such stays pending.

So an occasion that only the search finds stays pending unless another, eligible occasion decides the observation.
Yet finding occasions in a clipped middle is the reason the search exists.

**How it came out.** In the golden run, T-1 is pending with one exposure_unknown occasion and no eligible one. The live
leg had not run when this record was written; its result record states what the live reader judged and what code
derived.

**Fix candidates.** Neither is chosen here. The lead keeps the item in the backlog and asks the owner when to take it
up.
1. Give an expansion window, as overlap, the original window's records around the clipped record, so that its reader
   sees the exposure and the behaviour.
2. A rule that combines the expansion's occasion with the original window's exposure judgement.
