---
created_at: 2026-10-23T12:10:00+09:00
head: 2a61d6b
kind: design
supersedes: null
---

# S2 has two producers, so its one record holds one part each

S2 produces two things: the reading views of the captured transcripts (`views.json`) and the
inventory of the effective library (`inventory/*.json`, design §6.1). `records.run_stage` wrote one
record per stage — `stages/<stage>/record.json`, written at the start and overwritten at the end —
and `views` already owned S2's. A second caller would have replaced it, with no merge and no
refusal, so one record could not hold two producers.

## The decision

A stage may declare **parts**, one per producer, in `STAGE_PARTS` beside `STAGES` in
`session-distill/runlib/records.py`. Today `S2 = ("views", "inventory")` and no other stage declares
any.

- The record is still one file under one stage lock. `run_stage(..., part=...)` reads the record,
  replaces its own part's entry — status, inputs, outputs, declaration pin — and leaves every other
  part's entry exactly as found.
- Each part has its own status. The stage's status is **derived** on every write (complete only when
  every declared part is complete, failed when any part failed, running while any part runs,
  partial otherwise), and is never written by a producer. No producer can declare a stage complete
  on another's behalf.
- A downstream input resolves to the **part that produced the artifact** and is judged against that
  part's status and declaration pin. An S3 input on `views.json` is admitted when the views part is
  complete even if the inventory part failed, and refused when the views part is partial or failed.
  The refusal names the part (`INPUT_PARTIAL S2.views`).
- A part name the table does not declare is refused by name (`STAGE_PART_UNKNOWN`), including for a
  stage that declares no parts at all.
- A stage with no declared parts keeps today's record shape byte for byte, and its readers do not
  change. Records written before this change, single-shape S2 records included, still read:
  a record with no `parts` answers for itself, both for its status and for the artifacts it
  produced. No migration is needed, and none is written.
- An inspection-mode inventory (`--native-live`) writes no stage record at all: it is not a result.

## What this closes

**Option 1 — run the inventory inside the views stage.** Rejected. It needs no new machinery, but it
makes every inventory rerun cost a views rebuild: views took about twenty minutes on the owner's
real data on 2026-10-22. It also couples two producers that have no reason to know about each
other, and makes the dependency direction views → inventory permanent.

**Option 3 — give the inventory a stage id of its own (S2b).** Rejected. It is the smallest code
change, but design §6.1 places the inventory in S2, so the stage table and the design would
disagree, and every reader that reasons about stages would carry that disagreement.

## Why this shape and not a looser one

The alternative inside option 2 was to let any caller add any key to a stage record. A declared
table is what makes the derived status decidable: without the list of parts a stage is complete
whenever the parts that happen to have run are complete, which is the failure the derivation exists
to prevent. The table is also what makes an undeclared part refusable rather than silently written.

The change is deliberately small because `records.py` is shared: one constant, one optional
argument, two helper functions (`producing_part`, `derived_status`), and the part-aware branch in
the input check. Integration will rebase it with other branches.

## Controls

In `records.py --self-test`, each failing by name when its rule is reverted: the second part does
not clobber the first; a part rerun replaces only its own entry; the stage status is derived rather
than written; a downstream input is admitted by its producing part, refused when that part failed
or is partial, and refused when no part produced the artifact; an undeclared part is refused, for a
stage with parts and for one without; and a record written before parts existed still reads and
still answers for its own output.
