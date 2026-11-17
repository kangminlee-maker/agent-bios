---
created_at: 2026-10-21T10:09:00+09:00
head: a04f78a
kind: design
supersedes: 2026-10-21T0938--ebca5ee--plan-addendum-wp13-correction.md
---

# Session distill implementation plan: second correction to the WP-13 addendum

Round 4 of the WP-13 review found that the record this supersedes
(`2026-10-21T0938--ebca5ee--plan-addendum-wp13-correction.md`) describes a read the compatibility
projection does not perform, and that the revert contract it states was only half implemented.
Dated records are not edited, so this one carries both corrections. Everything the earlier two
records say that is not corrected here still stands.

## 1. The compatibility projection derives from `destination` alone

Plan §6.1 S-4 describes `ledger_compat.placed_entries()` as "derived from `destination` and the
latest place decision's `applied` (or the `legacy_application` element)". The record this
supersedes repeated that sentence. The implementation reads `destination` and the kept entry
fields, and never reads `decisions` at all.

**The implementation is right and no read is being added.** The projection's contract is the six
fields a schema 1 consumer reads: `{id, status, learning_id, placed_anchor, placed_package_id,
classification}`. `placed_anchor` and `placed_package_id` are `destination.anchor` and
`destination.package_id`; `status`, `learning_id` and `classification` are fields design §12.2
keeps on the entry. An `applied` record carries `{commit, paths, operations, delivery}` — not one
of the six. Reading it would change no output, and the plan's inert-field rule makes a read whose
result no consumer uses a defect, not a courtesy to a sentence.

What S-4 is protecting is that `placed_anchor` is **derived and never stored** — a second copy of
a field is a second authority. That holds: the projection is read-only, `learn/build-promotions.py`
reaches those fields only through it, and the entry carries no `placed_anchor` of its own in
schema 2. The migration's own guarantee — that the `placed`, `placed_anchor` and `implementation`
values land in `destination` and in the latest place decision's `applied` (or a
`legacy_application`) — is `migrate-ledger.py`'s, and its self-test holds it there. It is not a
read the projection has to repeat.

`ledger_compat.py`'s own module docstring claimed the `applied` read as well; that sentence is
corrected with this record.

## 2. A revert puts the row back, and the result is held against the inverse

The first correction said a revert's licence is the licence of the application it undoes. That was
a permission and nothing more: the event applied no restoration, so reverting a correction left
the corrected text in place, and an unrelated value passed because nothing compared the result
with anything.

A revert of an application is now derived in two parts (`revert_plan`):

- **Derived.** The state an entry that never had that application holds, which the ledger can
  reconstruct: a place's `destination` and a keep's `keep` return to null, the absorption of a
  merge and the retirement of a delete are removed. The code writes these itself, and refuses them
  from the caller (`REVERT_DERIVED_FIELD`) — a value the ledger derives is not a value to be
  supplied, and accepting one would let a revert write anything into it.
- **Supplied.** A value the application replaced and the ledger never recorded: the text a
  correction replaced, the route a re-delivery replaced. The revert carries it
  (`record_event(..., "revert", element=..., restore={...})`), and it must differ from what the
  application left (`REVERT_RESTORES_NOTHING`). Where the undone cell proves a replacement
  happened — the `text_revised` effect, or a re-delivery, whose whole meaning is a new route — a
  restoration is required.

The result is then held against the inverse (`revert_restored`), in `apply_decision` and again in
`row_violations`, so a revert recorded by hand without putting the row back is refused
(`REVERT_NOT_RESTORED`). A merge wrote a decision on the receiving entry, so reverting the merge
appends the receiver's own revert there too, and the round-trip control reads it.

**What is not decidable here, and why.** The ledger records no field history, so two things cannot
be proven and are not claimed:

- that a supplied value is the value the application replaced, rather than some third value. The
  ledger can require that it differ from what the application left, and does;
- the inverse of a **revival**. A place or an incubate out of `absorbed`/`retired` releases
  whatever retirement or absorption the row held, and those fields are optional on an entry, so an
  entry that held none and one whose value is now lost look the same from the history. The revert
  may carry them back and cannot be made to.

Storing the before-state of each application would make both decidable. That is a design question
for §12.1, not an implementation liberty, and it is left open here deliberately: this round's
boundary is what the recorded history can prove.
