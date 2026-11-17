---
created_at: 2026-10-21T09:38:00+09:00
head: ebca5ee
kind: design
supersedes: 2026-10-21T0820--9b42df2--plan-addendum-wp13.md
---

# Session distill implementation plan: correction to the WP-13 addendum

The addendum this record supersedes
(`2026-10-21T0820--9b42df2--plan-addendum-wp13.md`) named the properties schema 2 carries
beyond design §12.1, their readers and their reasons. Round 3 of the WP-13 review found five
defects in the code it describes, and three of them land on its text: one consumer it names does
not exist, one placement rule it states is narrower than design §12.2, and its reading of the
delivery event licensed a shape the event does not have. The addendum is a dated record, so it
is not edited; this record carries the corrections. Everything the addendum says that is not
corrected below still stands.

## 1. `legacy_placed`: the reader, and where it may sit

**Reader.** The addendum's table names `migrate-ledger.py` and `ledger_compat.py`. Only the
first reads it: `migrate-ledger.py` line 244 accepts a schema 1 `placed` value as preserved when
it equals an element's `at` **or** its `legacy_placed`, which is what design §12.2's
value-preservation rule needs. `ledger_compat.placed_entries()` derives its projection from the
entry's `destination` and the latest place decision's `applied`, and never reads `legacy_placed`.
The corrected consumer list is `migrate-ledger.py` alone.

**Placement.** The addendum's table said "legacy applications only". That is narrower than design
§12.2, which attaches `placed` to the **latest place decision** and uses a separate
`legacy_application` element only when the entry has no place decision (measured: G-5, G-8). The
migration therefore writes `legacy_placed` onto an ordinary migrated `decision1` element that
carries the application. The rule the code now enforces (`LEGACY_PLACED_MISPLACED`) is the one
that follows from §12.2: **`legacy_placed` belongs on a legacy element that itself carries an
application**, and never on an element that records none — an unapplied legacy decision, a
historical retirement, or the migration element.

## 2. The delivery event records an outcome; it does not append a decision

The addendum's §3 reading — an application stands whatever its delivery check found — is
unchanged and remains the contract. What was wrong was the shape the event took: the code
appended a second decision and replayed its disposition through design §12.3's table, so
recording a failed delivery for an already placed entry attempted `placed + place` and a second
decision of the same run duplicated the run.

Design §12.3's row is "any applied decision | delivery failed or unverified | unchanged;
`decisions[].applied.delivery` records it". The event therefore names the **run whose decision was
applied** and the outcome, and writes that outcome into that decision's `applied.delivery`.
Nothing else moves: no transition is replayed, no decision is appended, and the entry's fields
stand as the application left them.

One consequence for the append-only rule of design §12.1 ("nothing overwrites an earlier
decision"): a decision now has **two** fields a later window still writes — the resolutions of its
expected observation (design §11) and this delivery outcome. `row_violations` admits exactly those
two and refuses every other change to a recorded decision (`DECISION_REWRITTEN`).

## 3. An element of the migration is written by the migration

The addendum's §1 separated the two shapes of a `decisions[]` element but said nothing about how
each **enters** the ledger. A legacy element carries no approval row (`approval_id` is `legacy` or
`unavailable`, which `DECISION_UNAPPROVED` exists to refuse on a run's decision), so one appended
during an ordinary run would license row changes that no approval stands behind.

A legacy element enters a ledger only through the migration of the schema 1 file, which
`check_pair` judges by equality with `migrate-ledger.migrate()`. Between two schema 2 ledgers, an
appended legacy element is refused (`LEGACY_ELEMENT_APPENDED`) and licenses nothing.

## 4. A revert puts back what the application it undoes changed

The addendum's §3 gave each disposition its own licence. A revert has no disposition of its own —
it is an applied decision with disposition `none` — so that rule left it able to restore nothing
but a retirement or an absorption, and the text a correction revised, the destination a
re-delivery changed, and the keep record a keep installed stayed behind after their application
was reverted.

A revert's licence is therefore **the licence of the application it undoes** (`revert_licence`),
widened by the retirement and absorption fields a revival releases. Nothing else: a revert undoes
one application, it is not an occasion to edit the entry.

## 5. The allocation on the command line

Design §12.4's check needs to tell a run that froze **no** new id from the absence of a run. The
`--allocated` flag is therefore read as: omitted → no allocation (`ALLOCATION_REQUIRED` for a
schema 2 transaction); passed empty → the allocation of a run that froze no id; otherwise the ids
it names. A correction or a resolution writes the ledger without adding a row, and that is the
case the empty allocation exists for.
