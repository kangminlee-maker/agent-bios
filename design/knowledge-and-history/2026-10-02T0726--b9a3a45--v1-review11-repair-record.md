---
created_at: 2026-10-02T07:26:04+09:00
head: b9a3a45
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20261002-fceb6a, D-20261001-fa937f, D-20260930-c06461
---

# V1's eleventh bound review found an activation returning body bytes it never checked, and an activation now reads each body as composition read it

This follows the [00:26 repair record](2026-10-02T0026--8ef2bad--v1-review10-repair-record.md)
and the [00:35 direct-use record](2026-10-02T0035--ae6e541--v1-acceptance-after-review10-direct-use-record.md).

- **The record.** V1 was recorded into `run-20` at `b9a3a45`, and all 21 cases passed. `run-20`
  is `run-19` without V1's tenth, unpublished attempt (`v1-accept/make_run20.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 00:40:32 to 01:01:11 (`review-v1-20261002-r11/`).
- **The result.** `defects_found`: one medium finding, and 20 stated checks. The recomputable
  fingerprints, bindings and case outcomes match. P00 and P01 would remain accepted.

V1's attempt in `run-20` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### Medium: an activation returned bytes other than the body it recorded

This goes against done-when [1] and the exact result evidence of done-when [6].

- **The reviewer's case.** `N15-C11-POS`'s preparation, with the bundle read of
  `rules/review.md` returning `Do not require review.\n`. The activation committed with a
  receipt and no gaps. Its projection and the observation after it named the body `4e90f23c…`,
  while the bytes it returned hash to `bc43de51…`. The same case with the bytes unchanged
  committed consistently.
- **Reproduced here** on a copy of `b9a3a45`, with a bundle member rewritten after composition:
  the activation committed, its projection named `6242f073…`, and the bytes it returned hash to
  `bc43de51…`.
- **In the code.** `roles.projection` read each body it returned from its revision's bundle
  and checked nothing. Composition (`preparation.body_of`), a source's reference
  (`sources.reading.member_bytes`) and a start's text (`start.bodies_text`) each check the bytes
  against their digest. The activation's read was the one that did not.
- **Where it is reached.** Only where the owner's stored bundle changes after composition: an
  edited or damaged state directory. A start checks the bytes again before a host is handed
  them, so no session started through it received such bytes. The reviewer states the same.

## What the owner chose

From this review on, only a finding reachable in normal use blocks V1. A finding reachable only
when the owner's stored files are changed or damaged, or in a like abnormal condition, is
recorded as a known limit with its condition (`D-20261002-fceb6a`). This finding is fixed now,
because the fix is one place, and V1 is recorded and reviewed once more under that rule.

The closed alternatives are fixing every finding whatever condition it needs, the bar
`D-20261001-fa937f` kept, and publishing V1 from `run-20` with this finding as a known limit.

## What changed

- **`workenv/preparation.py`.** `held(state, revision, path, digest)` reads a member from its
  revision's bundle: its bytes where they are the bytes `digest` names, or why not
  (`role_body_unavailable`, `object_digest_mismatch`). `body_of` reads through it.
- **`workenv/roles.py`.**
  - `bodies` reads each body an activation returns, in its units' order, through
    `preparation.held`.
  - `activating` reads them once, after its other rules and before anything is committed. A
    body not held as its unit names refuses with that code at `/preparation_digest`.
  - `activating` returns the bodies it read, and `projection` returns exactly those.
  - So the answer as an activation is handed on (`session_routing_dispatched`) is refused as
    the activation is.
  - The module's description says so.
- **`gates/workenv/units/v1/test_roles.py`.**
  - New: a body rewritten after composition refuses `object_digest_mismatch`, and a body
    removed refuses `role_body_unavailable`. In each, the answer as it is handed on and the
    activation are refused and return nothing, and no delivery is recorded. With the bytes
    restored, the activation commits and returns them.
  - The test that calls `projection` directly reads the bodies first.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1zi.py`, `mutate_v1zi-rerun-r11fix.txt`) caught 6
  of 6:
  - a held body not checked against its digest;
  - a body the bundle does not hold read anyway;
  - an activation returning its bodies unchecked;
  - a body not held not refusing the activation;
  - a body not held left out instead;
  - the answer as an activation is handed on reading no body.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-r11fix.txt`), missed nothing they
  could apply. `moved_anchors.py rerun-r10fix rerun-r11fix` names no anchor this repair moved;
  each sweep cannot apply the same anchors as on the tree before it, all moved in the
  restructure, and `mutate_v1zg-reanchored.py` caught all 45 of them again.

- **The V1 tests:** 591 pass. **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical to
  `outcomes-after-v1zf.json`: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-20` holds, so P01 is not
  reopened.

## Next

1. A short real use with the committed code: one new session on each host, since activation
   serves both.
2. V1 recorded into `run-21`, which is `run-20` without V1's attempt (`v1-accept/make_run21.py`).
3. One bound review, under `D-20261002-fceb6a`, whose result goes to the owner.
