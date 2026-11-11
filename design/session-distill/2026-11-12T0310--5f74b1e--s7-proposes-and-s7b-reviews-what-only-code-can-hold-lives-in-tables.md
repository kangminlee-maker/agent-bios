---
created_at: 2026-11-12T03:10:00+09:00
head: 5f74b1e
kind: design
supersedes: 2026-11-11T2210--62ccccb--the-gate-refuses-each-of-ten-defects-planted-on-copies-of-an-accepted-judge-call.md
---

# WP-12: S7 proposes, S7b reviews, and what only code can hold lives in tables

Lane L's WP-12, from `33c873a` (lane E's S6, merged at `7adff24`) to `5f74b1e`. Nine commits. This
record states what the code at `5f74b1e` does and why the judgement calls fell as they did; it is
not a status page, and every figure in it is re-derivable from the artifact it names.

## What the stage is

S7 receives, per candidate, the kind and the diagnosis S6 derived and answers with a disposition, a
destination, operations and its reasons. S7b reviews that answer. Neither decides anything the
tables decide: the allowed `(kind, diagnosis) -> disposition` pairs
(`tables/allowed_pairs.json`), the structural rules (`tables/structural_rules.json`), the placement
rules (`tables/placement_rules.json`) and the report's total order (`tables/ranking.json`) are data,
read by `runlib/placement.py` and `runlib/ranking.py`, because a vocabulary written twice is two
authorities. The schemas hold SHAPE only: `propose.schema.json` makes `disposition` an enum and says
nothing about which disposition this candidate may have.

## The two readings of §9 that the design does not settle

`tables/ranking.json`'s group `quarantined_or_failed` had no member for `{status: returned}` or
`{status: failed}`. The consequence was not a gap but a wrong answer: the second pass places by
KIND, so a returned proposal of kind `already resolved` went to the resolved group, and a returned
row whose kind is `gap` matched no group at all and was REFUSED by the ranking.

- **`failed`** rests on §9's own population sentence, "every quarantined or failed item". Direct.
- **`returned`** rests on that sentence read one step further. §10.4 says an ineligible item is
  RETURNED with the failing condition named, and §9's population has no other place to put it. This
  is a reading, not a quotation, and it is written in the group's `$comment` as such.
- **`untested` in the first group** rests on RELEASE 1, not on §9. S8 is deferred
  (D-818391), so no row can be `tested`, and an untested row here is a proposed row whose test stage
  does not run - not a row offered for testing and skipped. §9's sentence does not name `untested`.
  The condition to revisit is written beside it: when S8 lands, an untested row means something §9
  has not placed, and this entry must be re-read rather than inherited.

The report's label is separate from the placement. `ranking.row_label` prints
`proposed (untested: s8_deferred)` for the statuses `test_state_label` lists, and `ranked` carries it
as `status_label` beside an untouched `status`. A label never decides a group.

## The legacy-maintenance row

The owner decided the 142 `incubating` ledger entries (D-20261111-e53a01): the default is `none`, so
items at `none` stay in the intake and no call is spent on them; the 24 entries that still carry a
classification block are shown as individual rows, and the other 118 in three groups by the kind of
their `decision1`. Expiry is moot under a `none` default. `stage_propose.decision1_kind` is the
function that reads that kind, and lane E uses the same one rather than its own first-word split.

## Three defects, each a check that could not fire

Found by the lead and by lane E on the merged tree, and each one had a control that agreed with the
bug:

1. **Fail-open validation.** The validator fell back to accepting everything when jsonschema was
   absent. It now goes through `runlib/validate.py` (`compile_schema` + `validate_instance`) with no
   fallback. That exposed the schema policy: `SUPPORTED_KEYWORDS` forbids `oneOf`, so nullables are
   `"type": ["x", "null"]` or a `$defs` twin.
2. **A blanket copy.** The flat proposal was built by copying the answer and updating it, so a field
   the contract never named rode through. It is built from an explicit field list now
   (`FROM_ANSWER`, `FROM_PLACEMENT_CLAIMS`, `DERIVED_INTO_PROPOSAL`), and `proposal_of` refuses an
   answer field no list names.
3. **`outcome["promotion"]["eligible"]`.** S6 writes `outcome["eligible"]["eligible"]`; the section
   `promotion` never existed. My own fixtures built the same wrong key, so the fixture library
   AGREED with the bug - fixing the reader made a frozen fixture start failing, which is how the
   agreement became visible.

Then B4, found by lane E by RUNNING the stage: `run` passed a bare `proposals.json` to
`records.write_json`, which confines its path beneath the run, so it resolved against the process's
working directory and raised `RUN_PATH_ESCAPE` before anything was written; and the file was never
registered with `stage.output`, so S7b's staleness check had nothing to compare. Both stages had
both defects. Every existing control called `document`, the pure half, so the stage's plumbing had
never run.

## The WP-20 interface

- `regeneration_packet` / `regenerated_problems` / `regenerate_reasons`: S9b's single retry, which
  may rewrite the six reason fields §7.3 names and nothing else. Every other field, and the set of
  fields itself, must be identical; a retry that returns the same Korean is refused as having
  regenerated nothing; the result goes back through `answer_problems`. Without that boundary a retry
  could return a different disposition and be a new proposal wearing an old proposal's provenance.
- `only=` on `document` and `run`, both stages, with `subset` recorded in the document. An id the run
  does not hold is refused by name and an empty subset is refused: a subset quietly narrowed to the
  ids that exist would report "every candidate answered" over a smaller population than the caller
  believes in. S7b calls `stage_propose.subset_problems` rather than asking the question again.
- `item_id` is S4's candidate id. There is no `item_sha` anywhere in `session-distill/`; a proposal
  digest, if WP-20 needs one, is WP-20's to define, and the narrow basis (disposition, operations,
  destination, claims) is the one that matches what regeneration is allowed to move.

## Control lessons this work paid for

Each of these cost a revert trial that found a control agreeing with a bug.

- **A key control whose expected order coincides with the id order passes under revert.** Every
  per-key ranking control now orders its ids AGAINST the answer it wants, so the key is what decides.
- **`control(name, got, want)` matches by containment, and a word is a substring of a longer string
  that starts with it.** `"rejected"` is inside `"rejected (untested: s8_deferred)"`, `"bounded"`
  inside `"unbounded"`. Three defects on this branch hid there. Compare by equality when the
  expected value is a prefix of the wrong answer.
- **A control that dies is not a control.** A refusal from a different exception family
  (`stagelock.Escaped`, not `Refused`), a record a refused stage never wrote, a field a mutation
  removed and the control indexed positionally - each killed the suite before any control spoke, and
  the trial reads a traceback instead of a named failure.
- **A row that mutates near its subject is not a negative control for it.** Two rows mutated the
  sentence beside the one the control reads.
- **Assert the subject set is non-empty.** A mutation that emptied the document passed two controls
  that compared the document with itself.
- **A control satisfied by something other than its subject.** Script controls read the file's own
  comments; a prose control read the word `jsonschema` out of its own docstring.

## Two mechanics that cost a real attempt

- **`git stash` drops `MERGE_HEAD`.** Stashing to inspect something during a merge resolution loses
  the merge state. Save the work by hand (`git checkout --` the one file), or diagnose in a separate
  clone.
- **A suite that runs a computed program is refused by `runlib/dispatch.py`** until the site is
  declared in `SCRIPT_RUNS` with what makes it true - here, that both commands refuse
  `CALL_NOT_WIRED` without their files and so start no model. A declaration, not an exemption.

## Where to re-derive the numbers

Suites: `python3 session-distill/runlib/<name>.py --self-test` for `stage_propose`,
`stage_review_proposals`, `ranking`, `sequencing`, `placement`. The umbrella is
`./gates/check-parity.sh`. Counts stated in any earlier record are claims about an earlier tree.
