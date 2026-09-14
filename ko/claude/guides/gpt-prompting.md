---
guide_id: gpt-prompting
language: ko
status: active
use_when:
  - gpt 계열 model을 위한 prompt, packet, 또는 tool 설명을 작성할 때
  - Claude main에서 gpt 쪽으로 cross-family review를 dispatch할 때
  - gpt subagent에 prompt하거나 main이 Codex일 때 자기 자신에게 prompt할 때
  - 구세대 gpt model용으로 작성된 prompt를 이식할 때
  - gpt 작업의 reasoning-effort 수준을 정할 때
core_rules:
  - 공유 recipe와 실제 대상 model의 section만 적용한다 — GPT-5.6과 GPT-6 Astra는 prompting 필요가 다르다
  - 경로가 아니라 목적지를 기술한다 — 결과, 성공 기준, 실제 제약, 사용 가능한 근거를 밝힌다
  - 동작을 바꾸는 것만 남긴다. 반복 서술, style 규칙, 동작을 바꾸지 않는 예시는 잘라낸다
  - 포괄적인 ALWAYS/NEVER 대신 각 선택이 적용되는 조건을 명시한 결정 규칙을 쓴다
  - effort를 올리기 전에 prompt를 고친다 — 출력이 약한 것은 대개 성공 기준, 의존 규칙, tool 라우팅 규칙, 또는 검증 루프가 빠진 탓이다
  - 구세대 gpt model에서 가져온 prompting 습관은 token을 쓰고 정확도까지 해칠 수 있다
derived_at: 2026-09-07
source_pins:
  - doc: prompt-guidance-gpt-5p6
    sha256: 46181efec9fd1160ef537b0379282a14c1ba32380f2f8149a805128253c1115a
    pinned_at: 2026-09-07
  - doc: model-guidance-gpt-6-astra
    sha256: 2a59b26078e001a4e4e3da10693e80ad5ee1c02cbe472afa6b682308f27b8b22
    pinned_at: 2026-09-07
targets:
  - gpt-6-astra
  - gpt-5.6-sol
  - gpt-5.6-terra
  - gpt-5.6-luna
verification_focus:
  - prompt 변경은 눈으로 보는 대신 같은 eval을 다시 돌려 검증한다
  - 제거는 한 묶음씩 해서 변화의 원인을 특정할 수 있게 한다
  - effort 변경은 대상 model이 지원하는 설정을 쓰고 baseline과 비교한다
  - model별 조언은 autonomy, writing style, delegation, verification을 포함해 각자의 고정 source와 대조한다
---

# GPT Prompting Guide

이 guide는 전역 Coding Guidelines의 범위 확장이다. gpt tier model을 위한 prompt를
작성할 때 사용한다 — cross-family로 dispatch하는 review packet, subagent brief, 또는
main이 Codex일 때 main 자신의 지시.

아래 공유 recipe와 실제 대상 model의 section을 함께 쓴다. main과 다른 model을 쓰는
subagent일 때도 prompt를 받는 model이 적용 section을 정한다. 이 section들은 기존
permission policy 안에서 prompt를 조정할 뿐, tool permission이나 approval requirement를
바꾸지 않는다.

| Target | Apply | Pinned source |
| --- | --- | --- |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | GPT-5.6 | `prompt-guidance-gpt-5p6` |
| `gpt-6-astra` | GPT-6 Astra | `model-guidance-gpt-6-astra` |

## GPT-5.6

- **먼저 단순화한다.** 결과, 제약, 근거, 완료 기준을 밝힌 뒤 model이 경로를 선택할
  여지를 둔다. 동작하는 prompt에서 시작해 반복 지시, 예시, 관련 없는 tool을 한 묶음씩
  제거하고 같은 eval을 다시 돌린다. 동작을 바꾸는 process 지시는 남긴다.
- **간결함을 조정한다.** GPT-5.6은 GPT-5.5보다 더 간결해지는 경향이 있다. 광범위한
  간결성 지시는 그대로 가져오기 전에 다시 시험한다. 답변을 지나치게 얇게 만들 수 있다.
  필요한 결과를 만들어 낸다면 그 지시는 유지한다.
  API가 `text.verbosity`를 제공하면 기본 상세 수준에는 그것을 쓰고, 과제의 길이, 구조,
  필수 내용에는 prompt를 쓴다. 근거, 결정, 유의점, 다음 행동보다 먼저 반복을 줄인다.
- **협업을 tone과 분리해 정의한다.** 언제 질문하고, 가정하고, 주도적으로 행동하고,
  불확실성을 설명할지 간결히 명시한다. 점검이나 계획 요청과 구현 요청을 구분한다.
  범위 안의 통상 작업이 불필요하게 멈추지 않도록 안전한 local 행동과 approval 경계를
  한 번 명시한다.
- **prompt 다음에 effort를 조정한다.** 현재의 유효 effort를 baseline으로 보존한 뒤,
  대표 과제에서 그것과 지원되는 한 단계 낮은 수준을 비교한다. 지연 시간이 중요하고
  품질이 유지되면 `low`를 쓴다. `medium`은 균형 잡힌 시작점이다. eval이 이득을 보일
  때 `high`/`xhigh`를 쓰고, `max`는 가장 어려운 품질 최우선 작업에 남겨 둔다. 활성
  model과 host에서 사용 가능 여부를 확인한다.

## GPT-6 Astra

- **주도성과 끝까지 수행하기.** Astra는 입력이 결과를 크게 바꿀 수 있을 때 질문할
  가능성이 더 높다. 행동 요청에는 context에서 통상 세부를 추론하고, 답하기 전에 검증을
  포함한 승인된 작업을 완료하라고 prompt한다. 계획이나 계속하겠다는 제안은 행동 요청을
  완료하지 않는다. 빠진 정보가 결과를 바꿀 때 질문하고, 기다리는 동안 독립적인 승인된
  작업은 계속한다. 이후 단계에 approval이 필요하면 먼저 구체적이고 검토 가능한 결과를
  준비한다. 기존 permission 경계를 지키고 가정적 위험만을 근거로 approval 단계를
  추가하지 않는다.
- **지시와 skill 민감성.** 불명확하거나 충돌하는 지침이 있는지 로드된 skill과
  instruction file을 점검한다. 더 높은 우선순위 지시와 permission 제약 안에서 명시적
  사용자 지시가 skill workflow 선호보다 우선하게 한다. skill이 멈춤, approval 요청,
  또는 미완료 작업을 초래하면 정확한 skill file을 식별하고 링크하며, 해당 규칙을 인용하고
  그것이 명시적인지 해석인지 설명한다. 선택 사항인 guideline을 새 requirement로 바꾸지
  않는다.
- **Writing style.** Astra는 상세한 응답, 목록, 표, 반복되는 표현으로 기우는 경향이
  있다. 독자에 맞춘 원하는 길이와 구조를 지정한다. 평문에는 간결한 문단, 익숙한 단어,
  능동적인 동사, 핵심부터 제시하도록 요청한다. 비교나 순서에 도움이 될 때 목록을 쓰고,
  결과를 평가하는 데 필요한 기술 세부는 남긴다. GPT-5.6의 간결성 편향을 가정하지 말고,
  정형화된 표현이나 틀에 박힌 대조 표현이 반복될 때 이를 명시한다.
- **Subagent delegation.** Astra는 workflow가 요구하는 것보다 delegation을 덜 할 수
  있다. 독립 작업을 언제 delegate할지, 의도한 병렬성의 정도, 각 subagent의 범위,
  작업을 local에 둘 때를 명시한다. 기존 spawn gate, 사용 가능한 seat, budget을 쓴다.
  능동적으로 하라는 일반 지시만으로는 delegation을 정하지 못한다. 정확한 간격을 갖춘
  읽기 쉬운 inter-agent message를 요구한다.
- **Testing and verification.** Astra는 작은 코딩 변경을 과도하게 test할 수 있다.
  관련 check와 완료 기준을 명시한다. 되돌릴 수 있고 영향이 작은 구현을 그대로 되풀이하는
  test는 피한다. 요구된 check를 완료하고, 새 편집, 실패, 또는 미해결 우려가 뒷받침할
  때만 이를 넓히거나 다시 실행한다. 이 조정은 요구된 repository gate와 실제 변경된
  동작의 validation을 보존한다.
- **Reasoning effort.** Astra는 `none`을 지원하지 않는다. `none` 또는 `minimal`에서
  prompt를 옮길 때는 `low`로 시작해 결과를 비교한다. 그 밖에는 현재 유효 effort를
  보존한다. 계열 전체의 effort ladder를 재사용하지 말고 활성 model과 host에서 지원하는
  설정을 확인한다. effort를 높이기 전에 빠진 성공 기준, 의존 규칙, 또는 검증 루프를
  고친다.

## Shared prompt recipe

이 순서로 조립하되, 산출물을 바꾸지 않을 block은 뺀다.

- `Role`과 `Personality` — 누가 어떤 어조로 행동하는가. 출력이 달라지지 않으면
  personality는 뺀다.
- `Goal`과 `Success criteria` — 결과, 그리고 완료를 판정하는 기준. 이 block이 token
  값어치가 가장 크므로 먼저 쓴다. 기준을 못 쓰겠다면 그 prompt는 아직 준비된 게 아니다.
- `Constraints` — 지켜야 할 안전, 비즈니스, 범위 한계. 실제 제약만 둔다. 선호는 output
  shape에 넣거나 아예 넣지 않는다.
- `Tools` — 과제에 필요한 것만 둔다. 각 설명은 무엇을 하는지, 언제 쓰는지, 중요한 반환
  field, 오류 동작을 밝힌다.
- `Output` — 산출물 형태. `Stop rules` — 언제 loop를 멈추고 답할지.

## When to add blocks

- Coding and debugging: 변경 뒤 실행할 validation을 명시한다 — 바뀐 동작에 대한
  targeted test, type/lint check, build, 최소 smoke test. 편집 전 선행 조회를 요구한다.
- Review: 일반 규칙을 포함하고 근거 기준과 verdict 형태를 명확히 한다. 기준이 없는
  reviewer는 그럴듯하게 들리는 finding을 기본값으로 삼는다.
- Research and grounded work: 검색해 얻은 source만 인용하고, 인용은 그것이 뒷받침하는
  주장에 붙이며, 추론은 뒷받침된 사실과 구분해 표시한다. 추측하지 말고 답을 좁히거나
  근거 부족을 보고하라고 말한다.
- Write-capable work: 안전한 행동(파일 읽기, 코드 편집, test 실행)을 명시하고 외부 쓰기,
  파괴적 행동, 범위 확장에는 확인을 요구한다.
- Implementation plans: 요구사항, 명명된 resource, 상태 전이, validation check, 실패
  동작, privacy/security, 미해결 질문.

## How to choose prompt shape

- 자기완결적 packet을 가진 하나의 제한된 질문 → hermetic 단일 실행. review의 기본값이다.
- 독립적인 작업 흐름으로 나뉘는 작업 → fan-out. 독립적인 읽기는 병렬화하고 의존 단계는
  순차로 둔다.
- 위 대상 model의 section과 활성 model 및 host가 실제로 지원하는 설정으로 reasoning
  effort를 고른다.
- 긴 history를 재개하기보다 자기완결적 packet을 선호한다. 추론하기도 cache하기도 더
  저렴하다.

## Programmatic tool calling

코드가 여러 tool 결과를 처리해 훨씬 작은 구조화 결과를 돌려주는 제한된 stage다.
핵심 조건은 병렬성이 아니라 **축소**다. 여러 호출, 병렬 호출, 의존 호출만으로는 이를
정당화하지 못한다.

- filtering, joining, sorting, ranking, deduplication, aggregation; 여러 유사 record에
  걸친 batching; 반복되는 결정적 validation; compact schema로 줄일 수 있는 큰 구조화
  결과에 쓴다.
- 한 호출이면 충분할 때, 중간 출력이 이미 작을 때, 각 결과가 다음 결정을 바꿀 수 있을
  때, 행동에 approval이 필요할 때, 답변이 citation이나 native artifact를 보존해야 할 때,
  또는 호출 사이에 의미적 판단이 놓일 때는 direct call을 선호한다.
- 일반적인 "programmatic tool calling을 효율적으로 사용하라"는 지시는 아무것도 하지
  않는다. 제한된 stage, 적격 tool, output schema, retry limit, stop condition, direct
  judgment로 되돌아갈 handoff를 명시한다. 두 경로가 모두 필요하면 handoff 하나를
  정의하고 경로를 바꾸거나 완료한 작업을 반복하지 말라고 말한다.
- **두 출력을 모두 test한다.** 프로그램 결과와 최종 assistant message는 별개다.
  프로그램이 올바른 record를 돌려도 message에서 필수 field, citation, 또는 유의점을
  빠뜨릴 수 있다.
- 같은 과제에서 두 경로를 비교하고, 응답이 기존 eval을 여전히 통과할 때만 더 낮은
  token/latency/cost를 개선으로 센다.

## Working rules

- 한 실행에 하나의 명확한 과제와 명시적 output contract를 둔다.
- **조립된 prompt에 모순이 없는지 읽는다.** 이 tier는 prompt contract를 면밀히
  따르므로, 서로 어긋나는 두 규칙은 규칙 하나가 빠진 것보다 더 불안정하게 만든다.
  더 많은 지시가 더 안전하다는 직관과 반대다.
- 각 authority 규칙은 한 번만 쓴다. "먼저 물어라", "변경하지 마라", "approval을
  기다려라"를 반복하면 안전하고 예상되는 행동에도 approval 요청이 생긴다.
- 오래 가는 과제에서는 현재 작업 layer — research, design, implementation, review,
  external coordination — 를 명시해 model이 layer를 조용히 넘나들지 않게 한다.
- 지속된 reasoning은 공짜 최적화가 아니다. 목표와 우선순위가 유지되는 동안에는 도움이
  되지만, 바뀌고 나면 낡은 reasoning은 token을 더하고 model을 폐기된 접근에 붙잡아
  둔다. 매 turn이 아니라 milestone에서 compact하고 compacted item은 불투명한 것으로
  취급한다.
- 명시적인 사용자 값을 보존한다. 올바른 값이 암시적일 때는 보편적 기본값이나 keyword
  map을 설치하지 말고 결정 기준을 주어 model이 context나 schema에서 추론하게 한다.
- 재사용 prefix는 안정적으로 유지하고 큰 system prompt의 잦은 변경을 피한다. cache
  breakpoint는 cache 동작을 측정 가능하게 개선할 때만 추가한다. 추가 전에 활성 model의
  cache 사용량과 cost를 점검한다.
- 각 tool 결과 뒤에 핵심 요청에 유용한 근거로 답할 수 있는지 묻는다. 그렇다면 답한다.
- 모든 visual artifact는 마무리 전에 render하고 layout, clipping, spacing, 누락 내용을
  점검한다.

## Prompt assembly checklist

1. 성공 기준을 먼저 쓴다.
2. role, goal, 실제 제약, output shape를 넣는다.
3. 과제에 필요한 tool만, 각각 언제 쓰는지와 오류 동작을 함께 넣는다.
4. stop rule과 과제가 통과해야 할 verification을 넣는다.
5. 맞는 model section을 적용한다. 다른 model에서 물려받은 규칙과 모순이 없는지 다시
   읽고, 목표한 변경은 같은 대표 사례로 validation한다.

## Evidence base

공급사의 GPT-5.6 coding-agent sample은 더 가벼운 system prompt로 대략 eval 점수
+10~15%, 전체 token 41~66% 감소, 비용 33~67% 감소를 보고했다
(`prompt-guidance-gpt-5p6`, 2026-09-07에 고정). 이는 그 sample의 방향성 결과이며,
Astra 측정치나 다른 workload에서 보장되는 이득이 아니다.

## Sources

GPT-5.6 section은 `prompt-guidance-gpt-5p6`에서, GPT-6 Astra section은
`model-guidance-gpt-6-astra`에서 파생했다. 공유 recipe는 GPT-5.6 guidance와
instructions에서 온 task, evidence, tool, validation 관행을 유지하며, model behavior 주장은
오직 각 model에 맞는 section에만 둔다. `source_pins`는 이 도출에 쓴 정확한 byte를
기록하므로 이후 공급사 편집을 감지할 수 있다.

`targets` model이 바뀌면 그 model의 section을 맞는 현재 document에서 다시 도출하고,
공유 규칙의 모순을 점검하며, 다른 model의 behavior 주장을 확장하지 말고 대표 eval을
다시 실행한다. `launch/check-prompting-targets.sh`는 launch config가 이 guide에 없는
model을 bind하면 실패한다. 이 check는 **naming**에 관한 것이며 `targets:`에 model을
추가하면 영구히 만족한다. guidance가 실제로 다시 도출되었는지는 결정할 수 없으며
어디에서도 gate하지 않는다.
