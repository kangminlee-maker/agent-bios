---
created_at: 2026-11-13T04:48:00+09:00
head: f21ba77
kind: design
---

# Release 1's S12 records the ledger and names the rest

Lead decision, 2026-11-13, made while implementing S12 (`session-distill/runlib/stage_close.py`),
under the owner's `D-20261113-f22b7d` (release 1's S11 writes files and the owner commits) and its
dated record, which asked for S12's release-1 form: the ledger, the versions and the coverage in the
checkout, the nudge as an owner command.

## What the close writes

Two tracked files of the declared checkout, and its own records in the run directory:

- `design/session-distill/ledger.json` — one `decisions[]` element per item of the confirmed final
  set and the run's window, through `runlib/ledger.py` alone (`apply_decision`, `create_entry`,
  `write_atomic`). The transitions of §12.3 are that module's; a pair it rejects is refused here by
  its own name and nothing is written.
- `session-distill/coverage.json` — for a periodic run, S3's `read-results.json` folded against the
  state S1 pinned (`census.reconcile`), promoted with `coverage.write_atomic`. A targeted run
  promotes nothing.

Both are written only if the file still hashes to what the run pinned at S0.

## What was closed

1. **Writing the version registry.** `versions.json` maps a closed window to the commit whose
   instruction corpus reflects it. Release 1's stages make no commit, so there is no sha to write;
   a row with a null commit would be a registry entry that registers nothing. The close names the
   line for the owner to add after their commit. The window row in the ledger carries
   `commit: null` for the same reason, and says so.
2. **Running `update-state.py`.** The launcher's state file is under the owner's home. Release 1
   writes no state root, so the close names the command instead of running it.
3. **Appending §11's resolutions to the ledger.** S3 derives them into the run directory. A
   resolution of `observed` or `not observed` rests on exposure — that the applied unit was delivered
   before the occasion — and release 1 verifies no delivery (every applied item is recorded
   `unverified`). Appending resolutions now would put conclusions in the ledger that the evidence for
   cannot yet be shown. They stay in the run directory until delivery evidence exists.
4. **An id the model or the owner picks.** A new entry's id is allocated by code: the series after
   the highest `S<n>` the ledger holds, numbered from 01 in the confirmed order, frozen in the run
   directory before the ledger is written (§12.4: "new ids exactly those allocated").
5. **A second ledger rule set.** The close builds an element and the fields its disposition licenses
   and hands them to `ledger.py`; it does not decide what an entry becomes. Where the mapping from a
   review row to an element is not enough for the ledger (an incubate adopted from S7b's alternative
   carries no observation, a merge needs a receiving entry), the ledger refuses and the close stops
   with the item named. That is deliberate: a release that guesses those fields writes a ledger
   nobody approved.

## What a row becomes

- an item S11 applied: `applied` with S11's journalled operation ids and paths, delivery
  `unverified`;
- a ledger-only keep, incubate or drop: `applied` with no operation (it takes effect at S12, §10.4);
- a `none`: on an existing entry an element with no `applied`; on a candidate with no entry nothing;
- a candidate formed in this window: a new entry — lesson from the candidate, kind and diagnosis
  from the review row, evidence as `{claim_id: the candidate, evidence_id: each event it was formed
  from}`, coverage basis `view`;
- a legacy entry or a due decision: decided on the entry it names, a due decision carrying the
  incubate it `resolves`.

## Not done by release 1's close

Each is named in `close.json` (`not_done`): delivery verification, the observation resolutions, the
occasion index, the dated run record under `design/`, the version registry, the launcher state.
`accounted` and `fully_read` on the window row are null: the close does not compute them.

## Revisit

With release 2's decision on S11 commits: the commit sha on the window and in the registry, delivery
verification, the resolutions, and the recovery close (`close --recovery` stays reserved).
