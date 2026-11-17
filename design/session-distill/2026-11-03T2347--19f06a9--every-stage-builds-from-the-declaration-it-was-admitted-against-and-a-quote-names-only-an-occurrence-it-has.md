---
created_at: 2026-11-03T23:47:00+09:00
head: 19f06a9
kind: review
supersedes: null
---

# Every stage builds from the declaration it was admitted against, and a quote names only an occurrence it has

The X review of WP-08, round 2 (on e6cb055), returned rework with one major finding and one minor. The X set closed at
its cap of two rounds (D-20261103-d0a4af). The lead verifies this fix on a pinned clone, and the W review of commits 2
to 5 reads it again. Both findings were reproduced on 19f06a9 before the change
(`work/impl/wp08/logs/x2fix-repro-3.log`, author-side).

## 1. S1 read its declaration before admission

**Finding.** `census.run` read run.json, then built the census from that read inside `records.run_stage`. An amendment
of `window.end` landing between the two produced a census for the old window under an S1 record of the new
declaration.

**Reproduced.** The census window was `2026-10-01T00:00:00/2026-10-08T00:00:00@UTC`. run.json's window ended
2026-10-09. Both S1's record and run.json were at `declaration_seq` 1.

**Every stage, not one.** The fix of round 1 moved S2's views and S3 onto the declaration their stage was admitted
against; this round finds the same shape in S1. The call sites of `records.run_stage` and the reads of run.json were
therefore listed again, from the code:

```
grep -n "run_stage(" session-distill/distill.py session-distill/runlib/*.py
grep -n "run_json_path(" session-distill/distill.py session-distill/runlib/*.py
```

Outside the self-tests and their fixtures, four production stages enter `run_stage`:

| Stage | Where | Before this commit | Now |
| --- | --- | --- | --- |
| S1 | `census.run` | read before admission, used to build | read before admission so a stale pin or table is refused before any record is written; `StageRun.admitted` refuses it unless it is byte-for-byte the admitted declaration (DECLARATION_MOVED) |
| S2 views | `views.run` | fixed in e6cb055 | `stage.declaration` |
| S2 inventory | `distill.cmd_inventory` | re-read run.json inside the stage, which an amendment after admission could change | `stage.declaration` |
| S3 | `stage_read.run` | fixed in e6cb055 | `stage.declaration` |

`census.build` takes the declaration it is handed. The dispatcher reads the declaration under its own lock for each
call and records the sequence it read; that is admission per call, not a read before a stage, and is unchanged.

**One fixture, two cases, every stage.** `records.fx_amended_at_admission(stage, assignments, when)` makes an
amendment land just before (`before`) or just after (`after`) a stage's admission. Those are the two places a stage
that reads the declaration on its own can be overtaken. Each stage's self-test runs both cases:

- **S1** (census):
  - before: refused DECLARATION_MOVED, and no census is written;
  - after: the census keeps its window, and S1 records sequence 0 while run.json is at 1.
- **S2 views** (views):
  - before: the windows and the views record the amended cap, under S2's sequence 1;
  - after: they keep the admitted cap, under S2's sequence 0.
- **S2 inventory** (distill):
  - both cases: the declaration the inventory part takes is the one its record names.
- **S3** (stage_read):
  - both cases: the reading's `declaration_seq` is S3's recorded one, 1 before and 0 after.

## 2. An occurrence the quote does not have

**Finding.** A quote that occurs once, answered with `occurrence: 1`, passed the schema and `answer_problems`. Then
`evidence.from_view` indexed past its spans with an IndexError, and the whole unit was quarantined.

**Reproduced.** `IndexError('list index out of range')`.

**Change.** `evidence.nth` resolves the occurrence for both `from_view` and `from_quote`. An occurrence that is not one
of the spans found (past the end, or negative) is refused as QUOTE_OCCURRENCE_UNKNOWN. In S3 that refusal drops the
claims resting on the quote, by that code, and the unit reads on.

**Controls.**
- evidence: occurrences 1 and -1 of a quote found once, through both readers.
- stage_read: the Codex window's claim on such a quote is dropped by name, and its unit is still read_complete.

## The defect commit 2b's first condition guarded against, reproduced

Before 19f06a9, a judge-failed attempt's claims were not stored. The supervisor returned `accepted: None` for an item
whose attempts the stage's check failed, and the reader read only an accepted item. But `gate.accepted` on such an
attempt's directory returned its answer: the read path existed and nothing used it. On 19f06a9 it is refused
(STAGE_CHECK_FAILED). The probe ran on 4e08e5f, e6cb055 and 19f06a9 (`work/impl/wp08/logs/x2fix-repro-c1-1.log`).
