---
created_at: 2026-09-01T13:52:53+09:00
head: 41b88a4
kind: design
supersedes: 2026-09-01T1351--41b88a4--npm-corpus-status-test-boundary.md
---

# Npm corpus-status fix — final boundary corrections

The package/transition test design in the superseded record stands with three corrections.

## Status is required on successful deployment

A command that deploys the launcher and advertises its corpus panel cannot finish a successful
`install` or `onboard` without a readable, selection-consistent corpus status. `cmd_install`
already runs deployment verification, so the contract must not simultaneously allow a successful
fresh deployment with no status and require verification to reject that state.

Status remains optional only for paths that do not claim a completed deployment, such as help,
uninstall, and dry-run. Dry-run must describe projection without writing it.

## Preserve the existing `repo` field

In npm mode, recompute `repo` as the resolved installed package root and keep it in status.
`run_corpus_apply` uses this existing field to find `<repo>/install.sh` when `agent-bios` is not
on PATH. Removing it would break a live recovery path and replacing it with a new source/package
identity field would increase the concept surface without changing the behavior.

Remove or mark unavailable only checkout-specific corpus-version and rollback metadata, including
version/summary, `rolled_back_to`, and `deployed_corpus`. Recompute `generated` and domains, and
preserve `last_apply` until the current onboarding records its own outcome.

## Make both hidden failures fire independently

The materialized-package E2E must contain two real write failures in addition to the success and
canary-outcome cases:

1. Point `AGENT_BIOS_CORPUS_STATUS` at an unwritable or structurally invalid destination and run
   onboarding from the packed root. Projection must print the exact write failure, return
   non-zero, and never print a completed-onboarding summary.
2. Let projection succeed, then use the deterministic success canary stub to remove the status
   before returning the expected marker. `record-apply` must then report that its status target is
   missing, onboarding must return non-zero, and no success summary may survive.

These cases separately kill stderr suppression around `project` and the silent `|| true` around
`record-apply`; one generic failure fixture cannot prove both paths.

For reproducibility, build the package subject in a clean temporary clone with the normal pack
guards satisfied, or use `npm pack --ignore-scripts` when the test's declared subject is only the
`files[]`/runtime-path boundary rather than publication provenance. In either route, extract the
actual tarball and assert its preconditions before onboarding.

With these corrections, the cause fix remains concept-surface preserving: the existing
`corpus-status`, `repo`, installer, assembler, and launcher recovery path keep their names and
authority; the npm layout gains an honest degraded projection rather than a parallel status
artifact.
