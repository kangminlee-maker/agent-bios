---
guide_id: llm-capability-boundary-patterns
parent: llm-capability-boundary
language: ko
status: active
use_when:
  - submit tool, runtime-owned field, output channel lock을 구현할 때
  - provider strict schema와 runtime allowed-set validation 중 선택할 때
  - grounding, provenance, projection, evidence-index 메커니즘을 구현할 때
  - security, side effect, persistence, idempotency, retry policy를 다룰 때
  - schema single source of truth와 migration을 관리할 때
---

# LLM And Capability Boundary: Enforcement Patterns

이 가이드는
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/llm-capability-boundary.md`의
scoped extension이다. Boundary doctrine이 runtime/tools와 capability surface에
배정한 enforcement 메커니즘을 구현할 때 사용한다.

## Structural Enforcement Patterns

### Bounded Submit Tool

LLM이 machine-consumed artifact의 semantic content를 제공해야 할 때 submit tool을
사용한다.

Pattern:

1. Runtime이 좁은 schema의 submit tool을 만든다.
2. LLM은 bounded semantic field만 제출한다.
3. Runtime은 unknown field와 runtime-owned field를 reject한다.
4. Runtime은 enum, ref, grounding, policy constraint를 검증한다.
5. Runtime이 canonical artifact를 쓴다.
6. Downstream consumer는 runtime artifact만 읽는다.

이는 LLM에게 "valid YAML을 써라"라고 요청하는 것보다 강하다. LLM은 여전히
semantic judgment를 수행하지만 shape, path, id, metadata, serialization은
runtime/tools가 소유한다.

Illustrative implementation:

```ts
type FindingSubmitPayload = {
  findings: Array<{
    target: string;
    claim: string;
    evidence_refs: string[];
    rationale?: string;
  }>;
};

function submitFindings(payload: FindingSubmitPayload, ctx: RuntimeContext) {
  rejectUnknownFields(payload, ["findings"]);
  rejectRuntimeOwnedFieldsDeep(payload, [
    "schema_version",
    "session_id",
    "lens_id",
    "candidate_id",
    "source_ref",
    "output_path",
  ]);

  validateEvidenceRefs(payload.findings, ctx.allowedEvidenceRefs);

  const artifact = {
    schema_version: 1,
    session_id: ctx.sessionId,
    lens_id: ctx.lensId,
    findings: payload.findings.map((finding, index) => ({
      ...finding,
      candidate_id: stableCandidateId(ctx, finding, index),
      source_ref: `${ctx.outputPath}#candidate-${index + 1}`,
    })),
  };

  atomicWriteYaml(ctx.outputPath, validateFindingArtifact(artifact));
}
```

### Runtime-Owned Deterministic Fields

Runtime/tools가 derive할 수 있는 deterministic field는 LLM authority 밖에 둔다.

Common runtime-owned fields:

- `schema_version`
- `session_id`
- `lens_id`
- unit identity가 이미 결정하는 `issue_id`
- stable runtime assignment가 가능한 `candidate_id`, `finding_id`, `cause_id`
- artifact path와 local id에서 derive 가능한 `source_ref`
- `output_path`
- validation scaffolds
- artifact envelope and serialization
- source snapshot id, source hash, trust tier, permission scope, staleness
  metadata

LLM은 selection 자체가 semantic task일 때만 known id를 선택할 수 있다. Runtime이
이미 아는 id라면 LLM이 제출하지 않는다.

Stable ordering만으로는 retry, batching, dedupe, parallelism에서 id가 깨질 수
있다. Run 간 안정성이 필요하면 normalized hash, idempotency key, persisted
sequence table, prior-run mapping을 사용한다.

### Accepted Output Channel Lock

Structured output이 중요하면 submit path를 유일한 accepted path로 만든다.

Examples:

- Canonical artifact write는 runtime submit handling을 통해서만 일어난다.
- Text output은 diagnostic으로 capture할 수 있지만 artifact truth가 되지 않는다.
- Contract가 tool-capable structured-output path를 요구하면 text-only executor는
  reject한다.
- Runtime-owned canonical path는 LLM-written scratch path와 격리한다.

이는 "올바른 format을 사용해 달라"를 "이 channel만 accepted된다"로 바꾼다.
Read-only filesystem route는 하나의 구현 방식이다. 더 깊은 원칙은 canonical
artifact truth가 runtime-controlled path를 통해서만 writable해야 한다는 점이다.

### Provider Strict Schema For Short Closed Values

Provider strict schema는 짧고 안정적인 closed vocabulary에 유용하다. 그러나
artifact authority는 아니다.

Good strict-schema candidates:

- `severity`
- `stance`
- `issue_role`
- `judgment_state`
- `impact_kind`
- `timing_class`
- `closure_class`
- LLM이 선택해야 하는 짧고 bounded된 `issue_id`
- confidence 또는 relation enum

Runtime enum validation도 유지한다. Provider support는 model, route, schema
subset, schema size, refusal/incomplete behavior에 따라 달라진다. Strict schema에
의존하기 전에 route를 probe하고, support가 없으면 의도적으로 fail하거나
downgrade한다.

Sensitive data, long source text, private ref, user-specific secret은 schema
name, enum value, const value, regex pattern 밖에 둔다. Schema text 자체도 data다.

### Runtime Allowed-Set Validation For Long Refs

Long ref, source-derived ref, quoted snippet, path-heavy string은 provider schema
안에서는 string으로 두고 runtime allowed-set validation으로 검증하는 편이 낫다.

Good runtime allowed-set candidates:

- `evidence_refs`
- quote를 포함하는 source ref
- line text를 포함하는 ref
- generated artifact anchor
- source snippet
- long path-like value
- user- 또는 tenant-scoped id

이 방식은 provider schema를 robust하게 유지하면서 fail-loud validation을 보존한다.
LLM은 string을 emit할 수 있지만, runtime은 computed allowed set 밖의 string을
reject한다.

### Grounding And Provenance

Grounding은 source truth가 decidable할 때만 hard gate로 사용한다.

Good grounding-blocked candidates:

- evidence anchor가 known source span으로 resolve된다
- quoted source text가 cited file 안에 존재한다
- ref가 known artifact와 anchor set에 속한다
- count, id, relation coverage를 deterministic하게 check할 수 있다

False positive 가능성이 큰 free prose에는 warning-style audit을 유지한다.
Free-text synthesis citation audit은 유용할 수 있지만, verifier가 충분히
reliable해지기 전에는 hard gate가 되지 않는다.

Grounding은 provenance가 아니다. Quote가 source span과 match해도 source는 stale,
unauthorized, poisoned, incomplete, low-trust일 수 있다. Provenance는 별도로
track한다.

- `source_snapshot_id`
- source hash 또는 version
- ingest time
- permission scope
- trust tier
- retrieval policy
- staleness policy
- 필요한 경우 poisoning 또는 integrity check

Production quote check는 robust해야 한다. Whitespace와 Unicode를 normalize하고,
stable offset 또는 line anchor를 사용하고, duplicate span을 disambiguate하고,
source snapshot id를 기록한다.

### Deterministic Projection

Artifact가 upstream artifact의 direct projection이면 runtime-owned로 만든다.

Examples:

- Lens sidecar에서 만든 finding ledger.
- Individual stance response에서 만든 issue stance matrix.
- Issue synthesis response에서 만든 synthesis ledger.
- Canonical issue artifact에서 만든 review record count와 classification summary.

Semantic design이 필요할 때 LLM이 projection rule을 정의할 수 있다. Runtime/tools가
그 rule을 적용한다.

Projection-first context는 downstream LLM unit이 큰 raw artifact를 다시 읽게 하는
것보다 나은 경우가 많다. Authoritative upstream artifact에서 `proposed_action`,
`issue_statement`, `domain_threshold_used`, `singleton_reason`, `shared_cause`,
dependency, bounded source ref 같은 compact semantic field를 추가한다.

Projection은 중요한 evidence를 숨길 수도 있다. Coverage, omitted evidence,
projection이 불충분할 때의 fallback trigger를 track한다.

### Human View From Machine Artifact

Machine artifact에 human-readable view도 필요하면, 가능하면 machine artifact에서
human view를 생성한다.

Pattern:

1. LLM이 semantic payload를 submit한다.
2. Runtime이 validated machine sidecar를 쓴다.
3. Runtime이 sidecar에서 markdown 또는 HTML을 render한다.
4. Machine consumer는 sidecar를 읽는다.
5. Human은 rendered view를 읽는다.

이 방식은 LLM에게 두 output의 일관성을 유지하게 하지 않는다. Rendered view도
untrusted output으로 취급한다. HTML을 escape하고, link를 sanitize하고, unsafe
markup을 제거하고, model- 또는 source-generated content를 실행하지 않는다.

### Evidence Index

반복적인 semantic review에 exact하고 re-checkable한 evidence가 필요하면 evidence
index를 사용한다.

Preferred shape:

- row당 하나의 claim
- row당 하나의 file path
- row당 numeric line, byte offset, stable anchor 중 하나
- multi-target claim은 여러 row로 split
- prose locator는 runtime/tools로 exact ref로 변환
- retrieval이 관여하면 source snapshot, permission scope, trust tier 포함

LLM은 semantic judgment에 evidence index를 사용한다. Runtime/tools는 deterministic
re-verification에 사용한다.

## Security And Side Effects

Prompt text, retrieved content, tool result, LLM output, rendered view, external
API response는 다음 boundary에 대해 validate되기 전까지 untrusted로 취급한다.

Required rules:

- Source document와 tool result는 data로 취급하고 authority로 취급하지 않는다.
- LLM output은 code, shell, SQL, browser, renderer, API, downstream agent로
  전달하기 전에 validate하고 sanitize한다.
- Tool과 route에는 least privilege를 사용한다.
- Side effect를 read-only, reversible write, external write, external send,
  financial/legal action, destructive action으로 classify한다.
- High-impact action에는 preview, diff, approval, downstream authorization을
  요구한다.
- Tool call, argument, policy decision, result를 audit용으로 log한다.
- Loop, scan, spend, mutate, network call을 할 수 있는 tool에는 rate limit과
  timeout을 둔다.
- 모든 authorization/allowlist entry는 boot나 deploy 시점에 live runtime key
  space에 대해 resolve한다 — format validation은 well-formedness만 증명하며,
  mis-formatted entry는 모든 deploy check를 통과하면서도 자기 route class
  전체를 조용히 거부할 수 있다. 수정은 explicit negative control과 redeploy된
  system을 통한 live end-to-end call로 검증한다.

LLM은 action을 recommend할 수 있다. Capability surface가 그 action이 available,
permitted, confirmed, accepted되는지 결정한다.

## Persistence, Idempotency, And Retry

Artifact write는 atomic하고 auditable해야 한다.

Preferred persistence pattern:

1. Accepted payload와 runtime-owned field로 memory 안에서 artifact를 만든다.
2. Schema, ref, policy, grounding을 validate한다.
3. Temp path에 쓴다.
4. Persisted bytes 또는 checksum을 verify한다.
5. Atomically rename하거나 canonical로 register한다.
6. Artifact lineage와 validator result를 기록한다.

Retry policy는 다음을 구분해야 한다.

- transient provider failure
- invalid structured payload
- unsupported ref
- grounding failure
- permission 또는 policy failure
- partial persistence failure
- side-effect uncertainty

Pure generation과 validation에는 retry가 안전하다. External side effect에는
자동으로 안전하지 않다. 필요한 경우 idempotency key, lock, duplicate detection,
compensation plan을 사용한다.

같은 record 위에서 다시 돌 수 있는 stage는 자기가 쓰는 field를 읽어서는 안 된다.
Re-run(재분류, backfill, retry)에서 출력이기도 한 입력 field는 model에게 자신의
이전 답을 다시 먹이고, 값은 source에서 조용히 drift한다. 포착한 원본은 immutable하게
두고, 파생된 값은 자기 field에 쓰며, `original ?? current`는 설계가 아니라
migration으로 다룬다. 그 sibling들을 감사한다: selection rule이 덮어써진 행을
건너뛰기 때문에만 무해한 것은 잠재된 사례다.

## Single Source Of Truth And Schema Evolution

Hybrid enforcement는 drift risk를 만든다. 하나의 constraint가 prompt text,
submit schema, provider schema, runtime validator, allowed-set builder, artifact
validator, test에 동시에 나타날 수 있다.

각 stage에는 하나의 canonical source를 정하고 나머지를 derive한다.

- submit tool schema
- provider schema
- runtime validator
- allowed-set validator
- artifact validator
- prompt contract
- tests
- migration sample artifacts

아직 derive할 수 없으면 authoritative source를 명시하고 schema/validator drift를
잡는 test를 추가한다.

Versioned artifact에는 migration policy가 필요하다.

- schema version bump가 필요한 변경
- backward/forward compatibility expectation
- old artifact용 migration script 또는 reader
- consumer contract tests
- deprecation window
- sample artifact updates
