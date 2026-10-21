---
created_at: 2026-10-21T14:20:00+09:00
head: 428724d
kind: design
supersedes: 2026-10-21T1310--9637e8b--revert-before-values-validation.md
---

# A revert names no target, so a pair is proved by replay, not by a shared run

This record carries `2026-10-21T1310--9637e8b--revert-before-values-validation.md` forward
unchanged — the owner's decision that an application records the values it replaced, the four rules
that record restates, and the five validation rules it added, including `applied.before`,
`REVERT_INVERSE_UNPROVABLE`, `BEFORE_MISSING`, `BEFORE_FIELD_WRONG`, `BEFORE_FIELD_OVERLAP`,
`REVERT_MERGE_SIDE`, `TRANSACTION_MULTIPLE_APPLICATIONS` and the receiver's `standing_decision`.
It adds how the two sides of a merge are identified and paired, which the superseded record left to
a shared operation id and a shared run.

## The rule

**A merge is identified by three things: the entry that made it, the run that decided it, and the
operation it recorded.** A shared operation id alone matches another run's decision, and a shared
run alone matches any decision that run made on that row.

**The partner's revert is the one this transaction appended.** A revert already sitting in the
partner's history was appended for its own reasons and closes no pair.

**That a revert undoes the merge is established by replay, never by its position or its run.** A
revert carries no reference to its target: what it undoes is what the replay of design §12.3 says
it pops. So for each side, the appended revert is replayed over the partner row as it stood before
it, and the decision it undoes has to be the merge's application on that row — the reduce (merge)
on the entry that made it, the receiving decision on the entry that received it. Otherwise
`REVERT_MERGE_UNPAIRED`, naming the partner row and what its revert undid instead.

The case this refuses is not hypothetical: the entry a merge absorbed can be decided again
afterwards — a drop over an absorbed row is allowed and changes no field — and its revert then
undoes that later decision. Both rows replay, both records check out, and the merge stays while its
receiving side is released.

`REVERT_MERGE_SIDE` names the absorbed entry's id, which is where the owner reverts a merge, or
says that no row of the ledger made the merge this decision claims to have received.

## What this closes

- Pairing by a shared operation id, or by a shared run.
- Accepting a revert that sits on the partner row without asking what it undoes.
- Reading the partner's whole history for its revert rather than what this transaction appended.

The revisit condition is unchanged: the ledger's size against the rows it covers, after the first
production run.
