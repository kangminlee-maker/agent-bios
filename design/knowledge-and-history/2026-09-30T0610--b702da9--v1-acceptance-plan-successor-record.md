---
created_at: 2026-09-30T06:10:32+09:00
head: b702da9
kind: design
plan: 2026-09-30T0604--b702da9--development-plan.json
supersedes: null
decisions: D-20260930-a0b6b8, D-20260930-78bd3d
---

# Before V1 is accepted, the plan says what V1 built

V1's acceptance began from the [P01 re-freeze](2026-09-29T1531--2fdbd67--p01-refreeze-record.md):
`accepted_nodes` `["P00", "P01"]`, `ready` `["V1", "R0"]`. All 21 of V1's cases passed on the
tree as it stood, but the plan did not describe V1 as built. This record carries what was found,
what the owner chose and the 06:04 plan successor that carries it. P01's re-freeze and V1's
record follow it and are not part of it.

## What was found

- **V1's tested subject did not measure.** `component:V1` resolved to unknown: "V1 has not
  written `workenv/admission.py`". A V1 record would have been refused `missing or stale tested
  subject`.
  - `workenv/admission.py` came to V1 from the component graph's P06 when the stages were drawn.
    V1 admits Instructions in `workenv/sources/revisions.py`, not in that file.
  - V1 wrote four files that no node owns: `workenv/commands.py`, `workenv/local.py` and
    `workenv/terminal.py` (the entry a person runs, `536b74e`), and `workenv/guides/` (the
    memory-use guide the usage contract points at, `365a6f2`). A change to them would have left
    V1 current.
- **Five operations assigned to V1 were not built,** and no V1 case reaches them. The first stage
  whose bound cases reach each:
  - `package.candidate.register`: PK, whose own done-when forbids changing source.
  - `preparation.assess` and `role.project`: V2.
  - `source.revision.publish`: V5.
  - event `configure`: V8.

  `cases.py` asks only that an entry sit under its node's owned paths, not that it exists.
- **Two of V1's done-when clauses named more than V1 built.**
  - [1] "Exact portable objects and scoped mutable authority transactions have request-bound
    receipts". Transfers and rights or grant changes are V5's operations, and the sentence was
    in no other node, so removing it from V1 alone would have dropped the obligation.
  - [5] "Explicit activation of the memory reader capability". V1 supplies the usage contract
    and the guide; the reader operations are V2's, and the guide says reading is not available
    in this version.
- **Smaller things, carried in the same change.**
  - V1's `covers` row for done-when [2] did not name CMP-STORAGE, the case that shows one
    authoring home (`source_home_conflict`).
  - TUI-ENTRY-KO-STATE's narrative named TUI-OBS-KOREAN-TERMINAL, which the 2026-09-22 trim
    removed.

A read-only audit found these, and each was re-derived before use: the subject resolution, the
five entries by import, and each clause's words against `serving.json`.

## What the owner chose

- **The plan is corrected in full before V1 is accepted** (`D-20260930-a0b6b8`). The alternative,
  correcting only what the evaluator refuses and carrying the rest into V1's record, is closed.
- **P01 is re-frozen before V1's record** (`D-20260930-78bd3d`). The alternative, keeping the
  2026-09-29 freeze and disclosing the moved bindings until V4, is closed.

## What the successor changes

`v1-accept/successor.py` in the workbench wrote every change by named edits, each anchor found
exactly once:

- **The plan** (`2026-09-30T0604--b702da9--development-plan.json`):
  - V1 owns `workenv/commands.py`, `workenv/guides/`, `workenv/local.py` and
    `workenv/terminal.py`, and no longer `workenv/admission.py`. V2 to V8 own the four as they
    own every earlier stage's paths, and keep `workenv/admission.py`.
  - V1's done-when [1] reads "Exact objects and scoped mutable transactions have request-bound
    receipts". The original sentence is appended to V5's done-when, with `done_when_from`
    `P03[0]`.
  - V1's done-when [5] reads "Explicit activation supplies a runtime-owned compact usage
    contract for decision memory and a reachable guide …; reading memory through that contract
    is V2's."
  - A stage that serves an operation implements its contract (the `cases.py` serving check), so
    V2 takes on C04 and C07, and V5 takes on C01.
  - The spec's binding is re-hashed. The catalog, the SSOT, the evaluator and its regressions
    keep their stamps.
- **The spec** (`2026-09-30T0604--b702da9--development-spec.md`): frontmatter, graph link, and
  the P03 row of the component mapping now names "V5 receipts for portable objects and authority
  transactions".
- **`gates/workenv/conformance/serving.json`:** the five rows go to V8, V2, V2, V5 and V8.
- **`gates/workenv/case-index.json`:**
  - V1's covers [2] adds CMP-STORAGE.
  - V5's covers gains the moved clause: N22-E2E-POS, N13-C09-POS, N22-OUTBOX-POS, N11-C08-POS.
- **TUI-ENTRY-KO-STATE:** the narrative now says input-method composition is observed by real
  use, because the trim removed the case that did. The scenario was regenerated.
- **`CURRENT.md`:** the two selectors, the successor sentence and the P01 line.

## How it was checked

- **Reproduction.** The script, run on a fresh `git archive` of `b702da9` with the same stamp,
  reproduced all seven changed files byte for byte. `CURRENT.md`'s P01 line was edited by hand
  afterwards.
- **The gates.**
  - `cases.py`: `CASES OK`. Before V2 and V5 took on the contracts, it failed by name three
    times: "V2 does not implement C07", "V2 does not implement C04" and "V5 does not implement
    C01".
  - `check-development-plan.py`: 33/442, and its self-test 7/71.
  - `scenarios.py --check`: 162 specs.
- **The subjects.** `component:V1` now measures (`1485622b…`), and `contracts` is unchanged
  (`8546f04f…`).
- **V1's 21 cases** pass on the successor tree (`v1-accept/dry2/`).
- **The bindings.** Against `run-9`'s, those of V1 to V9 and PK move; P00's, P01's and R0's do not.
  - V1's moves with the KO-STATE scenario.
  - The others move with the serving rows their cases reach.
  - On a scratch copy, the ownership correction alone moved none. So the ownership fix does not
    move bindings; the serving and scenario edits do.
- **The workenv gate** failed once, in `test_cases.Bindings`, whose copy of the tree takes only
  tracked files and so missed the untracked plan. After staging, `test_cases.py` passes 81.

## Next

1. **P00** is re-recorded into `run-10` by plan digest (`v1-accept/make_run10.py`).
2. **P01** is re-frozen: the control audit on this commit, its record, one bound review, and the
   evaluator.
3. **V1** is recorded by `run-tools/record_v1.py` with its direct-use evidence, then reviewed
   and evaluated.

F-20 stays open, as the owner chose on 2026-09-29, and V1's record states it.
