---
created_at: 2026-11-11T11:15:00+09:00
head: b39eff1
kind: design
supersedes: null
---

# The derivations read one table, and two judges' disagreement is a disputed field

WP-10, commit W1 (`2026-10-20T2119--cc0498f--implementation-plan.md` §2 WP-10): design §6.4's derivations as code
over `session-distill/tables/unit_outcome.json`, the one source `runlib/derive.py` and its fixture generator read.
Decision D-20261111-082292 records the interpretations below. Delivery evidence (§6.3), retrieval (§6.2), the
checks and the planted controls are the later commits of this package.

## What the table holds

Six sections, each a list of rows with ids, in the design's own words: `unit_diagnosis` (the four situation/action
pairs), `unit_outcome` (§6.4's ten rows, with `any` and `—` accepting every value of the column's domain),
`candidate_diagnosis` (the precedence covered > wrong or insufficient > trigger problem > gap, and the redundancy
row), `kind` (the outcome precedence, the two no-matching-unit pairs, obsolete, and one addition below),
`admission` (admitted, rejected, disputed) and `promotion` (two lineages, the grave consequence classes, type G's
three lineages or a confirmed arc, and the dispositions below the bar). Beside them: the value domains, the eight
admission requirements (S4's), and the absence-completeness policy. The code matches rows and returns the row id it
matched; it does not restate a rule a row holds.

## Interpretations the design leaves open

- **Two judges, one field.** Every judged field (situation, action, following, contribution) takes the judges'
  value when they agree and is `disputed` when they differ, shown with both values. A disputed following or
  contribution is matched as the table's `unknown`. A disputed situation or action leaves the unit's diagnosis
  `disputed`, which only a row accepting every diagnosis matches (`o1`, `o2`); otherwise its outcome is `unknown`.
  A disputed unit that could reach a precedence row above the best agreed diagnosis leaves the candidate's
  diagnosis `unknown`. §10.1's `판정` and §10.2's recomputation supply the settled value (`adjudicated`), and the
  derivation runs again with it. The closed alternative: taking one judge's value, which would let a single seat
  decide a misfire.
- **Reference points.** Unit outcomes are read at `release`, one per unit and session, because a delivery state is
  a fact about a session (§6.3); `current` answers only whether a release-side gap is covered now.
- **Obsolete first.** §6.4 names the obsolete case without a place in the order. The kind rows are ordered and the
  order is the precedence; obsolete is first, because a situation both judges find no longer arising makes its
  units' outcomes moot.
- **One addition to the kind rows.** For a candidate with no matching unit the design names two pairs (gap/gap is
  gap, gap/covered is already resolved). Any other pair - an absence unknown at either point, or current units
  that match without covering - is `unclassified` (`no_matching_unit_otherwise`), so the table stays total and
  nothing is read as a gap it is not. The row says it is not §6.4's.
- **The test state.** Release 1 runs no S8 (D-20261111-818391). `unit_outcome` takes a named test state; the
  domain is `untested: s8_deferred`, a blank or an unnamed value is `TEST_STATE_UNNAMED`. No row of §6.4 needs a
  test result, and each says so in its `test` column (`—`); a row that came to need one would name it there.

## The absence policy (open)

`absence_completeness.policy` is `literal`: an absence (`gap`) holds only where the reference point's own §6.1 flag
says complete. Since `native_settings` has no producer at any reference point (D-20261102-0caf7d), `literal` keeps
every absence unknown on every machine: no `gap`, no kind `gap` or `already resolved`. `scoped` reads the statuses
of the layers it lists, and every absence answer names what it read and what was unknown. Both paths are
implemented and controlled; which one ships was asked of the lead on 2026-11-11 with `literal` as the default, and
changing it is a change of this one field.

## Frozen fixtures and the design's rows

`derive.py --generate-fixtures` wrote `tables/unit_outcome_fixtures.json` once: one fixture per row, each holding
the row's cases built from the row's own fields (a `—` row expanded over its whole domain), with the row's own
expectation. The self-test runs every case through the production functions, records a fixture as executed only
after that, and compares the table's rows, the frozen fixtures and the executed cases by id (`ROW_UNFIXTURED`,
`FIXTURE_ORPHAN`, `CASE_NOT_EXECUTED`, `CASE_UNFROZEN`, and `ROWS_NONE` for a bijection over nothing). The design's
rows are copied once into the module (`DESIGN_6_4_*`) and the table, rendered back into the design's words, is held
against them (`CONTRACT_DRIFT`); the review compares the copy with the design text.

## Measured on this tree

| What | Result |
| --- | --- |
| The table | 35 rows; the frozen fixtures hold 209 cases |
| derive self-test | 53 controls, OK |
| Revert rows (`rows-w1.py`) | the baseline passes; 14 revert rows caught, none missed (the test-state row was missed once, its control reworked to hand a valid judgment a blank state, then caught) |
| Self-tests | every session-distill module with a self-test: 35, 0 not rc=0 |
