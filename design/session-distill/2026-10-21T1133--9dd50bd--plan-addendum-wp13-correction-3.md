---
created_at: 2026-10-21T11:33:00+09:00
head: 9dd50bd
kind: design
supersedes: 2026-10-21T1009--a04f78a--plan-addendum-wp13-correction-2.md
---

# Session distill implementation plan: third correction to the WP-13 addendum

Three review rounds in a row found the same class of defect in the revert of an application: each
round widened what the code would put back, and each time the reviewer found a case where the value
it wrote was not the value that had been there. Round 5 found three more (a keep standing over an
earlier keep cleared to null; fields an application may change that the restoration list did not
cover; a merge receiver whose own history had moved on). The owner's lead settled the direction
rather than the next case, and this record states it. It supersedes
`2026-10-21T1009--a04f78a--plan-addendum-wp13-correction-2.md`; what the earlier records say about
design §12.2's metadata, the delivery event and the compatibility projection still stands.

## 1. A revert is conservative

Design §12.3's revert row asks for two things: "the status before that decision; a revert decision
appended". That is the whole of the contract, and the status inverse is **derivable** — `replays`
reads it off the entry's own decisions through §12.3's table, and that part is unchanged.

A **field** inverse is performed only where the entry's recorded history fixes the earlier value
exactly. That is one case: a field the reverted disposition **installs** on an entry that had none
of it — a place's `destination`, a keep's `keep` record, the absorption of a merge, the retirement
of a deletion (`INSTALLED_BY`) — and only when nothing else could have put a value there.

Everywhere else the revert is **refused by name**, with one code,
`REVERT_INVERSE_UNPROVABLE <entry> <field>`, and **nothing is written**. The cases:

- design §12.3's cell required the application to revise the text (`text_revised`), so the text it
  replaced is gone;
- the application is a re-delivery, whose whole meaning is a new route over the one that was there;
- the application's own operations say what it changed: an `edit` reaches the text, a `route` the
  destination (`OPERATION_PROVES`). This is what catches a correction that moved a destination;
- an earlier decision still standing licenses the same field — a repeated or reaffirmed keep, where
  clearing the record would erase what the earlier keep protects;
- design §12.2 migrated a value into that field (`LEGACY_SETS`: a legacy application's destination,
  a historical retirement's `retired` and `retire_reason`), so the run did not put it there;
- the receiving entry of a merge had a decision applied to it between the merge and the revert, so
  reverting the merge alone does not put that entry back.

The receiving entry of a merge is part of that row's inverse, not a separate matter: the merge wrote
a decision there, so reverting the merge reverts that decision too, and a transaction that puts the
absorbed row back while leaving its receiver holding the merge is refused
(`RECEIVER_REVERT_MISSING`).

**A revert carries no value.** The caller cannot hand one in (`REVERT_VALUE_SUPPLIED`): the ledger
has nothing to check it against, and accepting an unverifiable value is how the previous two
versions of this rule came to record wrong restorations as successes. Both `apply_decision` and
`row_violations` apply the rule, so a revert recorded by hand in a transaction is judged the same
way (`REVERT_NOT_RESTORED` for an inverse not performed, and the same refusals above).

**What this leaves undone, deliberately.** After such a refusal the application stays in force and
the owner's route is forward, not back: a correction of the correction, a re-delivery of the
earlier route — each its own decision, with its own approval, recorded as what it is. The ledger
does not pretend to an undo it cannot derive. The reverted-by-the-owner row of §12.3 therefore
reaches the status in every case and the row only where the record carries it.

The closed alternative — recording each application's before-values on the application itself,
which would make every inverse derivable — is a change to design §12.1 and is not implemented
here. The owner records that decision at integration.

## 2. One decision per row a transaction allocates

A row that did not exist at the base has no recorded state for a second decision to be judged
against: `row_violations` does that work between two recorded rows, and on this side there is no
earlier row at all. Rather than check the first decision and wave the rest through — which is what
round 5 found — a transaction that introduces a row carrying more than one decision is refused by
name (`NEW_ROW_MULTIPLE_DECISIONS`). A run that decides such an entry again does it in the next
close, against the row that close recorded.

## 3. A delivery outcome written by a transaction obeys the event's rules

The delivery outcome is one of the two things a later window may write into a recorded decision
(correction 1, §2). Writing it through a transaction rather than through the event is now held to
the same two rules the event applies: design §12.3's row has only `failed` and `unverified`
(`DELIVERY_OUTCOME_INVALID`), and the delivery of an element design §12.2 migrated is the one the
migration recorded (`DELIVERY_ON_MIGRATED`).
