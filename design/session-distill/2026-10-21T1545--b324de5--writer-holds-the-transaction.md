---
created_at: 2026-10-21T15:45:00+09:00
head: b324de5
kind: design
supersedes: 2026-10-21T1420--428724d--merge-pair-identity.md
---

# The bytes on disk are the base of a transaction, so the writer holds design §12.4 before replacing them

This record carries `2026-10-21T1420--428724d--merge-pair-identity.md` forward unchanged — the
owner's decision that an application records the values it replaced (`applied.before`), the rules
that hold such a record complete (`BEFORE_MISSING`, `BEFORE_FIELD_WRONG`,
`BEFORE_FIELD_OVERLAP`, `REVERT_INVERSE_UNPROVABLE`, `TRANSACTION_MULTIPLE_APPLICATIONS`, the
receiver's `standing_decision`), and how the two rows of a merge are identified and paired
(`REVERT_MERGE_SIDE`, `REVERT_MERGE_UNPAIRED`). It adds where that contract is enforced.

## The rule

`runlib/ledger.py`'s `write_atomic` is the only way a schema 2 ledger reaches disk. Until now it
validated the ledger it was given and compared the file's hash with the one the caller read, and
nothing more: design §12.4 — every changed row matching a validated decision, and a decision never
overwritten — was enforced only by callers that chose to run `check_pair` first.

**The file a writer would replace is the base of a transaction, and the writer holds it against the
ledger that replaces it.** Inside the lock, after the hash check and before anything is written:

- The bytes on disk are read as a ledger and `check_pair(was, ledger, allocated)` is run, with the
  allocation the caller froze (`allocated`, empty by default: a writer that adds no row freezes
  none). Any violation refuses the write by name, `TRANSACTION_INVALID, nothing written`, carrying
  the violations themselves, and the file's bytes are left exactly as they were.
- A first write — no file, or an empty one — replaces no transaction and is held against nothing.
- Bytes that are not a ledger cannot carry the contract, so a writer over them is refused by name,
  `BASE_UNREADABLE`, rather than passed as a first write. A corrupt file is repaired by a person,
  not by the next writer that happens to hold its hash.

## Why here

`DECISION_REWRITTEN` is the rule that makes every other rule in this record readable: the recorded
`before` values, the `standing_decision` replay and the merge pair's positional identity all assume
that a decision, once written, stays where it is. A writer that could drop or reorder a decision
would leave each of those checks sound and the history under them unsound, and the gap was
demonstrable in this module's own self-test, which persisted a ledger with an appended decision and
then overwrote it with the one without.

Enforcing it in the writer rather than in each caller is the same choice the rest of this work
makes: one owner for one rule. A caller may still run `check_pair` for its own reasons; it can no
longer skip it.

## What this closes

- The append-only contract as a caller's responsibility.
- Treating unreadable bytes as the absence of a base.

The revisit condition is unchanged: the ledger's size against the rows it covers, after the first
production run.
