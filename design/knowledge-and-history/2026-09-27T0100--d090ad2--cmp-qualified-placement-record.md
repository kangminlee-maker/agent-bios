---
created_at: 2026-09-27T01:00:58+09:00
head: d090ad2
kind: design
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260927-467eb1, D-20260927-605d2f
---

# CMP-QUALIFIED moves to V5, and a missing body gates only what depends on it

This record carries the owner's decision on the question the V1 third-slice record
(`2026-09-26T2245--c47e084--v1-slice3-record.md`) left open, and one correction to that slice's
body rule found while explaining it.

## The owner's decision (`D-20260927-467eb1`)

The question held two parts, and the owner chose the default of each on 2026-09-27.

- **Placement.** CMP-QUALIFIED moves from V1 to V5.
  - **Why it cannot stay in V1.** Its `source.rights.set` step is served by V5
    (`workenv.authority`), so V1 cannot run it. The plan places a case no earlier than the layer
    that states the refusal its own step expects.
  - **The rejected alternative.** A double of V5's rights code in V1 would have put a stand-in for
    V5's code into V1's acceptance.
- **The body rule.** Bodies stay read from each pinned revision's snapshot (`D-20260926-3b2d7d`),
  as the SSOT's S08 table and N09-C07-NEG state. Reading repository-authored bodies from the
  working tree is not restored.

**What moves, and when.** The test catalog is a dated file of the selected bundle, so it is not
edited here. The P01 re-freeze, already due, issues its successor, which:

- removes CMP-QUALIFIED from the V1 to V4 profiles and from the `personal-start` obligation;
- keeps it from V5 on.

**What V5 changes in the case**, when it writes `source.rights.set`:

- one code for the rights refusal (its result states `source_not_authorized`, its preparation
  `source_right_not_overridable`);
- `rules/review.md` absent before its commit, so that this device never holds its bytes, which is
  what the case says;
- the deploy unit's expectation under the snapshot rule;
- its units in the composition's order.

**What V1 still checks.** The case guards one rule: a lower layer never silently serves an
unavailable winner. V1 keeps that rule under a unit test
(`test_a_winning_unit_whose_body_is_not_held_is_unavailable_and_nothing_lower_serves`), and the
test's revert fails.

## The correction (`D-20260927-605d2f`)

The third slice made a layered unit's missing body `role_body_unavailable`. The contract says
otherwise:

- the code is defined as "a winning unit whose body this installation does not hold";
- C07's `prepared_unit` says only a winning required unit gates a start, and that `needed_by` keeps
  a unit required whatever its standing;
- across the 162 scenarios, all four layered units stated with no body state no gap. They are the
  three preparations of SRC-07 and TUI-ENTRY-LOCAL-OFFLINE's start.

**The rule now.** A body that is not held, or holds other bytes, is a gap only for a winning unit
or a unit a winning unit needs. Any other unit states no `body_digest` and gates nothing.

**How it was checked.**

- **Tests.** The unit test that expected the gap now expects none. A new test gives a needed
  unit's missing body its gap. The mismatch test now uses a winning unit.
- **Reverts.** The three reverts of the rule each fail a test.
- **Units.** All 165 V1 units pass.
- **Cases.** No case outcome moved. The V1 driver gives 9 passed, 12 blocked and 1 failed (still
  CMP-QUALIFIED, until the re-freeze moves it). Every scenario gives 51 passed, 82 blocked and 29
  failed, as before.

## Next

V1's fourth slice:

- delivery and hosts;
- roles;
- the lost reply;
- activation's recheck of the working tree, which N09-C07-NEG expects.
