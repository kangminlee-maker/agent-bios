---
created_at: 2026-09-14T17:50:30+09:00
head: 35c75ca
kind: review
status: development-plan-validated-product-implementation-not-started
---

# Development planning review

The [current SSOT](2026-09-14T1720--35c75ca--consolidated-design-ssot.md) incorporates local lock,
signout, explicit offline reentry, in-flight request outcomes and separately
managed finalizers. It also records the user's explicit **no backward-compatibility
requirement**. The [development specification](2026-09-14T1720--35c75ca--development-spec.md),
[task graph](2026-09-14T1720--35c75ca--development-plan.json) and [test catalog](2026-09-14T1720--35c75ca--test-catalog.json)
turn that design into later implementation work. CURRENT.md points to this bundle.

## Decisions and source evidence

The planning investigation read actual Instructions store/catalog/session/app,
setup/import/installer, launcher, test-discovery and gate code. The selected
[brownfield manifest](2026-09-14T1720--35c75ca--brownfield-evidence.json) identifies 71 inspected files,
including untracked runtime/test files. This is not the full isolated implementation
baseline; P00 must capture all required working-tree inputs before coding.

The old implementation's off/reset, setup machine ID, authoring revision and
compiled instruction authority cannot be treated as the new access/Team/K/M
contracts. Existing code is reusable or replaceable as appropriate. Old commands,
readers, aliases, native resume and downgrade support need not be retained.
The user waiver does not authorize silent deletion of source work or selected data.

Recorded directions: `D-20260914-2b77cf` (compatibility waiver and controlled
cutover), `D-20260914-9012b8` (dependency-driven spec and scoped verification).
Prior product-purpose and identity decisions retain their scope.

## Review corrections

Three delegated read-only perspectives examined brownfield integration,
access/governance, and execution/UI/test coverage. Their reports were integration
inputs, not runtime proof or verified cross-provider independence.

Corrections incorporated before final checks:

- Target-supported --repo/root/catalog/owner/setup/import/host entrances must be
  inventoried and guarded, replaced or retired; a separate folder is insufficient.
- Personal P10/P11 and M1 no longer depend on Team/SSO/GitHub implementation.
- P14 depends on the client shell it extends. Worker unit tests have explicit
  paths; common conformance/fixtures/family harnesses have an integrator owner.
- Early tasks use scoped profiles; complete future families do not create reverse
  dependencies. Empty unbound case IDs before P01 mean not runnable, never passed.
- Empty test discovery/oracle sets fail, while legitimate empty product selections
  and memory results remain valid.
- Compatibility preservation and old-binary downgrade guarantees were removed.
- Final cutover rechecks selected-data revisions after old writers quiesce, so
  edits/outbox items arriving after an initial conversion cannot be lost.
- Local signout blocks future session-derived access; it does not retrospectively
  cancel dispatched requests or silently stop an independently authorized finalizer.

Focused follow-up reviews confirmed the addressed scope/profile/compatibility
changes; the final source-data race was then added to the spec, P18 and N24.
Review agreement does not certify all possible implementation cases.

## Checks performed now

- Current behavior: `python3 compose/test_instructions_compatibility.py` — 12 passed;
  `python3 compose/test_instructions_app.py` — 23 passed;
  `python3 compose/test_instructions_transactions.py` — 3 passed. Tests used their
  existing temporary-store fixtures. These 38 tests are starting-state evidence,
  not permanent backward-compatibility requirements or a full baseline certificate.
- Static plan checker: 19 tasks, 31 test families, U01–U19, W01–W10 and C01–C12
  coverage; acyclic dependencies; personal milestone independence; scope/profile
  and owner rules. Sixteen negative controls plus positive/overlap controls passed.
- Plan document bindings and selected input hashes are checked before dispatch.
  The checker reports only P00 initially ready and never runs a product task.
- Local document links/anchors, JSON parsing, explicit new-file terminology scan,
  product-purpose projection and decision-ledger validation passed in their scope.

The full Instructions/parity suite was not run in this planning turn. New N01–N26
runtime/platform/user scenarios remain planned and unimplemented. P01 must freeze
actual atomic case IDs, adapter/tool/encoding/protection bindings and their bounded
spike evidence before downstream implementation dispatch. Live provider, real
user/IME and release evidence cannot be substituted with fixtures or skipped tests.

## Bound documents

| Artifact | SHA-256 |
| --- | --- |
| consolidated-design-ssot.md | `0c4a5897b51cf1ccf1417f3fbb7b2f751a36691d8ed78c87ca7a7ad0c3728cc0` |
| development-spec.md | `ebce4a06ad098d151a2ae35238138bde90bf68096c2b4805edb5da8dc069fad4` |
| development-plan.json | `fd246c32e2a8e5f693a7d82fc81bb101fcb05f66195c8f476830c73675dd0c85` |
| test-catalog.json | `c9cbecd2f41ee9345dec494ac891983c3bf1d26749d324a6fa7404a3beeb4da5` |
| brownfield-evidence.json | `b5ae76d56d0c4ac7a8ff158e87c649a14147bd1494dac2ae0d8954e87f8942e7` |

The 15:04 visualization remains a labeled prior-revision map and was not regenerated
or browser-tested in this turn. No product runtime, installed configuration, native
session, real Team, OAuth consent, external repository, shared membership or index
was changed. The delivered Python checker is an author-side planning validator,
not the proposed AI workflow runner or product authentication implementation.
