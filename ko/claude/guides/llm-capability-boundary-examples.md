---
guide_id: llm-capability-boundary-examples
parent: llm-capability-boundary
language: ko
status: active
use_when:
  - boundary와 field-authority 설계의 worked precedent가 필요할 때
  - sidecar submit, structured-output hybrid, MCP schema projection, projection enrichment와 유사한 사례를 설계할 때
---

# LLM And Capability Boundary: Worked Examples

이 가이드는
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/llm-capability-boundary.md`의
scoped extension이다. 각 example은 problem, structural path, learning을 기록한다.

## Lens Sidecar To Finding Ledger

Problem:

- Lens markdown이 heterogeneous했다.
- Finding-ledger LLM이 noisy markdown을 다시 읽고 normalize해야 했다.
- Runtime이 id, ref, artifact path, validation scaffold를 강하게 보장하지 못했다.

Structural path:

- `submit_lens_findings`를 batched submit tool로 추가한다.
- LLM은 semantic finding field를 한 번 submit한다.
- Runtime은 `round1/{lens}.findings.yaml`을 쓴다.
- Runtime은 `session_id`, `lens_id`, `candidate_id`, `source_ref`,
  `human_output_ref`, validation, YAML serialization을 소유한다.
- Optional markdown은 sidecar에서 render한다.
- 모든 lens output이 sidecar가 되면 runtime이 `finding-ledger.yaml`을
  deterministic하게 쓴다.

Learning:

- Machine artifact는 LLM prose formatting에 의존하지 않는다.
- Batched submit은 partial-output과 per-call overhead를 줄인다.
- Runtime이 artifact를 소유하면 prompt packet이 audit packet이 될 수 있다.
- 이 contract에는 tool-capable route가 필요하며 text-only fallback은 fail
  clearly해야 한다.

## Structured Output Hybrid

Problem:

- Provider strict schema는 short enum을 enforce할 수 있다.
- Long evidence ref는 quote나 source text를 포함해 provider enum schema를 brittle하게
  만들 수 있다.
- Pure post-hoc validation은 shape는 잡지만 meaning은 보장하지 않는다.

Structural path:

- Short closed field에는 provider strict schema를 사용한다.
- `evidence_refs`는 provider schema에서 string array로 유지한다.
- Prompt packet projection에서 runtime allowed ref를 계산한다.
- Unsupported ref는 submit time에 reject한다.
- Artifact가 runtime submit handling으로만 생성되는 route를 사용한다.

Learning:

- Strict schema는 provider support와 schema shape가 적합한 곳에서만 real
  enforcement다.
- Long ref에는 runtime allowed-set validation이 필요하다.
- 각 field에는 하나의 primary authority와 충분한 layered check가 필요하다.

## MCP-Projectable Schema Boundary

Problem:

- MCP/Claude tool surface에는 단순하고 직접 유효한 object schema가 필요하다.
- Internal artifact schema는 더 풍부한 JSON Schema composition이 복잡도를
  줄일 수 있다.
- 모든 repository schema를 tool schema처럼 취급하면 internal design을 과하게
  제약할 수 있고, composed schema를 그대로 노출하면 tool host가 깨질 수 있다.

Structural path:

- Pattern-valid canonical tool name을 노출한다: `sheets_read` 같은
  `namespace_verb` snake_case를 사용하고 `^[a-zA-Z0-9_-]{1,64}$`를 만족시키며,
  dispatch, audit, allowed-tool config에 catalog name을 재사용하고 catalog
  또는 seed validation에서 강제한다.
- MCP tool `input_schema`와 MCP/Claude tool projection 대상 schema를
  MCP-projectable schema로 취급한다.
- MCP-projectable schema는 explicit field를 가진 direct object schema를
  우선하고 `oneOf`, `anyOf`, `allOf`를 피한다.
- Variant behavior는 operation enum, deterministic dispatch, runtime
  validation, explicit projection adapter 뒤에 둔다.
- Internal-only schema는 composition이 실제로 복잡도를 줄일 때 사용할 수
  있지만, MCP/Claude tool surface에 도달하기 전 compatible direct object
  schema로 projection한다.

Learning:

- Compatibility rule은 모든 internal schema에 대한 universal ban이 아니라
  tool projection boundary에 속한다.
- Tools/code가 projection과 validation을 소유해야 LLM이 incompatible schema
  shape를 실수로 노출할 수 없다.

## Issue Stance Matrix Projection

Problem:

- Compact projection에 later LLM unit이 필요한 action/dependency context가 없었다.
- Later unit이 raw artifact를 다시 읽게 하면 latency와 drift가 증가한다.

Structural path:

- Authoritative upstream artifact에서 action, dependency, threshold, singleton,
  shared-cause, bounded-source-ref field를 runtime projection에 enrich한다.
- Matrix merge는 deterministic하게 유지한다.
- Ref는 allowed source variant에 대해 validate한다.
- Omitted context가 중요할 수 있으면 projection coverage와 fallback을 track한다.

Learning:

- Projection-first enrichment는 LLM context를 확장하는 것보다 나은 경우가 많다.
- Later judgment가 semantic context에 의존하면 deterministic projection에 그
  context를 추가한다.
- Projection quality에는 schema check뿐 아니라 coverage check도 필요하다.
