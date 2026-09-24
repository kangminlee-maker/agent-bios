---
guide_id: llm-capability-boundary
language: ko
status: active
use_when:
  - structured output을 설계할 때
  - runtime-owned artifact를 변경할 때
  - submit tool이나 accepted output channel을 정의할 때
  - LLM semantic judgment와 deterministic execution을 분리할 때
  - validator, grounding check, capability-surface constraint를 설계할 때
  - tool use, retrieval, side effect, artifact persistence를 설계할 때
core_rules:
  - instruction은 의도한 작업, semantic criteria, completion criteria를 설명한다
  - capability surface는 context, tool, permission, route, path, output channel, validator, gate, approval로 제약을 집행한다
  - 각 field나 operation에는 하나의 primary authority를 먼저 정하고 필요한 layered check를 추가한다
  - LLM은 semantic judgment, rationale, tradeoff, evidence reduction을 담당한다
  - runtime/tools는 deterministic execution, artifact creation, merge, serialization, validation, persistence, test를 담당한다
  - machine-consumed artifact는 submit tool이나 equivalent constrained channel을 통해 생성한다
  - provider strict schema는 execution aid이며 artifact truth의 source가 아니다
  - tool input, tool result, retrieved content, rendered view는 validate 또는 sanitize되기 전까지 untrusted로 취급한다
field_assignment:
  short_closed_values: provider_closed_selection_plus_runtime_enum_validation
  runtime_known_ids: runtime_owned_unless_selection_is_semantic
  long_refs_and_source_snippets: runtime_allowed_set_validation
  evidence_anchors: grounding_blocked_when_source_truth_is_decidable
  source_provenance: runtime_owned_snapshot_hash_scope_and_trust_tier
  open_rationale: free_generation_with_shape_checks
  side_effects: capability_surface_plus_policy_gate
  artifact_envelope_and_serialization: runtime_only
verification_focus:
  - accepted output channel이 명시되어 있다
  - LLM이 free prose로 canonical machine artifact를 만들 수 없다
  - runtime-owned field와 unknown field는 fail-loud한다
  - provider schema limit은 의존하기 전에 확인되어 있다
  - long ref는 provider enum 대신 runtime allowed set으로 검증한다
  - grounding gate는 decidable truth에만 사용한다
  - source trust, permission, staleness, poisoning risk는 quote grounding과 별도로 확인한다
  - side-effect tool은 risk로 분류되고 permission 또는 approval gate를 가진다
  - artifact write는 atomic하고 가능한 경우 idempotent하며 audit 가능하다
  - schema, validator, allowed set, prompt, test는 하나의 authority를 공유하거나 drift-catching test를 가진다
---

# LLM And Capability Boundary Guide

이 가이드는 LLM이 machine-consumed artifact, code, ontology, pipeline output,
review finding, structured document, runtime decision을 생성, 선택, 검증,
요약, 라우팅할 때 사용한다.

핵심은 간단하다. Instruction은 의도한 작업을 설명한다. Capability surface는
유효한 실행 경로가 사용 가능하고, bounded되고, accepted되고, observable하도록
만든다.

Scoped extensions:

- Enforcement 메커니즘 — submit tool, runtime-owned field, output channel
  lock, provider schema 사용, allowed-set validation, grounding과 provenance,
  deterministic projection, security와 side effect, persistence와 retry,
  schema evolution — 은
  `${CODEX_HOME:-$HOME/.codex}/guides/llm-capability-boundary-patterns.md`를
  읽고 사용한다.
- 이 boundary를 적용한 worked case study는
  `${CODEX_HOME:-$HOME/.codex}/guides/llm-capability-boundary-examples.md`를
  읽고 사용한다.

## Core Model

- Instruction은 의도한 작업, semantic criteria, tradeoff, completion criteria를
  설명한다.
- LLM은 semantic work를 수행한다. 예: intent clarification, meaning
  assignment, materiality/causality judgment, rationale writing, option
  comparison, evidence reduction.
- Runtime/tools는 authoritative mechanical work를 수행한다. 예: parsing,
  counting, calculation, API call, deterministic merge, serialization,
  validation, persistence, test, diff comparison.
- Capability surface는 structural constraint를 제공한다. 예: accessible
  context, available tools, permissions, execution routes, artifact paths,
  accepted output channels, validators, retry policy, approval gates, failure
  behavior.
- Downstream system이 소비하는 canonical artifact는 raw LLM prose가 아니라
  runtime/tools가 만든다.

선호하는 프레이밍:

> LLM은 semantic content를 제안할 수 있다. Runtime은 무엇이 artifact truth가
> 되는지 결정한다.

Prompt는 의미를 명확히 하는 데 사용한다. Correctness, reproducibility,
artifact truth, privacy, security, side effect에 영향을 주는 동작은 capability
design으로 제약한다.

## Capability Surface

Capability surface는 LLM이 실제로 수행할 수 있는 action과 runtime이 실제로
accept하는 output의 집합이다. LLM이 규칙을 따르리라 기대하기 전에 surface를
먼저 설계한다.

중요한 lever:

- Accessible context: unit이 inspect할 수 있는 file, ref, row, artifact,
  source snippet, projection, retrieved evidence.
- Available tools: read tool, submit tool, validation tool, search tool, API
  tool, renderer와 input schema.
- Permissions: read-only, workspace-write, denied path, network access,
  sandbox mode, route-specific side effect, user approval.
- Execution routes: tool-capable executor, text-only executor, structured output
  route, direct-call route, deterministic runtime route, human-review route.
- Artifact paths: exact output path, canonical truth location, temp path, denied
  write location.
- Accepted output channels: submit tool call, structured JSON payload, runtime
  projection, generated YAML, markdown view, final prose.
- Validators and gates: schema validation, unknown-field rejection,
  runtime-owned-field rejection, enum validation, allowed-set validation,
  grounding check, provenance check, citation check, static check, E2E check,
  semantic quality gate.
- Retry/fail policy: transient generation failure는 retry하고, route가 required
  contract를 enforce할 수 없으면 fail clearly한다. Contract-failing item은
  loudly reject하고 valid result로 기록하지 않으며, artifact state에 failed
  또는 not-done status를 기록한다. Production path에서는 계속 진행하는 것이
  다음 step이 읽을 것을 contaminate할 때만 — stale하거나 not-reusable한 input,
  valid로 기록되려는 contract-failing value, outcome을 알 수 없는 external
  write — 전체 run을 halt하고, 그 외에는 loudly warn하며 계속 진행해 다음
  run이 not-done work를 이어받는다.
- Observability: prompt packet snapshot, model/provider version, schema hash,
  source snapshot, validator decision, retry reason, artifact lineage.

## Boundary Decision Table

| Need | Primary authority | Preferred mechanism |
|---|---|---|
| User intent 또는 product meaning 명확화 | LLM | Prose reasoning과 decision framing |
| Tradeoff 또는 materiality 선택 | LLM | Evidence로 bounded된 semantic judgment |
| Open rationale 또는 explanation 작성 | LLM | 필요한 경우 shape constraint가 있는 free generation |
| File 또는 fresh fact inspect | Tools/runtime | Search, parse, read, API call, source snapshot |
| Canonical machine artifact 생성 | Runtime | Submit payload plus runtime serialization |
| Id, path, metadata, timestamp 할당 | Runtime | Runtime-owned fields |
| 명시적 rule 기반 artifact merge | Runtime | Deterministic projection 또는 merge |
| Syntax, schema, ref, count 검증 | Runtime | Parser, schema, allowed set, tests |
| Source-span truth 확인 | Runtime | Decidable할 때 grounding gate |
| Source trust 또는 completeness 판단 | Runtime plus policy | Provenance, permission, staleness, trust tier |
| Forbidden action 방지 | Capability surface | Unavailable, invalid, unaccepted로 만든다 |
| Side effect 수행 | Capability surface plus policy | Risk class, permission, approval, audit log |
| Structured output 필요 | Capability surface plus runtime | Submit tool 또는 equivalent constrained channel |

## Structured Output Field Assignment

Artifact field마다 하나의 primary authority를 정한다. Cross-field invariant,
security policy, privacy policy, artifact-level consistency에는 layered check를
추가한다.

| Field kind | Primary mechanism |
|---|---|
| Short closed values | Provider closed selection plus runtime enum validation |
| Runtime-known ids | Runtime-owned; provider enum only when LLM must select |
| Long refs and source snippets | Runtime closed validation; provider enum excluded |
| Evidence anchors | Grounding-blocked when source truth is decidable |
| Source provenance | Runtime-owned snapshot, hash, scope, trust tier, staleness |
| Open materiality or causal rationale | Free generation with structured shape checks |
| Side-effect decision | Capability surface plus policy and approval gate |
| Artifact envelope and serialization | Runtime only |

목표는 모든 field를 provider strict schema에 밀어 넣는 것이 아니다. 각 field에
충분히 강한 가장 약한 mechanism을 사용하는 것이다.

## Generate-And-Validate

Generate-and-validate는 LLM이 하나의 accepted output channel을 통해 payload를
생성하고, runtime이 생성 후 validate하는 방식이다.

유용한 경우:

- field가 open하고 expressive하다
- iteration speed가 중요하다
- 현재 step에서는 shape correctness가 충분하다
- validator failure를 안전하게 retry할 수 있다

보장하는 것:

- expected top-level shape
- unknown field 없음
- runtime-owned field 없음
- parseable structured payload
- runtime이 쓴 canonical artifact

그 자체로 meaning을 보장하지는 않는다. Validator나 review gate가 잡지 않으면
well-formed payload도 unsupported claim, wrong ref, stale source, unauthorized
source, unsafe link, semantically wrong category를 포함할 수 있다.

## Construct-And-Verify

Construct-and-verify는 runtime이 artifact construction을 소유하고, 가능한 경우
closed choice를 제공하고, grounded claim을 검증하는 방식이다.

유용한 경우:

- LLM call 전에 option을 enumerate할 수 있다
- ref 또는 anchor를 source truth에 대해 check할 수 있다
- invalid value가 impossible하거나 fail-loud해야 한다
- artifact authority 또는 downstream impact가 높다
- side effect에 permission, preview, approval이 필요하다

비용:

- runtime이 option space를 enumerate해야 한다
- validator가 product-critical code가 된다
- 잘못된 constraint가 정답을 배제할 수 있다
- nuanced judgment가 가장 가까운 bucket으로 discretize될 수 있다
- dependency가 더 sequential해진다

LLM judgment 전체를 대체하는 blanket rule이 아니라 field 또는 operation 단위로
사용한다.

## Design Procedure

새 LLM-assisted artifact를 설계하거나 기존 artifact를 수정할 때 이 절차를 사용한다.

1. Canonical artifact와 downstream consumer를 식별한다. Consumer가 이미 있다면 schema만이
   아니라 그 **수용 술어(acceptance predicate)** 를 읽는다: schema는 어떤 필드가 나올 수
   있는지를 말하고, 술어는 어떤 조합이 인정되는지를 말한다. Schema만 보고 설계한 producer는
   유효하지만 결코 수용되지 않는 레코드를 낼 수 있다 — consumer가 대상당 한 레코드로
   판정하는데 사건당 한 레코드를 내는 것이 흔한 형태이고, 필드 단위 검사는 전부 통과한다.
2. Field를 semantic field, deterministic field, provenance field,
   side-effect operation으로 나눈다.
3. 각 field 또는 operation에 하나의 primary authority를 정한다.
4. Accepted output channel을 결정한다.
5. Accessible context와 available tools를 task에 맞게 shaping한다.
6. Deterministic field를 runtime-owned로 만든다.
7. 선택한 model과 route에서 실제로 지원되는 provider schema constraint를 확인한다.
8. Schema와 validator를 하나의 canonical source에서 derive한다.
9. Unknown field, runtime-owned field, unsupported ref, denied action에
   fail-loud check를 추가한다.
10. Truth가 decidable한 곳에만 grounding check를 추가한다.
11. Source trust, permission, freshness, integrity에 provenance check를 추가한다.
12. Failure kind와 side-effect class별 retry/fail policy를 결정한다.
13. Artifact persistence를 atomic하고 auditable하게 만든다.
14. Invalid value, unsupported ref, route rejection, grounding failure, policy
   failure, schema drift, artifact persistence에 focused test를 추가한다.
15. 어떤 check가 shape, wiring, source grounding을 증명하고 어떤 check가
   semantic quality를 추정만 하는지 report한다.

## Verification Checklist

- LLM은 free prose로 canonical machine artifact를 만들 수 없다.
- Accepted output channel이 명시되어 있다.
- Structured output은 submit tool 또는 equivalent constrained channel을 사용한다.
- Runtime-owned field는 LLM이 submit하면 reject된다.
- Unknown field는 fail loudly한다.
- Short closed value는 지원되는 곳에서는 provider enum을 사용하고 모든 곳에서
  runtime enum을 사용한다.
- Provider schema limit과 refusal/incomplete behavior는 선택한 route에 대해
  test되어 있다.
- Long ref는 quote-heavy, private, tenant-scoped, source-derived이면 provider enum이
  아니다.
- Runtime allowed-set check는 unsupported ref를 reject한다.
- Grounding gate는 decidable truth에만 사용한다.
- Source trust, permission, freshness, integrity는 source-span grounding과 별도로
  check한다.
- Tool input, tool result, retrieved content, LLM output, rendered view는 각
  boundary에서 untrusted로 취급한다.
- Side-effect tool은 risk class, permission, approval gate를 가진다.
- Human view는 가능하면 machine artifact에서 derive하고 rendering 전에 sanitize한다.
- Artifact write는 atomic하거나 명확한 recovery path를 가진다.
- Retry는 failure class에 대해 safe, idempotent이거나 명시적으로 blocked된다.
- Schema, validator, allowed set, prompt, test는 하나의 authority를 공유하거나
  drift-catching test를 가진다.
- Observability는 prompt packet, model/provider version, schema hash, source
  snapshot, validator decision, retry reason, artifact lineage를 capture한다.
