---
created_at: 2026-10-21T12:10:00+09:00
head: f7ec815
kind: design
supersedes: 2026-10-21T1133--9dd50bd--plan-addendum-wp13-correction-3.md
---

# An application records the values it replaced, and a revert puts exactly those back

Owner decision of 2026-10-21. It amends design §12.1 of
`2026-10-20T1942--9684f05--mechanism-design.md` and replaces the conservative-revert rule of the
record it supersedes. The plan, `2026-10-21T0820--9b42df2--plan-addendum-wp13.md`, and everything
else in the superseded record's earlier corrections stand. This record is the contract for
`session-distill/runlib/ledger.py` and `session-distill/schemas/ledger.schema.json` on schema 2's
revert; `record_problems` holds it against the module.

## The rule

A decision's `applied` record gains one property:

- **`applied.before`** — for every row field this application changed, the value the row held
  immediately before it. It is an object of two parts: `fields`, the values the row held, keyed by
  field name, and `absent`, the names of the fields the row held no value in (an absent property
  and a null are the same answer, and both differ from a value). The two parts never name the same
  field. The fields it may name are exactly the fields a disposition licenses, which is what
  `contract_problems` asserts against `DISPOSITION_FIELDS`.

The eight top-level keys of a decision (design §12.1) are unchanged, and `applied`'s four required
keys are unchanged: `before` is an optional property of `applied`, written by every application
this code makes and absent from every element design §12.2 migrated.

**A revert restores exactly that record**, plus the status the entry's own history derives
(design §12.3's revert row, unchanged). It restores a value where `fields` holds one and leaves the
field without a value where `absent` names it. It accepts no value from its caller
(`REVERT_VALUE_SUPPLIED`).

**It is refused by name, `REVERT_INVERSE_UNPROVABLE <entry> <field or property>`, when:**

- the application it undoes carries no `before` — an element design §12.2 migrated, or a row
  written by hand. Its status can be reverted and its fields cannot, so the whole revert is
  refused rather than half applied;
- a decision still standing changed the same field after the one being reverted — revert that one
  first. On one row this cannot arise: a revert undoes the latest standing decision and each
  earlier one is still covered by its own record, so the order is last in, first out. The one place
  two rows are involved is a merge, where the receiving entry's own history can move on after the
  merge it received, and `merge_receiver` is where that is checked;
- a merge's receiver holds no decision carrying that merge's own operation
  (`operation_id`), so there is nothing of the merge on that row to put back.

A merge writes `before` on both rows — the absorbed entry's own decision and the decision it
writes on the receiver — and its revert restores both or neither. A transaction's appended revert
is held against both rows the same way (`RECEIVER_REVERT_MISSING`, `REVERT_NOT_RESTORED`).

The transaction side (design §12.4) checks the record rather than trusting it: the appended
decision's `before` must equal the base row's values for exactly the fields the row change touched.
A field the change touched and the record does not name is `BEFORE_FIELD_MISSING`, one the record
names and the change did not touch is `BEFORE_FIELD_EXTRA`, and a value that is not what the row
held is `BEFORE_FIELD_WRONG`. A row that did not exist replaced nothing, so a creating decision's
record names no field.

**One applied decision per row per transaction** (`TRANSACTION_MULTIPLE_APPLICATIONS`). A second
would have to be judged from the row the first left, and this side holds the row only as the base
recorded it and as the close wrote it, never the state in between — an application and its revert
batched into one close would be judged against neither. A run decides an entry once
(`DECISION_RUN_DUPLICATE`), so what this refuses is a close carrying two runs' applications for
one row; those are two closes.

## Why

The superseded rule derived each field's earlier value from the history: the disposition, the
cell's effects, the operations recorded, and what later decisions still stood. Six review rounds
each found a case it got wrong — a retirement the migration kept directly on the row, a correction
with no operations recorded, a placement that also set a relation, a keep reaffirmed with the same
record, a receiver whose destination the merge moved. Each fix narrowed the inference and the next
round found another case, because the information needed was not in the ledger at all.

Writing it down ends that: the application is the moment the earlier value is known, and it is the
only moment. The code then reads values instead of deriving them, and the rules above are about
the record's own completeness, which is decidable.

## What this closes

- **Inferring the prior value from the history** (the superseded record's rule). It cost six
  rounds and could not be made complete.
- **Status-only reverts** — reverting the status and leaving every field as the application left
  it. It is sound, and it makes most reverts useless.
- **A caller-supplied restoration value.** Unchanged from the superseded record: a value handed in
  is one nobody can check.

Revisit when `before` makes the ledger too large to review — the measurement is the ledger's size
against the rows it covers, after the first production run.
