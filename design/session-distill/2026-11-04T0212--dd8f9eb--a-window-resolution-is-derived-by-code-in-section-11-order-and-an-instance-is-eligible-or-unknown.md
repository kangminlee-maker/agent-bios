---
created_at: 2026-11-04T02:12:00+09:00
head: dd8f9eb
kind: design
supersedes: null
---

# A window resolution is derived by code in §11's order, and an instance is eligible or unknown

WP-08 commit 4 is split in two, as the lead approved on 2026-11-04. 4a, this record, lands the derivation that turns one
expected observation's instances into its window resolution. 4b connects S3 to it:

- the expected observations due, read from the ledger the declaration pins;
- their criteria in the read packet;
- the search forcing expansions;
- the instances stored with the basis code sets;
- the resolutions recorded for WP-21.

The plan amendment of 2026-11-03 (row 6) places `measures.derive_resolution` and its O9 fixtures in WP-08. WP-21
stores the resolution and consumes it. Rendering and the ledger close move to WP-21 and WP-23.

## What lands

| Piece | Where |
| --- | --- |
| `derive_resolution(instances, basis)` returning `{resolution, basis, counts, occasions}` | `session-distill/runlib/measures.py` |
| The O9 and F04 fixtures, through the real basis predicate `views.coverage_basis` | `measures.o9_fixtures`, `measures.self_test` |
| The umbrella leg | `gates/check-parity.sh` |
| The deferral of a third exposure value | D-20261104-6df529 |

The rule is §11's, in its order:

1. `not_observed` when an eligible occasion was not observed;
2. otherwise `observed` when there is at least one eligible occasion, every one is observed, no occasion has
   `exposure_unknown`, and the basis is `source` or `view`;
3. otherwise `no_occasion` when the basis is `source` and no occasion was found;
4. otherwise `pending`.

The result is the ledger's `$defs.resolution` without `run` and `window`, which WP-21 adds when it stores the
resolution with `ledger.append_resolution`. The counts follow the ledger: `eligible`, and the eligible occasions'
`observed` and `not_observed` counts. `exposure_unknown` occasions are counted apart, and a not-observed verdict on one
of them does not count as not observed. `occasions` lists every instance. The module is pure, as `bound.py` is: no
runlib import, no file read, no clock.

## Choices made here

1. **An instance is `eligible` or `exposure_unknown`, never "not exposed"** (D-20261104-6df529, a deferral). Design
   §11 gives the instance two states, and the plan gives exposure by rule to WP-21 done-when 7 (old installer, older
   carrier, compiler digest, loading record). That rule reads pins and receipts the window does not show. An occasion
   shown not exposed is therefore no occasion of the applied item, and it is never an instance. Until WP-21 lands:
   - a pre-application occasion the model cannot show exposed is answered `exposure_unknown`;
   - an otherwise observed resolution then stays `pending`;
   - `not_observed` still wins, as the first O9 fixture shows.

   Revisit at WP-21 done-when 7, or when C1 or the rehearsal shows pre-application occasions holding observed
   resolutions pending.
2. **The input is one expected observation's instances in one scope.** These are refused by name as RESOLUTION_INPUT:
   - a basis outside §5.4's three values;
   - instances of two expected observations;
   - an instance whose basis is not its scope's (the basis is set by code, once per scope);
   - an exposure or verdict outside the two values;
   - an occasion repeated.
3. **The fixtures run through the real basis predicate.** Each fixture gives a scope, and `views.coverage_basis` sets
   its basis. So the F04 fixtures (one source left unaccounted: an absence and an observed occasion both `pending`) and
   the fixtures with a missing, deferred, failed or partly read session exercise the predicate S3 uses. A copy of the
   predicate would not show that.
4. **Which O9 rows are here.** Every row whose outcome §11's derivation decides is here, sixteen fixtures with F04's
   two. These rows are elsewhere:
   - rows about exposure itself (old installer, removed wrapper, compiler digest, personal layer, recovery, pre-receipt
     transaction) belong to WP-21's predicate;
   - the carried pending intervention belongs to WP-09 and WP-21's two scratch runs;
   - rows about reading (the search forcing an expansion, the skipped span's match) reach this derivation as the
     instances and basis the reading left, and S3's self-test runs them through the reader in 4b.

## Controls (measures self-test)

- Each fixture derives its expected resolution.
- Each fixture's expected resolution, replaced by each of the other three in turn, fails by the fixture's name. This is
  done-when 5's "each expected verdict flipped failing by name".
- The fixtures reach all four of §11's resolutions.
- Every combination of one occasion's exposure and verdict on every basis, and of no occasion on every basis, derives
  where §11 puts it.
- The vocabularies equal the schemas':
  - the resolutions and basis of `ledger.schema.json`'s resolution;
  - the instance's basis, exposure and verdict in `observation.schema.json`;
  - the result's keys plus `run` and `window` equal the ledger resolution's required keys;
  - the counts equal the ledger's counts.
- The six refused inputs are each named.
- The counts keep the `exposure_unknown` occasion apart, and `occasions` keeps every instance.

The pretrial (`work/impl/wp08/c4a/c4a-revert.py`, author-side) has twelve rows, and each reverts one rule or check.
Each row must fail its control by name, and the unmutated suite must pass:

- not observed winning;
- the exposure_unknown and basis conditions of observed;
- the basis and no-instance conditions of no_occasion;
- counting not observed on eligible occasions only;
- the flip check;
- a branch left unreached;
- the ledger's vocabulary;
- the scope check;
- the repeat check;
- the predicate's source check.

The first pretrial found a defect in the self-test. With the source check reverted, a refused fixture left `None` in
the set of reached resolutions, and sorting that set raised before any control named itself. That is the shape the
lead's W notes record three times in this work package. A refused fixture is now named where it is refused and
left out of the reached set.
