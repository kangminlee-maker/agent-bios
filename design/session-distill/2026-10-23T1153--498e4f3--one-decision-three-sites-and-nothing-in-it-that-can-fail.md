---
created_at: 2026-10-23T11:53:42+09:00
head: 498e4f3
kind: review
supersedes: 2026-10-23T1030--64c5962--the-stop-decision-is-the-first-thing-settlement-does.md
---

# One decision, three sites, and nothing in it that can fail

Hermetic review round 3 on `498e4f3` returned five major findings and one minor. The 1030 record said
the stop decision is the first thing settlement does, which was true of where it stood and not of what
it was made of: the decision itself could fail before persisting anything (HC#0), the two readers of
the same rows disagreed about the same row (HC#1, HC#4), the decision was unreachable from two places
settlement can end at (HC#2, HC#3), and the ordering control checked a list of strings rather than the
boundary (HC#5). This record supersedes it.

**Two claims in the 1030 record were wrong and are corrected here.** It said covering an exception out
of `_follow` would need a decision inside the follow loop; it does not — the same decision runs once,
on exceptional completion, from the rows the monitor already holds. And it said the ordering control
held every statement settlement makes against the order; it held eight named strings, and a statement
inserted before the decision passed it.

## The guarantee

**One decision.** `Supervisor._offer_stop` is the only place a bound excess becomes a stop. It reads
rows through `bound.observed_rows`, checks them with `bound.check_observed`, builds the entry with
`bound.excess`, and persists through `_stop_run`. The first offer wins: the call's own record of the
stop is the guard, so a later site adds nothing when an earlier one already stopped the run.

**Three sites, and no fourth.**

1. The statement after `_follow` returns. The AST control holds that boundary: between the `_follow`
   call and the first offer, in the AST of `call`, there is nothing at all.
2. The statement after `_reconcile` returns, because reconciliation can MEASURE a row that was still
   pending — a compaction measured from the closing aggregate — so the excess can exist only then.
   This site runs before the seat projection, the usage record and every write after them.
3. The failure path. Any exception out of `_follow` or out of settlement offers from the monitor's
   rows and then re-raises the original exception unchanged. The monitor is reachable there because
   `_follow` publishes it into a holder as soon as it exists.

**The fourth site is removed.** The old end-of-settlement check read the written usage record. **For a
canonical `Ledger` row — the short spellings the token factories emit — that is the same rows read
later**, so its presence could not be told apart from its absence by any control; a decision site no
control can distinguish from its absence is not a site. What stays at the end of settlement is the
`input_observed` figure and the `USAGE_INCOMPLETE` refusal, which are about the record, not about the
stop.

The equivalence is scoped to canonical rows on purpose. A row carrying **conflicting aliases** —
`input_tokens: 0` beside `input: 135796` — reads as zero live, because `observed_of` prefers the long
spelling, while `Ledger.record` keeps only the short one, so the written record would show the excess.
No producer emits both today, so this takes internal corruption or injection; it is named below as a
residual rather than closed by restoring a site.

**Nothing in the decision can fail before the stop is persisted.** The rows container is walked inside
a guard, so a container that is not a sequence is reported rather than raised. Counts are rendered
through `bound.render_count`, which never raises, and an entry whose count cannot even be serialised is
written without the number and says so. The clock has a fallback and the entry records that it was
used; a clock that raises never blocks a stop. The redundant second clock call in `_stop_run` is gone —
the entry already carries its own `at`.

**One aggregation policy.** `bound.row_observation` is the per-row reading both `observed_rows` and
`observed_input` use, so the live rows and the written record cannot disagree about the same row. A
component is counted only when it is a whole number, not negative and not a bool — `isinstance(x, int)`
admitted `True` as one token and let a negative cache field cancel an excess. The valid components of a
row are a **lower bound**: a request whose input alone is past the bound is past the bound whatever its
cache fields failed to say, and the missing components are reported beside that, never instead of it.

## Residuals

- **Background threads inside `_follow`.** A reader or sampler thread that dies without propagating
  leaves rows it never read. Rows nobody read are not evidence we hold, so there is nothing to decide
  from; this is named, not closed.
- **A failure before the monitor exists.** If `_follow` raises before creating the monitor, the holder
  is empty and there are no rows. Same reason.
- **Repair after an unwritable ledger.** Unchanged from 0925: the supervisor lock and ledger being
  unusable refuses the next reservation by the same failure, so admission is not open in that state,
  but nothing remembers the attempt once the condition clears.
- **Conflicting spellings inside one row.** A row holding both `input_tokens` and `input` with
  different values is read live by the long spelling and written by the short one. Nothing the host
  produces carries both; the canonical-row invariant is not enforced, and that is why the fourth-site
  equivalence above is scoped rather than stated flatly.
- **The observer-form instruction comparison.** Unchanged: a change between the count and the send that
  the normalization ignores alters the raw length without a refusal.

## Closed alternatives

- **A pending-settlement barrier in the ledger.** Still not taken, for the reason the 1030 record
  gives, with the same revisit condition: repair-reopens-admission observed in practice, or a recovery
  protocol designed for another reason.
- **Keeping the end-of-settlement decision as a safety net.** Ruled out above: it is the same reading,
  later, and an indistinguishable site is a claim nobody can check.
- **Letting an invalid component stand as a count.** Ruled out. A negative or boolean field is not a
  count, and treating it as one let an invalid value cancel a conclusive excess.

## Controls

`bound.py` holds the policy: the two readers run over one table of row shapes and must agree, a partial
row's valid components are its lower bound, a negative or boolean component is reported rather than
counted, and a container that cannot be walked is reported rather than raised — judged through a guard
so that a reading which raises fails a control by name instead of ending the suite. `dispatch.py` holds
the sites: a count too large to render, a clock that raises, a rows container that is not a sequence, an
excess that only reconciliation establishes (settling cleanly, with a failing projection, and with a
failing usage write), an exception out of `_follow`, a lock release that fails after the ledger write,
the snapshot helper judged on its own, and the AST boundary with a planted statement before the offer.
Seven mutations were reverted one at a time; each failed named controls with no aborts — the
validation (2 in `bound`), the partial-row policy (4 in `bound`, 1 in `dispatch`), the clock fallback
(1), the serialisation guard (2), the reconciliation site (5, all of them the clean-settlement
controls), and the failure path (2). The container guard failed its own control in `bound` (1) and one
in `dispatch`; that dispatcher case is explained by `_rows_snapshot`'s guard as much as by the rule's,
which is why the snapshot helper now carries a control of its own instead of being inferred from it.
