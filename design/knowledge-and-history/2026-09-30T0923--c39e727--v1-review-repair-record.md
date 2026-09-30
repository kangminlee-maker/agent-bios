---
created_at: 2026-09-30T09:23:56+09:00
head: c39e727
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-76d550, D-20260930-1dfd67, D-20260930-6c708c
---

# V1's bound review found two false signals, and both are repaired before V1 is recorded again

This follows the [06:10 plan successor](2026-09-30T0610--b702da9--v1-acceptance-plan-successor-record.md).
P01 was re-frozen under the 06:04 plan in `run-10` (`accepted_nodes` `["P00", "P01"]`, `ready`
`["V1", "R0"]`). V1 was recorded into `run-10` by `run-tools/record_v1.py`, with all 21 cases
passed. Its one bound review was dispatched to `gpt-6-astra` at max effort, hermetic and
read-only, from 07:50:45 to 08:07:35, with the recorded commit's source in the packet.

The review returned `defects_found`: two findings, and 20 stated checks. It found that every
digest the record states recomputes, that the 21 outcomes are what the logs show, and that
publishing would unaccept neither P00 nor P01. V1's pending attempt is therefore not published.
V1 is recorded again, in a new run, after this repair.

## What the review found

1. **High: a selected Instructions source that does not resolve starts silently** (done-when
   [10]: "relevant gaps/material effects … stay visible and enforced").
   - Composition reported `selection_unresolved` at `/collections/0`.
   - `workenv/hosts/start.py` started on any `previewed` composition, and `roles.projection`
     carried only gaps at `/units/…`. With no Instructions unit it projected nothing at all.
   - So the activation committed with no gap, and the session's environment said nothing.
   - The reviewer showed it with the real owners on an in-memory store.
   - Re-derived here from the code:
     - `roles.py` filtered the gaps to `/units/`;
     - `start.py` never read `material_gaps`;
     - the entry's positions read the collection's state, not the composition.
   - The design says a required winning startup unit must resolve or the person changes the
     selection (SSOT, "A required winning startup unit must resolve"). C07 says
     `selection_unresolved` is "not absence, and no lower layer silently satisfies it".
2. **Medium: F-20** (done-when [0] and [6], exact result evidence).
   - The hook recorded the delivery of its own composition, whose unit ids the session never
     saw; the launch text named the start's.
   - The reviewer cited the 11:51 record's measured ids and the owner's state extract.

## What the owner chose

- **The session still starts, and is told** (`D-20260930-76d550`). The alternative — refusing
  the start and showing the reason on the entry until the selection changes — is closed. It was
  the coordinator's recommendation and was not taken.
- **F-20 is fixed now** (`D-20260930-1dfd67`), not deferred as chosen on 2026-09-29.
- **How F-20 is fixed** (`D-20260930-6c708c`). The environment is made of cross-preparation
  facts only, and the hook records a delivery only where its composition renders the launch
  text byte for byte.
  - The alternative — composing once per start, binding the start's own preparation to the
    link — is closed. It changes C02/C07's rule that a delivered preparation is composed for its
    link, and the scenarios, and re-freezes P01.
  - The rendered text's only per-preparation value was the unit id, which is why this works.

## What changed

- **`workenv/roles.py`**
  - `material(store, prepared)`: the preparation's material gaps at an Instructions unit or an
    Instructions collection, the collection's role read from the store.
    - A gap at another role's unit or collection is left out.
    - So is one at neither (the checkout moved), which already refuses the activation.
  - `projection` carries those gaps. A preparation with an Instructions gap and no unit now
    projects a `role_projection` with no unit and the gap (the schema allows an empty `units`).
    One with neither still projects nothing.
- **`workenv/hosts/start.py`**
  - `bodies_text` names no unit id: `Source src_…, body sha256 ….`
  - `gaps_text` writes a section `## Missing from this environment` listing each gap, where it
    is (for example "The personal instructions collection") and its code with the contract's
    meaning.
  - `environment(state, prepared)` renders the whole environment, and `start` uses it.
  - The job carries `environment`, the sha256 of that text.
- **`workenv/hosts/hook.py`.** On `new`, the hook renders its composition with
  `start.environment` and records only where its sha256 is the job's. It no longer compares
  body digests alone.
- **`FINDINGS.md`.** F-20 is deleted (closed).
  - F-19 stays open: a start whose only Instructions entry is unresolved hands no body, and its
    `new` delivery record is still lost. The activation and its projection now carry the gap.
- **Tests.**
  - `test_roles.py`, 22 tests. It adds:
    - an unresolved Instructions selection carried by a projection with no unit;
    - an unresolved knowledge selection not carried.
  - `test_start.py`, 37 tests. It adds:
    - a start whose selection has an unresolved source still launches and its environment ends
      in the missing section; after `new`, the activation's projection carries the gap;
    - the recorded delivery names a preparation whose unit ids differ from the start's and whose
      rendered environment is the launch text.
  - The job and exact-text tests are updated. The moved-checkout test now moves the environment
    digest.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1r.py`) caught all 8 mutations:
  - collection gaps not carried;
  - a gap alone projecting nothing;
  - the gaps not rendered;
  - the environment given no gaps;
  - the unit id named again;
  - the job without the digest;
  - the hook comparing bodies only;
  - the hook checking nothing.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`v1-accept/all_outcomes.py`, 837 profile-case outcomes: 61
  passed, 764 blocked, 12 failed) are identical before and after. No later stage's case moved.
- **Bindings.** No scenario, serving row or contract file changed, so P01's bindings are
  unchanged.

## Next

1. **Real use on both hosts,** with the committed code:
   - a start on each, and whether the recorded preparation renders the handed text;
   - a Claude Code start whose collection holds an unresolved source, and whether the session
     reads the missing section.
2. **`run-11`:** `run-10` with V1's unpublished attempt removed and kept as evidence.
3. **V1 recorded again,** and one bound review.
