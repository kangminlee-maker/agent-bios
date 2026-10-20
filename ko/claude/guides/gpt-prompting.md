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
  - 공유 recipe와 대상 model 계열의 section을 함께 적용한다 — GPT-5.6과 GPT-6은 prompting 필요가 다르고, GPT-6 조언은 Astra에서 관찰된 것으로 다른 GPT-6 model에는 출발점이다
  - 경로가 아니라 목적지를 기술한다 — 결과, 성공 기준, 실제 제약, 사용 가능한 근거를 밝힌다
  - 동작을 바꾸는 것만 남긴다. 반복 서술, style 규칙, 동작을 바꾸지 않는 예시는 잘라낸다
  - 포괄적인 ALWAYS/NEVER 대신 각 선택이 적용되는 조건을 명시한 결정 규칙을 쓴다
  - effort를 올리기 전에 prompt를 고친다 — 먼저 성공 기준, 의존 규칙, tool 라우팅 규칙, 또는 검증 루프가 빠졌는지 확인한다
  - 구세대 gpt model에서 가져온 prompting 습관은 token을 쓰고 정확도까지 해칠 수 있다
derived_at: 2026-10-20
source_pins:
  - doc: prompt-guidance-gpt-5p6
    sha256: 46181efec9fd1160ef537b0379282a14c1ba32380f2f8149a805128253c1115a
    pinned_at: 2026-10-20
  - doc: model-guidance-gpt-5p6
    sha256: bcbc002991e3ff6491ba5c4d38d8f5c497fa785c0b11ea27d92c9d34676ab460
    pinned_at: 2026-10-20
  - doc: upgrading-to-gpt-5p6-sol
    sha256: d4d2494240bc124bde81d96a9a389f3ed7122deabc4b508c18d26a3ebd20c74f
    pinned_at: 2026-10-20
  - doc: model-guidance-gpt-6-astra
    sha256: ad1aeb3d87e2e61a91233447f7c54b7b18ebfecc4315eeefab15bf5861b3a5c7
    pinned_at: 2026-10-20
  - doc: model-gpt-6-astra
    sha256: b7c19b3bb89e87a392a0f3f8b732c5e7c9f0bf558cbe3022c491575a947fcef8
    pinned_at: 2026-10-20
  - doc: model-gpt-6p1-sol
    sha256: acfe91d19882aaf7bb52877898684614035a947de02f2955c9de905a7efb1362
    pinned_at: 2026-10-20
  - doc: model-gpt-6-sol
    sha256: 3dcb62c16386c40e52438e7fa7fb46b979d13cbfc324d0807246e24ce43345bb
    pinned_at: 2026-10-20
  - doc: model-gpt-6-luna
    sha256: 2e4861582095740f5ea84b14bb18fa476a49c426b397b779b964bc144397b451
    pinned_at: 2026-10-20
  - doc: reasoning
    sha256: a561487dd41db8828b5b9920d77275bdced3c3c07ba1fb9f3c3230c5aaeb925b
    pinned_at: 2026-10-20
  - doc: codex-models
    sha256: 77779d7adf13e05df5bf7fa82088ebbaa647d16682a91cea5cd3cad043474f8e
    pinned_at: 2026-10-20
  - doc: prompt-caching
    sha256: 74dc45350d5de0e7eef80b0b09d67b733a73170275f1bacb0760e066a4254480
    pinned_at: 2026-10-20
  - doc: responses-multi-agent
    sha256: b16d53b38bc957a790d39d2a736531addfed88a2c806e2be11aac190ea817a3e
    pinned_at: 2026-10-20
  - doc: structured-outputs
    sha256: 09aa3814251cf168070294ace79d677091de04b330055048392548d604aa7104
    pinned_at: 2026-10-20
  - doc: tools-programmatic-tool-calling
    sha256: fc459e1947d9fd4506c54c2a4f3e202d483a3a12a3488f06b974dbf98c787630
    pinned_at: 2026-10-20
targets:
  - gpt-6-astra
  - gpt-6.1-sol
  - gpt-6-sol
  - gpt-6-luna
  - gpt-5.6-sol
  - gpt-5.6-terra
  - gpt-5.6-luna
verification_focus:
  - prompt 변경은 눈으로 보는 대신 같은 eval을 다시 돌려 검증한다
  - 제거는 한 묶음씩 해서 변화의 원인을 특정할 수 있게 한다
  - effort 변경은 대상 model이 받아들이는 값을 쓰고 baseline과 비교한다
  - 계열 수준 조언은 계열 document와, model별 사실은 각 model page와, Codex 전용 값은 Codex document와 대조한다
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
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | GPT-5.6 | `prompt-guidance-gpt-5p6`, `model-guidance-gpt-5p6` |
| `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna` | GPT-6 family | `model-guidance-gpt-6-astra`와 해당 model의 page |

## Per-model facts

각 model page나 계열 guide에서 가져온, 받아들이는 `reasoning.effort` 값과 tool calling
경로다. effort를 생략하면 문서화된 기본값이 적용된다.

| Model | `reasoning.effort` | Tool calling | 공급사 설명 |
| --- | --- | --- | --- |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `none`, `low`, `medium`(기본값), `high`, `xhigh`, `max` | reasoning과 tool을 함께 쓰려면 Responses API; Chat Completions의 function tool은 유효 effort가 `none`일 때만 — effort를 생략하면 `medium`이 되어 이 조합이 깨진다 | Sol은 최상위 성능, Terra는 지능과 비용의 균형, Luna는 효율적인 고용량 작업 |
| `gpt-6-astra` | `low`, `medium`, `high`, `xhigh`, `max`; `none` 미지원; 문서화된 기본값 없음 | Responses API; Chat Completions는 tool 없는 요청만 | 가장 까다로운 reasoning, 코딩, computer use, 전문 업무 |
| `gpt-6.1-sol` | `low`, `medium`(기본값), `high`, `xhigh`, `max`; `none`과 `minimal` 미지원 | Responses API; Chat Completions는 tool 없는 요청만 | 더 낮은 비용으로 Astra에 가까운 성능; 자기 과제에서 Astra와 비교한다 |
| `gpt-6-sol` | `none`, `low`, `medium`(기본값), `high`, `xhigh`, `max` | reasoning과 tool을 함께 쓰려면 Responses API; Chat Completions의 function calling은 `none`에서만 | 복잡한 코딩과 agentic workflow; 해당 page는 더 새로운 Sol로 6.1 Sol을 가리킨다 |
| `gpt-6-luna` | `none`, `low`, `medium`(기본값), `high`, `xhigh`, `max` | `gpt-6-sol`과 같음 | 집중된 고용량 과제 |

## GPT-5.6

- **먼저 단순화한다.** 결과, 제약, 근거, 완료 기준을 밝힌 뒤 model이 경로를 선택할
  여지를 둔다. 동작하는 prompt에서 시작해 반복 지시, 예시, 관련 없는 tool을 한 묶음씩
  제거하고 같은 eval을 다시 돌린다. 동작을 바꾸는 process 지시는 남긴다.
- **간결함을 조정한다.** GPT-5.6은 GPT-5.5보다 더 간결해지는 경향이 있다. 광범위한
  간결성 지시는 그대로 가져오기 전에 다시 시험한다. 답변을 지나치게 얇게 만들 수 있으며,
  필요한 결과를 만들어 낼 때만 남긴다. API가 `text.verbosity`를 제공하면 기본 상세
  수준에는 그것을 쓰고, 과제의 길이, 구조, 필수 내용에는 prompt를 쓴다. 근거, 결정,
  유의점, 다음 행동보다 먼저 반복을 줄인다.
- **협업을 tone과 분리해 정의한다.** 언제 질문하고, 가정하고, 주도적으로 행동하고,
  불확실성을 설명할지 간결히 명시한다. 점검이나 계획 요청과 구현 요청을 구분한다.
  범위 안의 통상 작업이 불필요하게 멈추지 않도록 안전한 local 행동과 approval 경계를
  한 번 명시한다.
- **prompt 다음에 effort를 조정한다.** 현재의 유효 effort를 baseline으로 보존한 뒤,
  대표 과제에서 그것과 지원되는 한 단계 낮은 수준을 비교한다. 지연 시간이 중요하고
  품질이 유지되면 `low`를 쓴다. `medium`은 균형 잡힌 시작점이다. eval이 이득을 보일
  때 `high`/`xhigh`를 쓰고, `max`는 가장 어려운 품질 최우선 작업에 남겨 둔다. 받아들이는
  값은 위 표에 있다. 활성 host에서 다시 확인한다.

## GPT-6 family

OpenAI는 GPT-6용 prompting document를 하나만 공개한다. 그 best practice는 GPT-6
Astra에서 관찰된 동작을 다루고, 계열 전체의 출발점으로 제시되며, 선택한 model과
workload에서 평가하라고 되어 있다. 따라서 아래 다섯 동작 항목은 Astra 관찰이다.
`gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`에 대해 공급사는 model별 prompting 동작을
밝히지 않는다. model마다 다른 것은 위 표의 API 사실이며, 각 model page에서 가져왔다.

- **주도성과 끝까지 수행하기.** Astra는 입력이 결과를 크게 바꿀 수 있을 때 질문할
  가능성이 더 높고, 작업 중에도 진행을 막지 않는 질문을 던진다. 행동 요청에는 context에서
  통상 세부를 추론하고, 답하기 전에 검증을 포함한 승인된 작업을 완료하라고 prompt한다.
  계획이나 계속하겠다는 제안은 행동 요청을 완료하지 않는다. 빠진 정보가 결과를 바꿀 때
  질문하고, 기다리는 동안 독립적인 승인된 작업은 계속한다. 이후 단계에 approval이
  필요하면 먼저 구체적이고 검토 가능한 결과를 준비한다. 기존 permission 경계를 지키고,
  가정적 위험만을 근거로 approval 단계를 추가하지 않는다.
- **지시와 skill 민감성.** Astra는 긴 지시를 더 잘 따르고 context에 더 민감하다. skill
  file의 불명확하거나 충돌하는 지침은 Astra를 멈추게 하고 작업을 일찍 막을 수 있다.
  로드된 skill과 instruction file을 점검한다. 더 높은 우선순위 지시와 permission 제약
  안에서 명시적 사용자 지시가 skill workflow 선호보다 우선하게 한다. skill이 멈춤,
  approval 요청, 또는 미완료 작업을 초래하면 정확한 skill file을 식별해 링크하고, 해당
  규칙을 인용하고, 그 규칙이 명시적인지 해석인지 말하게 한다.
- **Writing style.** Astra는 상세한 응답, 목록, 표, 그리고 session을 넘어 반복되는
  표현으로 기우는 경향이 있다. 독자에 맞춘 길이와 구조를 지정한다. 평문에는 간결한
  문단, 익숙한 단어, 능동적인 동사, 핵심부터 제시하도록 요청하고, 목록은 내용이
  병렬이거나 순차적이거나 비교하기 쉬울 때만 쓴다. 결과를 평가하는 데 필요한 기술
  세부는 남기고, 원치 않는 정형 표현과 대조 틀이 반복되면 이를 명시한다.
- **Subagent delegation.** Astra는 workflow가 요구하는 것보다 delegation을 덜 할 수
  있고, 언제 어떻게 delegate할지에 대한 prompting에 잘 반응한다. 독립 작업을 언제
  delegate할지, 의도한 병렬성의 정도, 각 subagent의 범위, 작업을 local에 둘 때를 기존
  spawn gate, seat, budget 안에서 명시한다. "능동적으로 하라"는 지시만으로는 delegation을
  정하지 못한다. 단어 사이 간격이 올바른, 읽기 쉬운 inter-agent message를 요구한다.
- **Testing and verification.** Astra는 작은 코딩 변경을 과도하게 test할 수 있다.
  관련 check와 완료 기준을 명시하고, 되돌릴 수 있고 영향이 작은 구현을 그대로 되풀이하는
  test는 피한다. 요구된 check를 완료하고, 새 편집, 실패, 또는 미해결 우려가 뒷받침할
  때만 이를 넓히거나 다시 실행한다. 요구된 repository gate와 변경된 동작의 validation은
  그대로 유지된다.

### Reasoning effort

- model이 받아들이는 한 현재 유효 effort를 보존한다. `none`으로 돌던 prompt는 Astra나
  6.1 Sol에서 `low`로 옮기고, `minimal`로 돌던 prompt는 `low`에서 시작해 대표 과제로
  비교한다. effort가 `none`이 아니면 `temperature`, `top_p`, 그리고 log-probability
  옵션(`top_logprobs`; Chat Completions의 `logprobs`; Responses `include`의
  `message.output_text.logprobs`)을 뺀다. 응답 사이에 effort를 바꾸려면
  `configuration_update` item을 넣고(GPT-6 전용, 표준 단일 agent 요청, effort만 변경)
  요청 수준 effort는 그대로 두어 cache된 prefix를 살린다. 그런 history에는 자동
  compaction·truncation을 쓸 수 없고 `/responses/compact`도 이를 거부한다. `/responses`
  요청에 `compaction_trigger` item을 넣어 compact한 뒤, 다음 user message 전에 새
  `configuration_update`를 추가한다. effort를 높이기 전에
  빠진 성공 기준, 의존 규칙, 또는 검증 루프를 고친다. effort는 조정 손잡이이지 품질을
  되찾는 주된 수단이 아니다.
- **Codex에서.** `ultra`는 API 값이 아니라 Codex의 effort다. 과제를 subagent로 나눠
  실행하므로 의미 있는 부분으로 나뉘는 작업에 맞는다. GPT-6 Luna는 Max까지 지원하고
  Ultra는 없으며, 대부분의 과제에는 둘 다 필요 없다. effort는 model 세대 사이에 정확히
  대응하지 않으므로, 익숙한 과제를 한 단계 낮은 설정으로 돌려 보고 조정한다. effort를
  생략한 실행은 client의 기본값을 물려받는데, 이는 API 기본값과 다를 수 있으므로(client
  catalog는 `gpt-6.1-sol`을 `low`로 두고, API 기본값은 `medium`이다) launch config에
  고정한다. client의 model catalog는 model별 base instruction도 prompt 아래에 깔아
  둔다. Astra, 6.1 Sol, 6 Sol은 위 testing 조정을 담고 있고, GPT-6 Luna는 요청받지
  않으면 test를 추가하거나 실행하지 말라고 지시받으므로, 검증이 필요한 Luna 실행은
  prompt에 check를 명시해야 한다(Codex client catalog, codex-cli 0.163.0, 2026-10-20에
  읽음; 공개 document가 아니다).

## Shared prompt recipe

완성된 prompt는 이 순서로 배열하고, 초안은 성공 기준부터 쓴다(아래 checklist). 산출물을
바꾸지 않을 block은 뺀다.

- `Role`과 `Personality` — 누가 어떤 어조로 행동하는가. 출력이 달라지지 않으면
  personality는 뺀다.
- `Goal`과 `Success criteria` — 결과, 그리고 완료를 판정하는 기준. 나머지보다 먼저
  초안을 잡는다. 기준을 못 쓰겠다면 그 prompt는 아직 준비된 게 아니다.
- `Constraints` — 지켜야 할 안전, 비즈니스, 범위 한계. 실제 제약만 둔다. 선호는 output
  shape에 넣거나 아예 넣지 않는다.
- `Tools` — 과제에 필요한 것만 둔다. 각 설명은 무엇을 하는지, 언제 쓰는지, 중요한 반환
  field, 오류 동작을 밝힌다.
- `Output` — 산출물 형태. schema로 강제한 출력에서는 model이 schema의 key 순서대로
  field를 쓰고 모든 field가 필수다. 그래서 이 저장소는 verdict field보다 그것을 뒷받침하는
  근거 field를 앞에 두고(eval로 확인할 설계 선택이다), 값을 억지로 채우는 대신 맞지 않는
  입력을 보고할 명시적 방법을 준다. `Stop rules` — 언제 loop를 멈추고 답할지.

## When to add blocks

- Coding and debugging: 변경 뒤 실행할 validation을 명시한다 — 바뀐 동작에 대한
  targeted test, type/lint check, build, 최소 smoke test, visual artifact가 있으면
  render해 점검. 편집 전 선행 조회를 요구한다. validation을 실행할 수 없으면 그 이유와
  차선의 check를 요구한다.
- Review: 일반 규칙을 포함하고 근거 기준과 verdict 형태를 명확히 한다.
- Research and grounded work: 검색해 얻은 source만 인용하고, 인용은 그것이 뒷받침하는
  주장에 붙이며, 추론은 뒷받침된 사실과 구분해 표시한다. 추측하지 말고 답을 좁히거나
  근거 부족을 보고하라고 말한다. 근거가 없다는 것이 사실로서의 "아니오"는 아니다.
- Write-capable work: 안전한 행동(파일 읽기, 코드 편집, test 실행)을 명시한다. 확인은
  session이 아직 승인하지 않은 외부 쓰기, 파괴적 행동, 범위 확장에만 요구하고, 작업을
  준비한 뒤 마지막 단계로 요청한다. 앞서 주어졌거나 과제에서 분명히 암시된 승인은
  그대로 유효하다.
- Implementation plans: 요구사항, 명명된 resource, 상태 전이, validation check, 실패
  동작, privacy/security, 미해결 질문.

## How to choose prompt shape

- 각 단계가 바로 앞 단계에 의존하거나, 과제가 짧은 한 번의 실행으로 끝나거나, agent들이
  같은 가변 상태를 두고 경합할 때는 단일 실행. 작업이 독립적이고 경계가 분명한 과제로
  나뉘거나, 분리된 context가 집중에 도움이 되거나, 병렬 탐색이 경과 시간을 줄일 때는
  fan-out. subagent는 token 사용을 늘리므로 분할이 그 값을 해야 한다. 한 실행 안에서는
  독립적인 읽기를 병렬화하고 의존 단계는 순차로 둔다.
- 표와 대상 model의 section에서 reasoning effort를 고른다. API dispatch에서는
  reasoning과 보이는 출력이 출력 한도를 나눠 쓰고, reasoning이 보이는 출력이 나오기 전에
  한도를 소진할 수 있다. reasoning과 산출물을 합쳐 출력 용량을 잡고, effort 수준을
  비교할 때 그렇게 소진된 실행을 함께 센다.
- 안정적인 지시와 공유 참조 자료를 앞에, 요청마다 다르거나 바뀌는 내용을 뒤에 두고, 그
  prefix를 자주 바꾸지 않는다. 순서만으로는 아무것도 cache되지 않는다. prefix가 최소
  cache 길이에 이르고 breakpoint에서 끝나야 하며, implicit caching은 바뀌는 뒷부분까지
  함께 기록하므로, GPT-5.6 이후 model에서는 implicit breakpoint가 안정 경계를 놓칠 때
  명시적 breakpoint로 그 경계를 표시한다. 여러 turn에 걸친 작업에서는 이전 message와
  tool 결과를 유지해 이후 turn이 전체 prefix를 재사용하게 한다.

## Programmatic tool calling

코드가 여러 tool 결과를 처리해 훨씬 작은 구조화 결과를 돌려주는 제한된 stage다.
핵심 조건은 병렬성이 아니라 **축소**다. 여러 호출, 병렬 호출, 의존 호출만으로는 이를
정당화하지 못한다.

- filtering, joining, sorting, ranking, deduplication, aggregation, 여러 유사 record에
  걸친 batching, 반복되는 결정적 validation, compact schema로 줄일 수 있는 큰 구조화
  결과에 쓴다. 한 호출이면 충분할 때, 중간 출력이 이미 작을 때, 각 결과가 다음 결정을
  바꿀 수 있을 때, 행동에 approval이 필요할 때, 답변이 citation이나 native artifact를
  보존해야 할 때, 또는 호출 사이에 의미적 판단이 놓일 때는 direct call을 선호한다.
- 일반적인 "programmatic tool calling을 효율적으로 사용하라"는 지시는 아무것도 하지
  않는다. 제한된 stage, 적격 tool, output schema, retry limit, stop condition, direct
  judgment로 되돌아갈 handoff를 명시한다. 두 경로가 모두 필요하면 handoff 하나를
  정의하고 경로를 바꾸거나 완료한 작업을 반복하지 말라고 말한다. 실행 중인 프로그램은
  tool search를 부를 수 없으므로, stage에 필요한 deferred tool은 프로그램 시작 전에
  찾아 로드하라고 요구한다.
- **두 출력을 모두 test한다.** 프로그램 결과와 최종 assistant message는 별개다.
  프로그램이 올바른 record를 돌려도 message에서 필수 field, citation, 또는 유의점을
  빠뜨릴 수 있다. 같은 과제에서 두 경로를 비교하고, 응답이 기존 eval을 여전히 통과할
  때만 더 낮은 token/latency/cost를 개선으로 센다.

## Working rules

- 한 실행에 하나의 명확한 과제와 명시적 output contract를 둔다.
- **조립된 prompt에 모순이 없는지 읽고, 각 authority 규칙은 한 번만 쓴다.** GPT-5.6
  guidance는 GPT-5급 model이 prompt contract를 면밀히 따르므로 충돌하는 규칙이 빠진
  세부보다 더 큰 불안정을 만들고, "먼저 물어라", "변경하지 마라", "approval을 기다려라"를
  반복하면 안전하고 예상되는 행동에도 approval 요청이 생긴다고 보고한다. 이 guide는 두
  점검을 모든 대상에 저장소 관행으로 적용한다.
- 오래 가는 과제에서는 현재 작업 layer — research, design, implementation, review,
  external coordination — 를 명시해 model이 layer를 조용히 넘나들지 않게 한다.
- 지속된 reasoning은 공짜 최적화가 아니다. 목표와 우선순위가 유지되는 동안에는 도움이
  되지만, 바뀌고 나면 낡은 reasoning은 token을 더하고 model을 폐기된 접근에 붙잡아
  둔다. model이 `reasoning.context`를 지원하면(GPT-5.6 계열은 `all_turns`가 기본값이고
  GPT-6.1 Sol도 지원한다) 이전 reasoning이 더는 관련 없을 때 `current_turn`으로 둔다.
  매 turn이 아니라 milestone에서 compact하고 compacted item은 불투명한 것으로 취급한다.
- 명시적인 사용자 값을 보존한다. 올바른 값이 암시적일 때는 보편적 기본값이나 keyword
  map을 설치하지 말고 결정 기준을 주어 model이 context나 schema에서 추론하게 한다.
- 각 tool 결과 뒤에 성공 기준 — 요구된 행동과 validation 포함 — 이 유용한 근거와 함께
  충족되었는지 묻는다. 그렇다면 답한다. loop 최소화가 정확성, 요구된 근거, 계산, 요구된
  citation보다 우선하는 일은 없다.

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
(`prompt-guidance-gpt-5p6`). 이는 그 sample의 방향성 결과이며, GPT-6 측정치나 다른
workload에서 보장되는 이득이 아니다.

## Sources

GPT-5.6 section은 `prompt-guidance-gpt-5p6`에서 파생했고, 그 사실 행은
`model-guidance-gpt-5p6`과 `upgrading-to-gpt-5p6-sol`에서 가져왔다. GPT-6 family
section은 `model-guidance-gpt-6-astra` — 유일한 GPT-6 prompting document "Using
GPT-6"로, Astra URL이 제공한다 — 에서 파생했고, model별 사실은 `model-gpt-6-astra`,
`model-gpt-6p1-sol`, `model-gpt-6-sol`, `model-gpt-6-luna`에서, effort 의미와
`configuration_update` 제한은 `reasoning`에서, Codex 전용 effort 값은 `codex-models`에서
가져왔다. base instruction에 관한 설명은 Codex client의 local model catalog에서 왔으며,
이 catalog는 어떤 URL도 제공하지 않고 어떤 pin도 추적하지 않는다. 공유 recipe는 GPT-5.6
guidance의 task, evidence, tool, validation 관행을 유지하고 이를 GPT-6 대상에도
적용하는데, 이는 이 저장소의 선택이다. prompt 배치는 `prompt-caching`, 실행 형태는
`responses-multi-agent`, schema로 강제한 출력은 `structured-outputs`, programmatic stage의
선행 조건은 `tools-programmatic-tool-calling`에서 가져왔다.
model behavior 주장은 오직 각자의 section에만 둔다. `source_pins`는 이 도출에 쓴 정확한
byte를 기록하므로 이후 공급사 편집을 감지할 수 있다.

`targets` model이 바뀌면 그 model의 section을 맞는 현재 document에서 다시 도출하고,
공유 규칙의 모순을 점검하며, 다른 model의 behavior 주장을 확장하지 말고 대표 eval을
다시 실행한다. `launch/check-prompting-targets.sh`는 bind된 model이 모두 `targets:`에
**이름으로** 올라 있는지만 검사한다. guidance가 실제로 다시 도출되었는지는 결정할 수
없으며 어디에서도 gate하지 않는다.
