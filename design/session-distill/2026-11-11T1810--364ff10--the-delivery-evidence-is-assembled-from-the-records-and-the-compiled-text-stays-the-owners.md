---
created_at: 2026-11-11T18:10:00+09:00
head: 364ff10
kind: design
supersedes:
---

# WP-11b — the producer of delivery evidence (lane L)

S5b (`session-distill/runlib/stage_delivery.py`, `distill.py deliver`) assembles, from the records a
run already holds, the input `runlib/delivery_evidence.delivery()` takes, calls it per owed pair, and
writes `delivery-evidence.json`. This record is the package's one dated record. Numbers in it are
claims about the tree at `364ff10`; re-derive them from the artifacts before acting on any of them.

## What it reads, and the rule each source obeys

Three sources, each with its own absence rule, because a key one of them cannot fill must read as
"this run cannot say" rather than "there was nothing".

1. **The inventory** answers selection, the events and the release.
2. **S2's published facts** answer what the session was GIVEN: the snapshot's items with the surface
   each was selected at, the compiled instruction text's sha256, and per unit how many of its
   operative-context lines that text held, as counts.
3. **The run's immutable copy** answers what the session READ.

A key no source can fill is absent, never empty. An empty `reads` is the claim that the session read
nothing; a missing one is the truth that this run cannot say.

## The compiled text is answered as counts (D-20261111-d05b16)

The lead's boundary decision, in its fact-only form: the acquisition boundary stays at S2, and the
compiled instruction text never enters a run. The only question §6.3 asks of that text is whether it
holds a unit's operative-context lines, and a count answers it. So the comparison happens at S2,
where the snapshot is readable, and a selection inventory publishes `{covered, total}` per unit
reference beside the text's digest.

`delivery_evidence.delivery()` gained an optional `instruction_coverage` input and one reader,
`in_compiled_text`, which prefers the facts and falls back to a fixture's `instruction_text`. A
session with neither reads `unknown` by `compiled_text_unavailable`, never `not_delivered`.

**The digest is published once per document, not per unit.** The brief's fact shape was
`{covered, total, text_sha256}` per unit, and a session has one compiled text, so a per-unit digest
would be the same value repeated — the restatement this repo's authority rule forbids. The judge's
reader asks only for the counts, so the behaviour is identical. (Deviation accepted by the lead.)

**The prefix rule is asymmetric by side, and the revert discipline is what established that.** A
unit's line is the file's own bytes and is compared as written; a line of the compiled text is held
both as written and with a reading tool's line-number prefix removed. The first rule written here
stripped a text only when every one of its lines carried a number, and reverting that condition
changed no answer the suite asked about — a row that passes under revert is a finding, and the
finding was that the guarded property was the wrong one. Normalizing both sides makes `1<TAB>foo` and
`2<TAB>foo` the same line; normalizing the text conditionally makes the two sides disagree about what
a line is whenever the text is a mixture.

## A reference that resolves to nothing is a failure, not a dropped row (D-20261111-682fdf)

The counts are keyed by the inventory's `r-` reference and the judge asks about a `unit_id`.
`coverage_facts` returns the references it cannot resolve instead of dropping them: a block whose
every row failed would otherwise read exactly like a session whose inventory published no block, and
that difference decides between `compiled_text_unavailable` and a failure this run caused itself.
Every pair of such a session whose unit the block does not answer for names
`coverage_ref_unresolved`, the document counts them per session and in total, and the state stays
`unknown` — a fact that failed to resolve is not evidence that the text lacked the unit's lines.

## The ladder is the session's, not the unit's (D-20261111-647b5c)

§6.3 judges a unit on the ladder of the surface its item was selected at, and that is a fact about
one session: two sessions can hold the same unit at different surfaces, and the native layers are
judged by layer with no surface at all. The surface is therefore attached per pair from the session's
own selection. A session that states none leaves the judge to answer `surface_unclassified`.

## The §6.3 fixture library, at the records level

`session-distill/tables/stage_delivery_fixtures.json` holds one frozen fixture per state path this
stage can write, each a whole set of run-shaped artifacts driven through `document`, written once by
`stage_delivery.py --generate-fixtures`. W2 froze the judge's fixtures per table row; these are the
same states reached the long way, which is the only way to test an assembly rather than the judge.
`derive.coverage_problems` holds the three sets as one bijection.

The library earned itself immediately: **`injection_at` was never assembled**, so every
always-surface unit stopped at `selected` whatever the coverage facts said. It is now the first
recorded session injection on the record-ordinal scale.

Two state paths are declared unreachable with their reasons rather than faked (D-20261111-5a79c5):

- `exposed_not_read` needs a level between selection and a read of the unit's bytes, which exists
  only on the guide surfaces, whose `pointer exposed` asks whether the compiled text holds the item's
  emitted path. That is a predicate over the text, and S2 publishes counts.
- the catalogue route to `not_delivered` needs the ladder of an item the session was NOT given, while
  surfaces are published only for the items it was. The same state is reached honestly through the
  native layer (`not_in_recorded_injection`).

Both are the same boundary question the coverage counts were, and both are raised with the lead
rather than closed here. So is the installer surface: `installer_exposure` is called with the inputs
as they are, which is none of them, because the installation binding is a verdict over the owner's
state root and S2 publishes no part of it. The row is `unknown: unbound` with the absent producer
named.

## Names that must not merge

`delivery_assembly_pending` is this stage's per-pair state INSIDE a file that exists.
`delivery_assembly_waiting` is S6's state when no such file exists at all. One says the evidence was
assembled and answered nothing for this pair; the other says nobody assembled any.

## Traps this package paid for

- **A control that only ever saw the fixture its author drew passed over a shape the schema never
  had.** The first commit read `session_ref`, `unit_ids` and `decision_at` off a check row — fields no
  producer writes — and its controls passed because they judged that invented shape and no real file.
  Re-anchored on `checks.schema.json`, S4's `candidates.json` and an event record's `at_record`.
- **A control that dies before printing its failure is not a control.** Four of them here:
  `evidence["pin_reason"]`, `codex_reads[0]`, `with_reads["unparsed"]`, and `doc["pending_reason"]`
  compared against `None`. Every control compares an absence value or uses a guarded index.
- **A handler nothing dispatches to is a command that reports itself unimplemented.** `cmd_deliver`
  sat in `distill.py` unreachable for seven commits while the suite ASSERTED the
  `STAGE_NOT_IMPLEMENTED` answer, because `deliver` was absent from the implemented list. Found by
  running S5b on a real run. The dispatch is now one table held against the `cmd_` functions in both
  directions.
- **`inventory.checkout_copy` copies git-tracked files only**, so a new module fails
  `distill.py --self-test` until `git add`. `AGENTS.md` forbids `git add -N` before a commit.
- **A `$comment-` key beside a schema's properties is read by the emission as a declared field** and
  refused by name. The prose goes inside each property.
- **A loop variable named like the suite's own local rebinds it** for every line after the block; this
  suite's `fixture` is its run directory.
- **A revert of an assertion cannot fail.** One harness row was dropped rather than counted: the
  bijection's negative control is a planted state path, not the removal of its own check.

## Measured on the lead's C2 run (2026-11-11, clone at `/tmp/l11b/c2/run`, counts only)

| what | count |
| --- | --- |
| sessions in the inventory | 67,893 |
| sessions with a read pin | 39 |
| of those, with a selection inventory | 0 |
| pairs S5b owes | 24,962 |
| of those, with a decision ordinal | 436 |
| current units | 26,855 |
| current units whose own text this run cannot see (redacted) | 14,116 |
| current units carrying lane E's `edges` | 0 |

The 39 pinned sessions all record `selection.status = unknown / input_failed`, so every pin-based
surface reads `unknown` for a recorded input failure whatever else is assembled — a **C2
OBSERVATION**, not yet a finding; it becomes one only if it persists after S2 is re-run. The native
layer holds 7,300 events and no `session_injection` producer ran. The redaction share is a **C3
fact** the owner should see beside the budget: more than half the current units cannot be judged on
their own lines, and such a pair is answered `unit_text_redacted` rather than compared against the
placeholder.

**Done-when 3 is not finished.** S5b refuses on this clone by name —
`DELIVERY_EDGES_ABSENT 26855 current unit(s) carry no edges` — because the clone's inventory predates
lane E's export. The measurement needs S2 re-run on the clone, which is an acquisition the boundary
reserves for S2 and this lane does not perform; the frozen inputs are a temporary directory and are
not in the run.

## Harnesses (outside the repo, `work/impl/`)

`pretrial-wp11b-c1.py` … `-c9.py`. c1–c5 carry no real-home canary — the constraint was missed. The
canary was **absent when c6 began and nothing deletes it**, so c1–c5 provably left nothing at the
protected path; every harness from c6 on carries it, and every run has reported it absent before and
after.
