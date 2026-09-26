---
created_at: 2026-09-26T20:06:39+09:00
head: 4f81320
kind: design
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260926-617e4f, D-20260926-37e90d
---

# An authored admission names the manifest it submits

The 17:47 slice-2 record left one question for the owner. `source.revision.admit` through the
`author_here` route carried only a `source_request`: a role, a destination and a route name. That
is nothing that says what is admitted. The owner chose option A on 2026-09-26: the route names the
manifest it submits, and the request carries it. This record is that change and what it let V1 do.
Everything else in the 17:47 record still stands.

## The contract

`C01 source request` changed in one definition, and its description corrected a stale count:

- `author_here_route` now requires `manifest_digest`: the digest of the `source_manifest` the
  request carries, as submitted (members by path, digest and size). The owner stores that
  manifest with the time it produced it, so the revision digest is not the one the route names.
- The description said "one of four routes"; there have been three since `extend_supplied` was
  dropped.

Two examples changed and one was added:

- `request_to_author_here.json` names `revision_submitted.json` by its digest.
- `request_for_a_role_the_table_does_not_hold.json` does too, so its only refusal stays the role.
- `request_to_author_here_without_its_manifest.json` is new. It is refused `variant_mismatch` at
  `/route` in submit mode.

`examples/index.json` was re-emitted. The contract tests (156) and every example pass.

## The code

`source_revision_admit` now serves `author_here` (`D-20260926-617e4f`):

- **The manifest.** The route's `manifest_digest` must name a manifest the request carries, or
  the admission is `ref_unavailable` at `/route/manifest_digest`. A manifest for another source
  is `request_mismatch`.
- **The source.** The first admission expects no head and creates the source in the
  destination's scope, with the payload's role, kept the destination's way. A later admission
  names the head it expects and must name the same scope, role and way, or it is
  `source_home_conflict`.
- **The destination.** One kept by a package is `publisher_bytes_modified`. A
  repository-authored one needs a binding of its repository held here, or it is
  `binding_unverified`, and its bytes come from that checkout.
- **The rest is a commit.** Signatures, member bytes, the bundle published before the unit, and
  the head checked again inside it. Commit and admission now share that code.

How a source's home keeps it — managed, repository-authored or package-published — is now held
for every source, admitted or registered: storage layout 3 adds `sources.home_mode`. A
registration keeping an admitted source another way is a second home. A row written under layout
2, with no value there, reads it from its home record.

Admitting a published package or importing an external one is not served. Neither is the
provenance two V8 cases expect beside an authored admission (`D-20260926-37e90d`).

## The scenarios

The 30 authored admissions in 16 specs were aligned with the contract:

- Each step now carries the manifest it submits and marks it submitted.
- Its route names that manifest.
- The stored manifest is the submitted one with the owner's `produced_at`.

In ten specs the owner had minted 20 member digests. Those digests are now stated by the
submitter, as the value each stood for, everywhere the spec names them. `--check` passes on all
162.

## How it was checked

- **Units.** 121 V1 tests; 11 are new:
  - 10 admission tests;
  - a registration changing only the package.

  Storage's upgrade test also checks the new column.
- **Reverts.** 86 for slice 2 and the admission, and the first slice's 53 again. Three survived
  the first pass, because their tests changed two things at once:
  - the package or document root of a home (only its mode was tested);
  - the stale check before an admission publishes (the check in the unit caught it too);
  - an admission changing only the way its source is kept.

  Each got a test that changes that alone, and all 139 are caught.
- **The driver, at V1.** Still four passes and no failures. CMP-PINS, DEL-PERSONAL,
  N09-C07-POS and N15-C11-POS now pass their admissions and block at `workenv.preparation`, with
  the other cases waiting there, so 10 of the 18 blocked cases wait on it.
- **Every scenario.** With admission in scope: 59 passed, 84 blocked and 19 failed, against
  61/84/17 before. The two new failures are V3's and V8's routes, served nowhere yet:
  - N27-IMPORT-POS imports a package;
  - N16-C12-POS expects a provenance.

  CAP-06 and SRC-04 now fail at their admission rather than at the resolve after it. Under V1's
  own routing, 20 of 22 pass, as before.
- **Direct use.** The state root of the slice-2 direct use, written under layout 2, was opened
  and brought to layout 3 with `home_mode`. Then:
  1. It authored a personal rules source here, receipt #8, and revision two against its head,
     receipt #9.
  2. Admitting again on the old head was `stale_base`.
  3. Admitting into the same source as knowledge was `source_home_conflict`.
  4. A route naming a manifest the request did not carry was `ref_unavailable` at
     `/route/manifest_digest`.
  5. The source is held with no home record, kept `managed`.
  6. It authored `docs/setup.md` as the repository's knowledge, and the bundle holds the
     checkout's bytes.

  The transcript is `transcript-three.txt`.

## P01

The contract change, like the scenario alignments before it, moves what P01 froze. The P01
re-freeze, already due, takes them together.

Nothing here is pushed.
