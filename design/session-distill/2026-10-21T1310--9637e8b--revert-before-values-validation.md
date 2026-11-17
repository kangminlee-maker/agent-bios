---
created_at: 2026-10-21T13:10:00+09:00
head: 9637e8b
kind: design
supersedes: 2026-10-21T1210--f7ec815--revert-before-values.md
---

# A recorded before-value is only as good as the rules that hold it complete

This record carries the owner decision of `2026-10-21T1210--f7ec815--revert-before-values.md`
unchanged — an application records the values it replaced in `applied.before`, a revert restores
exactly those plus the status design §12.3 derives, and the alternatives that record closed stay
closed — and adds the validation rules its review found missing. The superseded record is kept for
its reasoning; this one is the contract `session-distill/runlib/ledger.py` `record_problems` holds
against the module.

## What this record carries over unchanged

Named here because this record is the contract, and a rule nobody restates is a rule the next
reader looks for in a superseded file:

- A revert restores exactly `applied.before` — its `fields` where the row held a value and nothing
  where `absent` names it — plus the status the history derives, and it accepts no value from its
  caller (`REVERT_VALUE_SUPPLIED`).
- It is refused by name, `REVERT_INVERSE_UNPROVABLE`, where the application it undoes recorded no
  values to put back, and where a merge's receiver holds no decision carrying that merge's own
  operation.
- A record is held against the row change it claims to describe: `BEFORE_FIELD_MISSING`,
  `BEFORE_FIELD_EXTRA`, `BEFORE_FIELD_WRONG`.
- One applied decision per row per transaction (`TRANSACTION_MULTIPLE_APPLICATIONS`): the row
  between two of them is recorded nowhere.

## What the superseded record left open

Writing the earlier value down removes the inference, and it moves the whole question to the
record's own completeness. Five ways a record could be absent, self-contradictory or unpaired
passed validation:

**1. Every application records what it replaced, including one that replaced nothing.**
`create_entry` writes `applied.before` on the decision that creates a row, as the empty record —
a row that did not exist replaced nothing, and recording that is not the same as recording nothing.
A decision a transaction appends without the property is refused by name, `BEFORE_MISSING`, where
it is appended rather than where a revert later fails to read it, and a creating decision whose
record names any field is refused by the same comparison as any other (`BEFORE_FIELD_EXTRA`). A
missing record is treated as empty nowhere.

**2. The two parts of a record never name the same field** (`BEFORE_FIELD_OVERLAP`). A field in
both `fields` and `absent` says the row held a value there and held none, and a revert reading it
would write the value back and clear it in one pass. It is refused in the ledger's own semantic
validation, so a stored ledger cannot carry one, and in transaction validation, so a close cannot
introduce one. This covers the record a merge writes on its receiver.

**3. A migrated element carries no record** (`LEGACY_BEFORE`). Design §12.2's elements are not a
run's applications, and the earlier record already said `before` is modern-only; nothing enforced
it.

**4. A merge is put back on both rows or on neither, from either side** (`REVERT_MERGE_SIDE`).
The decision a merge writes on its receiver carries the merge's own operation, so it is
recognizable as the receiving side of a merge rather than an ordinary correction. The owner reverts
a merge on the entry it absorbed: a revert aimed at the receiver is refused by name, and the
refusal names the absorbed entry. In transaction validation the pair is required from either side —
a receiver put back while the row it absorbed still holds the merge is refused, as is a receiving
decision whose merge no entry of the base made.

**5. The receiver's merge decision has to be the application still standing over that row**, derived
through the same replay a revert of any row uses (`standing_decision`, design §12.3's table), not
through the list of applied elements. The list counts reverted applications and reverts themselves,
which both refused a merge whose receiver had moved on and come back, and admitted a revert dressed
as the application it undid. A receiver whose own decisions do not replay to its status is refused
by name (`REPLAY_INCONSISTENT`) rather than read.

## Regression cases this record requires

The owner's decision is only worth its controls, and two of them are about the real data rather
than a fixture:

- **S2-19 of the live ledger**, whose retirement design §12.2 kept directly on the row with no
  element of its own. A drop applied over it changes no field, so its record is empty and its
  revert restores the status and leaves the retirement where the migration put it. The control runs
  on the migration of `design/session-distill/ledger.json`, not on a synthetic stand-in, and plants
  a revert that clears those fields.
- **A merge that revised its receiver's own text and route.** The record on the receiver's decision
  is what puts that row back, asserted through the transaction side and through the event API, with
  planted wrong restorations failing by name.

## What this closes

- Treating a missing `before` as an empty one, anywhere.
- Deriving the receiver's standing application from its applied elements rather than from the
  replay every other row uses.
- A receiver-initiated merge reversal as an ordinary revert.

Nothing in the superseded record's closed alternatives is reopened. The revisit condition is
unchanged: the ledger's size against the rows it covers, after the first production run.
