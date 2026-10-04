---
created_at: 2026-10-04T17:32:02+09:00
head: 0fb45a9
kind: design
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V2
supersedes: null
decisions: D-20261004-1af5a7, D-20261004-cb2c6d
---

# A resolve states what stays unresolved inside the state it returns, one gap per entry, and four cases are corrected to say so

This records a correction to frozen scenarios found while measuring V2's progress on
2026-10-04. It accepts nothing.

## What was found

Every case of V2's profile was run under profile V2:

- V1's 21 cases all passed.
- Of V2's own 26 cases, 6 passed, and 19 stop at an operation or a driver feature V2's later
  slices build.
- One failed at a step slice 1 already serves: CMP-UI at `resolve_journal_mode`.

Two places disagree between frozen scenarios. C03 and C05 settle neither.

- **Where a resolve states a conflict.**
  - Nine resolve steps answer `previewed` with no gap of the result's own, and state the conflict
    inside the `qualified_state` they return: DC-SET, CMP-ORDER and the N07 cases.
  - Three state the conflict on the result's outcome as well: CMP-UI's one and CMP-MEANING's two.
  - `workenv/memory.py` answers as the nine do.
- **How the state names it.**
  - Of the 43 states that carry a gap, 34 give each unresolved entry a gap that names it by
    `pointer`.
  - Nine state one gap with no pointer, inherited from the contract example
    `c05/state_whose_conflict_waits_for_the_person.json`: two in CMP-MEANING, two in CMP-UI, four
    in DC-DURABLE and one in N08-PENDING-NEG.
  - `workenv/memory.py` names each entry.

## What was decided

- **`D-20261004-1af5a7`, the owner's choice.**
  - A resolve that returns a state answers with no gap of its own: the resolve succeeded, and what
    stays unresolved is part of what it returned.
  - CMP-UI and CMP-MEANING are corrected.
  - Closed: restating the gaps on the result, which would change the code and nine other steps.
- **`D-20261004-cb2c6d`, by the same rule.**
  - The scenarios that differ are corrected and the code stays.
  - The nine states name each unresolved entry by its own gap.
  - C05 says whatever could not be resolved is named in the state, and its runtime rule
    `gap_named_entry_not_current` is read through the pointer.
  - The contract example is a valid record under its schema and a frozen P01 artifact, so it is
    left as it is, and the specs set the gaps over it.

## What was checked

- **The generator.** `scenarios.py --check`: 162 specs, no problem. All 43 states with a gap now
  name their entries.
- **CMP-UI** passes `resolve_journal_mode` and now blocks at `project_effective_instructions`, on
  `role.project`, which slice 5 builds.
- **CMP-MEANING** runs under V5 … V9 and blocks at its first step, on access V5 builds.
- **The other runs.**
  - V1's 21 cases passed, and V2's family N07 passed 5 of 5.
  - `units/v2` passed 76 tests. `test_scenarios`, `test_cases`, `test_driver` and
    `test_executor` passed 236.
  - `check-workenv.py`: OK.
- **The bindings**, against those measured at `0fb45a9`.
  - Only `fixture_fingerprint` moved, for V2 … V9.
  - V1, P00, P01, R0 and PK did not move.
