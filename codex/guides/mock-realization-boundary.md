---
guide_id: mock-realization-boundary
language: en
status: active
use_when:
  - adding mocks, fakes, stubs, fixtures, or simulated providers
  - deciding whether a mock-backed path counts as completion
  - separating verification harnesses from production semantic paths
  - centralizing mock payloads for later deletion or replacement
  - reporting verification results that include mock-backed checks
core_rules:
  - mocks are verification realizations, not production semantic paths
  - use mocks to verify wiring, schemas, artifact contracts, deterministic projections, failure handling, and harness stability
  - use real semantic paths to verify product behavior, materiality judgment, causal reasoning, and semantic quality
  - keep mock behavior behind explicit realization switches, fixture modules, or mock executors
  - centralize mock payloads in a small deletion boundary so mock support can be removed or replaced together
  - share validators and artifact contracts between mock and production paths
  - report mock-backed verification separately from production-path verification
completion_policy:
  mock_backed_paths_support_verification: true
  mock_backed_paths_count_as_product_completion: false
  semantic_quality_from_mock: not_applicable
verification_focus:
  - mock paths exercise the same artifact contracts as production paths
  - mock payloads are centralized and easy to delete
  - mock execution is selected only through explicit realization config
  - verification reports distinguish mock, fixture, and live paths
  - production semantic gates run on real semantic paths
---

# Mock Realization Boundary Guide

This guide is a scoped extension of the global Coding Guidelines. Use it when
adding, reviewing, or cleaning up mocks, fakes, stubs, fixtures, simulated
providers, or mock executors.

The central rule is that a mock is a verification realization. It can prove that
the harness, contract, validator, projection, or failure path works. It does not
prove that the product semantic path works.

## Core Distinction

| Question | Mock path | Production semantic path |
|---|---|---|
| What does it prove? | Wiring, schemas, persistence, projections, failures | Real behavior, semantic judgment, user-visible quality |
| Who owns semantics? | Fixture author | Real model, real service, real user input, or real runtime authority |
| Completion credit | Verification support only | Product completion evidence |
| Quality gate status | `not_applicable` or harness-only | Passed/failed against real semantic criteria |
| Cleanup strategy | Central deletion boundary | Maintained product path |

Use the same artifact contracts and validators whenever possible. The mock path
should exercise the product contract, not create a parallel contract.

## Appropriate Mock Uses

Use mocks for:

- wiring checks
- schema and parser checks
- artifact persistence checks
- deterministic projection checks
- retry and failure handling checks
- timeout and cancellation checks
- E2E harness stability
- fixture-based regression tests
- external dependency isolation when the dependency is not under test

Use real paths for:

- product behavior
- materiality judgment
- causal reasoning
- semantic quality gates
- user-visible recommendations
- provider integration confidence
- release evidence for high-risk flows

## Structural Pattern

1. Define an explicit realization selector such as `mock`, `fixture`, `live`, or
   `direct`.
2. Keep mock payloads in a fixture module or fixture directory.
3. Keep mock executors as thin shells that route fixture payloads through the
   same validators and artifact writers used by production.
4. Mark semantic-quality evaluation as `not_applicable` for mock realization.
5. Report mock-backed verification separately from live or production-path
   verification.
6. Keep the deletion boundary small enough that mock support can be removed or
   replaced in one focused change.

## Realization Selector

Use explicit realization config so a mock cannot silently become the product
path.

Illustrative implementation:

```ts
type Realization = "mock" | "fixture" | "live";

function parseRealization(value: string | undefined): Realization {
  if (value === "mock" || value === "fixture" || value === "live") return value;
  return "live";
}

function selectProvider(realization: Realization) {
  if (realization === "mock") return createMockProvider();
  if (realization === "fixture") return createFixtureProvider();
  return createLiveProvider();
}
```

## Central Fixture Boundary

Centralize mock payloads. Runtime code that needs deterministic mock artifacts
imports from this boundary instead of growing inline mock-specific payloads.

Illustrative implementation:

```ts
export const reviewMockFixtures = {
  findingLedger() {
    return {
      schema_version: 1,
      findings: [
        {
          finding_id: "finding-001",
          target: "fixture-target",
          claim: "fixture finding",
          severity: "low",
        },
      ],
    };
  },
};
```

## Thin Mock Executor

Keep the mock executor as an execution shell. It should not become the place
where product behavior is reimplemented.

Illustrative implementation:

```ts
async function runMockUnit(unit: Unit, ctx: RuntimeContext) {
  const payload = reviewMockFixtures[unit.artifactKind]();
  const artifact = validateArtifact(payload, unit.artifactKind);
  await writeArtifact(ctx.outputPath, artifact);
  return {
    realization: "mock",
    artifact_path: ctx.outputPath,
    semantic_quality: "not_applicable",
  };
}
```

## Shared Validators

The mock path should pass through the same validators as production. This makes
mock tests useful for contract drift without letting mocks become product
completion evidence.

Illustrative implementation:

```ts
function writeArtifact(path: string, payload: unknown) {
  const validated = validateCurrentArtifactContract(payload);
  return writeYaml(path, validated);
}

await writeArtifact(outputPath, reviewMockFixtures.findingLedger());
await writeArtifact(outputPath, liveModelArtifact);
```

## Semantic Quality Gate

Mock-backed runs should make semantic quality explicitly not applicable. They
can still verify the harness and artifact collection.

Illustrative implementation:

```ts
function evaluateSemanticQuality(args: {
  realization: Realization;
  artifact: unknown;
}) {
  if (args.realization === "mock") {
    return {
      status: "not_applicable",
      applicability: "real_semantic_path_only",
      reason: "mock verifies harness and contracts, not product semantics",
    };
  }
  return evaluateLiveSemanticQuality(args.artifact);
}
```

## Verification Reporting

Separate mock-backed checks from production-path checks in final reports.

Preferred reporting shape:

```ts
type VerificationReport = {
  mock_checks: CheckResult[];
  fixture_checks: CheckResult[];
  production_path_checks: CheckResult[];
  unverified_risks: string[];
};
```

Useful report language:

- "Mock run passed artifact-contract checks."
- "Mock run did not evaluate product semantic quality."
- "Live semantic path remains unverified."
- "Production path passed semantic quality gate."

## Deletion Boundary

Mock support should be easy to remove or replace. A good deletion boundary has:

- one fixture module or fixture directory
- one realization selector
- one mock executor shell if needed
- shared validators outside the mock boundary
- tests that name the realization explicitly
- no product runtime dependency on mock-only payloads

When cleanup is needed, remove or replace the fixture module, realization route,
and mock-only tests together.

## Product Completion Rule

Mock-backed paths can support verification but do not count as product
completion.

Examples:

- A mock E2E can prove the pipeline writes all expected artifacts.
- A mock E2E cannot prove the recommendation is semantically correct.
- A fixture can prove a validator rejects malformed payloads.
- A fixture cannot prove a live provider follows the intended reasoning path.
- A mock provider can prove retry handling.
- A mock provider cannot prove the real provider integration is production-ready.

Connected cloud documents (live Sheets/Docs with bound scripts, triggers,
permissions, protections, named ranges, external references) are live
integrated systems, not portable files: unless the user explicitly asks for a
copy/export, edit in place through the native authority (connected-document
MCP/API). Before writing, enumerate the beyond-cell elements so none are
silently dropped, and report external load states (loading, timeout, quota,
permission-denied, broken reference) distinctly instead of collapsing them
into one success/failure.

## Design Procedure

Use this procedure before adding or extending mock behavior.

1. Name what the mock is meant to verify.
2. Name what the mock does not verify.
3. Choose an explicit realization selector.
4. Put mock payloads in one fixture boundary.
5. Route mock outputs through shared validators and artifact writers.
6. Keep mock executors thin.
7. Mark semantic quality as not applicable for mock runs.
8. Add reporting that separates mock checks from production-path checks.
9. Add at least one real semantic-path check when product behavior is part of
   the completion claim.
10. Keep deletion or replacement possible in one focused change.

## Verification Checklist

- Mock use is explicitly selected.
- Mock payloads are centralized.
- Mock behavior is not embedded across production logic.
- Mock output uses the current production artifact contract.
- Shared validators run on mock output.
- Mock-backed verification is reported separately.
- Semantic quality is not claimed from mock-backed output.
- Product completion has real semantic-path evidence.
- Mock support has a clear deletion boundary.
