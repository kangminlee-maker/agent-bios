---
guide_id: mock-realization-boundary
language: ko
status: active
use_when:
  - mock, fake, stub, fixture, simulated provider를 추가할 때
  - mock-backed path가 completion evidence인지 판단할 때
  - verification harness와 production semantic path를 분리할 때
  - mock payload를 나중에 제거하거나 교체하기 쉽게 중앙화할 때
  - mock-backed check가 포함된 verification result를 보고할 때
core_rules:
  - mock은 production semantic path가 아니라 verification realization이다
  - mock은 wiring, schema, artifact contract, deterministic projection, failure handling, harness stability 검증에 사용한다
  - product behavior, materiality judgment, causal reasoning, semantic quality는 real semantic path로 검증한다
  - mock behavior는 explicit realization switch, fixture module, mock executor 뒤에 둔다
  - mock payload는 작은 deletion boundary에 중앙화해서 mock support를 함께 제거하거나 교체할 수 있게 한다
  - mock path와 production path는 validator와 artifact contract를 공유한다
  - mock-backed verification은 production-path verification과 분리해서 보고한다
completion_policy:
  mock_backed_paths_support_verification: true
  mock_backed_paths_count_as_product_completion: false
  semantic_quality_from_mock: not_applicable
verification_focus:
  - mock path가 production path와 같은 artifact contract를 통과한다
  - mock payload가 중앙화되어 쉽게 삭제 가능하다
  - mock execution은 explicit realization config로만 선택된다
  - verification report가 mock, fixture, live path를 구분한다
  - production semantic gate는 real semantic path에서 실행된다
---

# Mock Realization Boundary 가이드

이 문서는 전역 Coding Guidelines의 scoped extension이다. Mock, fake, stub,
fixture, simulated provider, mock executor를 추가하거나 검토하거나 정리할 때
사용한다.

핵심 규칙은 다음과 같다.

> Mock은 verification realization이다. Harness, contract, validator,
> projection, failure path가 동작하는지는 증명할 수 있다. Product semantic
> path가 동작한다는 증거는 아니다.

## Core Distinction

| Question | Mock path | Production semantic path |
|---|---|---|
| 무엇을 증명하는가 | Wiring, schemas, persistence, projections, failures | Real behavior, semantic judgment, user-visible quality |
| semantics의 소유자는 누구인가 | Fixture author | Real model, real service, real user input, or real runtime authority |
| completion credit | Verification support only | Product completion evidence |
| quality gate status | `not_applicable` 또는 harness-only | Real semantic criteria 기준 passed/failed |
| cleanup strategy | Central deletion boundary | Maintained product path |

가능하면 mock path와 production path는 같은 artifact contract와 validator를
사용한다. Mock path는 product contract를 exercise해야 하며, 별도 contract를
만들면 안 된다.

## Appropriate Mock Uses

Mock을 사용할 곳:

- wiring checks
- schema and parser checks
- artifact persistence checks
- deterministic projection checks
- retry and failure handling checks
- timeout and cancellation checks
- E2E harness stability
- fixture-based regression tests
- test 대상이 아닌 external dependency 격리

Real path를 사용할 곳:

- product behavior
- materiality judgment
- causal reasoning
- semantic quality gates
- user-visible recommendations
- provider integration confidence
- high-risk flow의 release evidence

## Structural Pattern

1. `mock`, `fixture`, `live`, `direct` 같은 explicit realization selector를
   정의한다.
2. Mock payload를 fixture module 또는 fixture directory에 둔다.
3. Mock executor는 fixture payload를 production과 같은 validator/artifact
   writer로 흘려보내는 얇은 shell로 유지한다.
4. Mock realization의 semantic-quality evaluation은 `not_applicable`로 표시한다.
5. Mock-backed verification과 live/production-path verification을 분리해서
   보고한다.
6. Mock support를 하나의 focused change로 제거하거나 교체할 수 있을 만큼
   deletion boundary를 작게 유지한다.

## Realization Selector

Mock이 product path로 조용히 섞이지 않도록 explicit realization config를
사용한다.

구현 예시:

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

Mock payload를 중앙화한다. Deterministic mock artifact가 필요한 runtime code는
inline mock-specific payload를 늘리지 말고 이 boundary에서 import한다.

구현 예시:

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

Mock executor는 execution shell로 유지한다. Product behavior를 재구현하는
장소가 되면 안 된다.

구현 예시:

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

Mock path는 production과 같은 validator를 통과해야 한다. 그래야 mock test가
contract drift를 잡는 데 유용하면서도 product completion evidence로 오해되지
않는다.

구현 예시:

```ts
function writeArtifact(path: string, payload: unknown) {
  const validated = validateCurrentArtifactContract(payload);
  return writeYaml(path, validated);
}

await writeArtifact(outputPath, reviewMockFixtures.findingLedger());
await writeArtifact(outputPath, liveModelArtifact);
```

## Semantic Quality Gate

Mock-backed run의 semantic quality는 명시적으로 not applicable이어야 한다.
Harness와 artifact collection은 검증할 수 있다.

구현 예시:

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

Final report에서 mock-backed check와 production-path check를 분리한다.

권장 reporting shape:

```ts
type VerificationReport = {
  mock_checks: CheckResult[];
  fixture_checks: CheckResult[];
  production_path_checks: CheckResult[];
  unverified_risks: string[];
};
```

유용한 report 표현:

- "Mock run passed artifact-contract checks."
- "Mock run did not evaluate product semantic quality."
- "Live semantic path remains unverified."
- "Production path passed semantic quality gate."

## Deletion Boundary

Mock support는 제거하거나 교체하기 쉬워야 한다. 좋은 deletion boundary는
다음을 가진다.

- 하나의 fixture module 또는 fixture directory
- 하나의 realization selector
- 필요한 경우 하나의 mock executor shell
- mock boundary 밖의 shared validators
- realization을 명시하는 tests
- mock-only payload에 대한 product runtime dependency 없음

Cleanup이 필요하면 fixture module, realization route, mock-only tests를 함께
제거하거나 교체한다.

## Product Completion Rule

Mock-backed path는 verification을 지원할 수 있지만 product completion으로
count하지 않는다.

예시:

- Mock E2E는 pipeline이 expected artifacts를 모두 쓰는지 증명할 수 있다.
- Mock E2E는 recommendation이 semantically correct한지 증명할 수 없다.
- Fixture는 validator가 malformed payload를 reject하는지 증명할 수 있다.
- Fixture는 live provider가 의도한 reasoning path를 따르는지 증명할 수 없다.
- Mock provider는 retry handling을 증명할 수 있다.
- Mock provider는 real provider integration이 production-ready임을 증명할 수 없다.

연결된 cloud 문서(bound script, trigger, permission, protection, named range,
external reference가 있는 live Sheets/Docs)는 portable file이 아니라 live
integrated system이다: 사용자가 명시적으로 copy/export를 요청하지 않는 한,
native authority(connected-document MCP/API)를 통해 in place로 편집한다. 쓰기
전에 cell을 넘어서는 요소를 열거해서 아무것도 조용히 누락되지 않게 하고,
external load state(loading, timeout, quota, permission-denied, broken
reference)를 하나의 success/failure로 뭉뚱그리지 않고 구분해서 보고한다.

## Design Procedure

Mock behavior를 추가하거나 확장하기 전에 이 절차를 사용한다.

1. Mock이 무엇을 검증하려는지 이름 붙인다.
2. Mock이 무엇을 검증하지 않는지 이름 붙인다.
3. Explicit realization selector를 선택한다.
4. Mock payload를 하나의 fixture boundary에 둔다.
5. Mock output을 shared validators와 artifact writers로 흘려보낸다.
6. Mock executor를 얇게 유지한다.
7. Mock run의 semantic quality를 not applicable로 표시한다.
8. Mock check와 production-path check를 분리하는 report를 추가한다.
9. Product behavior가 completion claim에 포함되면 real semantic-path check를
   최소 하나 추가한다.
10. Mock 삭제 또는 교체가 하나의 focused change로 가능하게 유지한다.

## Verification Checklist

- Mock use가 explicit하게 선택된다.
- Mock payload가 중앙화되어 있다.
- Mock behavior가 production logic 곳곳에 박혀 있지 않다.
- Mock output이 current production artifact contract를 사용한다.
- Shared validators가 mock output에도 실행된다.
- Mock-backed verification이 별도로 보고된다.
- Mock-backed output에서 semantic quality를 주장하지 않는다.
- Product completion에는 real semantic-path evidence가 있다.
- Mock support에 명확한 deletion boundary가 있다.
