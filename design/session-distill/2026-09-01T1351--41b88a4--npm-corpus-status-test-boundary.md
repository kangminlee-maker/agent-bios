---
created_at: 2026-09-01T13:51:08+09:00
head: 41b88a4
kind: design
supersedes: 2026-09-01T1348--41b88a4--npm-corpus-status-blocker.md
---

# Npm corpus-status fix — package and transition boundary

The cause fix in the superseded design stands: keep the existing `corpus-status` concept,
ship `compose/corpus-state.py`, and let its `project` command produce the runtime domain/apply
status in an npm layout without shipping the author-only version registry or ledger.

This record narrows where degraded projection is allowed and completes the verification space.

## Required means required for the feature

`corpus-status.json` is not structurally required for every installer operation; the launcher
already has an unavailable-state fallback. A fresh global file deployment can finish without it.
It is required for the advertised TUI **Corpus packages** panel, recorded apply outcomes, and the
proposed desktop onboarding skill to report the truth. Once onboarding promises those features,
failure to write their status must make onboarding incomplete rather than print a guessed note and
return through the success path.

## Layout decides whether registry absence is legal

Determine the source layout before projecting:

- **npm package** — no `.git`: author-only `design/session-distill/versions.json` and
  `ledger.json` are expected to be absent. Project current domains and apply state, and mark
  version/ledger/rollback data unavailable.
- **checkout or worktree** — `.git` exists as a directory or gitfile: the registries are required.
  Missing, malformed, or inconsistent registry data is an error. Preserve the prior status rather
  than silently degrading to npm mode.

The installer must surface the exact projection or record-apply error. Replace the current
stderr suppression and generic `versions.json/ledger missing?` guess. A failure after corpus files
were written must say that deployment changed but status recording did not; it must not report the
whole onboarding as complete.

## Npm projection over prior checkout state

In npm mode, preserve only fields whose authority remains valid, including a prior `last_apply`
until the current onboarding records its outcome. Recompute `generated`, source/package identity,
and domain fields. Remove or explicitly mark unavailable checkout-only version, ledger summary,
rollback, repository, and deployed-corpus fields; never carry them forward as current npm facts.

This is the transition the live run exposed: a checkout-generated status from 2026-08-31 remained
unchanged after an npm onboarding on 2026-09-01. Because both selected every domain, the stale
domain list looked correct while its timestamp and empty `last_apply` exposed the mismatch.

## Verification cases

Build the subject from the real package:

1. Run `npm pack`, extract the tarball, and assert that the materialized root contains
   `compose/corpus-state.py` while the two author registries are absent.
2. **Fresh npm state:** start without `corpus-status.json`, apply a non-default selection, and
   assert fresh available/applied sets plus `last_apply: applied`.
3. **Stale checkout-to-npm transition:** seed a status carrying a checkout `repo`, generated time,
   version/summary, rollback/deployed-corpus fields, and a different domain selection. Apply from
   the packed root and assert a new generated time, package identity, the requested domains,
   `last_apply: applied`, and removal or explicit unavailability of every checkout-only field.
4. **Checkout contrast:** in a `.git` directory and a gitfile worktree, remove or corrupt each
   registry in turn. Projection must fail by the named cause and leave the prior status bytes
   unchanged.
5. **Canary outcomes:** use a deterministic canary stub only to exercise installer plumbing.
   Success records `applied`; failure records `canary_failed` and exits non-zero. Do not count the
   stub as activation evidence.
6. **Standalone verification:** require a readable status and equality between
   `domains.applied` and `selection.json`. During install verification, which runs before the
   activation canary records the final outcome, do not require `last_apply: applied` yet.

The package test must use the materialized tarball rather than a checkout copy. The existing
installer scenario uses the checkout as `$REPO`, so it cannot detect a missing packaged file.

## Negative controls

Prove the package E2E fails by name when each cause is restored:

- omit `compose/corpus-state.py` from the tarball;
- restore unconditional author-registry reads in npm mode;
- retain checkout-only fields during npm reprojection;
- suppress a projection or record-apply error; and
- stop checking status/selection equality in `verify`.

Removing the package-gate exemption and adding the script to `files[]` catches the first cause.
It does not discover the script's internal data dependencies, because the gate scans runtime paths
from `install.sh` and `compose/assemble.py` and follows imports rather than arbitrary Python data
paths. The materialized-package E2E owns the legal absence of the author registries and the npm
degrade contract.

## Desktop order remains unchanged

Only after these package and transition cases pass should the standalone desktop onboarding skill
consume `corpus-status.json`. The skill still delegates every write to
`agent-bios onboard --domains ...` and requires a new desktop task after applying a selection.
The Claude-only activation canary remains separate from proof that Codex desktop consumed the
managed global region.
