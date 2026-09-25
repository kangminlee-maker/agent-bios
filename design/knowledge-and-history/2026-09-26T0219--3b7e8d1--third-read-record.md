---
created_at: 2026-09-26T02:19:00+09:00
head: 3b7e8d1
kind: review
status: review-fixes-read-a-third-time-by-two-reviewers-fixed-p00-accepted-p01-stale-no-stage-implemented
plan: 2026-09-25T1636--6fa562f--development-plan.json
supersedes: 2026-09-25T1722--9d6eef4--recheck-record.md
decisions: D-20260926-8dfbf0, D-20260926-78c4f5, D-20260926-19a53d
---

# The review fixes, read a third time by two reviewers

The [re-check record](2026-09-25T1722--9d6eef4--recheck-record.md) fixed the six defects the
second read found, in commit `3b7e8d1`. The owner asked for a third read of those fixes by two
reviewers of different providers, each working through its own Ultracode orchestration. This
record carries both reads, what each found, and what was changed. The bundle members stamped
`2026-09-25T1636--6fa562f--` are unchanged; the fixes are in `gates/workenv/` and in
`CURRENT.md`.

## The two reads

Both read the same blind tree: an archive of `3b7e8d1`, the versions before it and the whole
change under `before/`, both earlier review results under `prior/`, and `run-7`. The rationale
ledger and the repository's working rules were withheld; the re-check record was included as
claims to test. Everything is in
`~/.local/share/agent-bios-workbench/team-env-20260920/review-stage-bundle-20260925-r4/`.

- **Codex** — provider `openai`, model `gpt-6-astra`, effort `ultra`, through the
  `$ultracode-for-codex` skill, from 18:03 to 18:23. Its Codex home held only the login and the
  two Ultracode skills, and writes were confined to the review directory; the login copy is
  removed after each run. It reports that the Ultracode CLI runtime 0.7.1 executed two
  schema-enforced phases, Inspect and adversarial Verify, of three agents each at `high`, with
  no fallback to native subagents. The tree's checksums are unchanged after the run.
- **Claude Fable 5.1 at `max`** — an Ultracode workflow: fifteen check agents (one per earlier
  finding re-checked, one per pressure lens), three skeptics trying to refute each finding, two
  trying to overturn each "resolved" judgement, a completeness critic and its three follow-up
  checks. Session limits interrupted it twice; it was resumed from its journal each time, and
  186 of its 188 agents finished. The synthesis agent did not, so the tallies below are computed
  from the journal, which is preserved with the workflow script under `fable/`.

| Earlier finding | Codex | Fable |
| --- | --- | --- |
| documents N01 | resolved | resolved |
| machinery N1 | resolved | resolved |
| machinery N2 | resolved | resolved, overturned by both skeptics: a coroutine or generator test still passed |
| machinery N3 | resolved | partly resolved |
| machinery N4 | resolved | resolved |
| machinery N5 | resolved | resolved, overturned by both skeptics: the report could still drop bound cases |
| machinery F2 | resolved | resolved |
| machinery F5 | resolved | partly resolved |

Codex reported three new findings, each verified before it reported them. Fable's agents
reported 52, counting the same defect found by several agents; 50 survived their skeptics.

## What was found and changed

Each was reproduced in the tree before it was fixed.

| Area | Found by | Fix |
| --- | --- | --- |
| A rule credited without its oracle's record being written by the contract's code | Codex R2; Fable (the N3 and F5 re-checks, the rule-credit lens) | A rule counts only where a profile binding its case serves a step that is an operation of the rule's contract, handles a record of the kind its oracle judges, expects no refusal another contract states, and does not address an earlier request (`D-20260926-8dfbf0`). All 22 current rule and case pairs keep a credited profile |
| A case reported `passed` though its assertion never ran | Codex R1; Fable | A generator test, a coroutine its TestCase never awaits, a method that is not a test, an unexpected success, and a method-less case each report `failed`; the driver refuses to run under `python -O` |
| What the driver reports and how it exits | Fable | The command exits 0 only when every case passed (`D-20260926-78c4f5`); a class that cannot be set up fails with its cause; a module that cannot be imported, or skips itself, fails every case with the cause and the report still holds every bound case; a module's own set-up runs; the stated cause is the exception's line; a profile whose cases of a family are bootstrap commands is refused with that reason |
| The driver-equivalence comparison | Codex R3; Fable | Every open profile is asked about every catalog family, with a refusal expected where it binds none or only bootstrap cases; its controls now catch a driver that answers for an unbound family, one that drops some atomic cases, and a report that drops bound cases |
| The serving table | Fable | A layer with no name, a layer or addressed row with no node, and a refusal one layer states twice are named instead of crashing or being reported twice; a selection for a profile no plan node is tested by is refused |
| Documents | Fable | `CURRENT.md` counts P00's and P01's known-opposite controls as rejected ones plus the accepted untouched copy; the drift tool and `cases.py` state their rules without a count that had gone stale |

## Not adopted, and corrections

- **Carrying an accepted implementation stage's binding.** One Fable agent argued that editing
  shared machinery during V2 would strand an accepted V1 unless its binding could be carried;
  its six skeptics split three to three. Deferred to V1's acceptance (`D-20260926-19a53d`): the
  discharge rule keeps V1 current when V2 records.
- **Refuted:** that a layer's own code should earn rule credit (three of three skeptics), and
  that `CURRENT.md` still sends a reader to superseded rule sentences (two of three): the dated
  records keep the wording true on their day, and `CURRENT.md` points to the newest record,
  which states the current rule.
- **Record heads.** A record's `head` is the commit it was written on, so its counts describe
  the commit that carries it: the re-check record's test counts are those of `3b7e8d1`.
- **Corrections to dated records**, which are not edited: the re-check record credited the
  documents pass of the second read with upholding the rejection of machinery F4; it was the
  machinery pass. The why of `D-20260925-90ecdf` says the second read's construction kept C05 at
  V2; it removed C05 from V2 and gained credit through V6. `D-20260926-8dfbf0` states the
  correction.

## Controls

Each fix was reverted in a copy of the tree, one at a time, and its test was required to fail by
name: the six Codex fixes and sixteen Fable fixes all did. One revert first survived, the
journal-answered credit, because the kind filter already refused the construction the test
used; the test now makes the queries handle the judged record, so only their exclusion refuses
the rule, and the faithful revert fails it. Fable's strongest overturning construction, a
family-prefix filter inside the driver's run that silently drops every atomic case, is caught by
the report test at R0 and at V1's N27. `gates/workenv/test_driver.py` runs 40 tests (24 at
`3b7e8d1`) and `gates/workenv/test_cases.py` 80 (74); the workspace gate passes its unit tests and
static analysis, every profile's binding holds (`CASES OK`), and the plan gate passes with 33
positive and 442 negative controls. The evaluator still reads `run-7` as accepted `[P00]`, ready
`[P01]`.

## Not done

- **These fixes have not been read by a reviewer.** Whether to read them again is the owner's
  call.
- **P01 re-freezes** over the regrouped registry once V1's cases can be run.
- **V1** is next: the family modules its cases need, then V1 implemented, used here and tested.
