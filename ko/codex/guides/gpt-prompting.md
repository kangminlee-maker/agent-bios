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
  - 공유 recipe와 대상 model 계열의 section을 함께 적용한다 — GPT-5.6, GPT-6, GPT-6.2는 prompting 필요가 다르다. GPT-6 조언은 GPT-6 Astra에서, GPT-6.2 조언은 GPT-6.2 Astra와 Sol에서 관찰된 것이며, 각각 같은 계열의 나머지 model에는 출발점이다
  - 경로가 아니라 목적지를 기술한다 — 결과, 성공 기준, 실제 제약, 사용 가능한 근거를 밝힌다
  - 동작을 바꾸는 것만 남긴다. 반복 서술, style 규칙, 동작을 바꾸지 않는 예시는 잘라낸다
  - 포괄적인 ALWAYS/NEVER 대신 각 선택이 적용되는 조건을 명시한 결정 규칙을 쓴다
  - effort를 올리기 전에 prompt를 고친다 — 먼저 성공 기준, 의존 규칙, tool 라우팅 규칙, 또는 검증 루프가 빠졌는지 확인한다
  - 구세대 gpt model에서 가져온 prompting 습관은 token을 쓰고 정확도까지 해칠 수 있다
derived_at: 2026-11-24
source_pins:
  - doc: model-guidance-gpt-6p2
    sha256: d51a271ccee79b94428bc1d1a1591f9f98c424f2d9d084a37ccc4358dada40c0
    pinned_at: 2026-11-24
  - doc: prompt-guidance-gpt-5p6
    sha256: fbf38652350fee866f46d888e6a0e83537cf5a5a148818271332260cd3e439f7
    pinned_at: 2026-11-24
  - doc: model-guidance-gpt-5p6
    sha256: bcbc002991e3ff6491ba5c4d38d8f5c497fa785c0b11ea27d92c9d34676ab460
    pinned_at: 2026-11-24
  - doc: upgrading-to-gpt-5p6-sol
    sha256: 59484b7370078d3482d972dfeb7f79fe862e410571881f9983e1bca7dea89ebe
    pinned_at: 2026-11-24
  - doc: model-gpt-6p2-astra
    sha256: b12e61471fed60c843626fdee3dea09c86babae84ea779a5f5eb9193cb62720f
    pinned_at: 2026-11-24
  - doc: model-gpt-6p2-sol
    sha256: 551d09dbb7e6f64a1af314446b8d5a72ab9bf66daa4407060007d11ce54acf43
    pinned_at: 2026-11-24
  - doc: model-guidance-gpt-6-astra
    sha256: b12f5dde985df0ac1e03ea5eaa40dfcdb0e4620a1bf1ae4d78cdd81f8c7f4c3a
    pinned_at: 2026-11-24
  - doc: model-gpt-6-astra
    sha256: 31d55873985379d2b4e129fd41f974e8511b9de1a5105dc4e0692b53b504a8cb
    pinned_at: 2026-11-24
  - doc: model-gpt-6p1-sol
    sha256: 02dff9ef937bbc97fb24ba7c936269a549563cfb8a49b91a6ba1c1575d2b77c0
    pinned_at: 2026-11-24
  - doc: model-gpt-6-sol
    sha256: 8e3cd3378f0686313dd489ed37347d481d24d4b791e7bd28b1538c4df7762fc4
    pinned_at: 2026-11-24
  - doc: model-gpt-6-luna
    sha256: dacc9870e67c0d68e4272f8394d4296ffe7cf70f18d3f4675ee6bd4c666966b7
    pinned_at: 2026-11-24
  - doc: reasoning
    sha256: f0c480788b035a289f34aef88a58cb48abead8abd82194ae8f68b110d5971bfa
    pinned_at: 2026-11-24
  - doc: codex-models
    sha256: 2ca411d02af5e803e25d60eedcac752c7a6153c2c6dffafdbd854aff61f4277c
    pinned_at: 2026-11-24
  - doc: prompt-caching
    sha256: 41fd5ad72dc74045ffb0fbe33e8213a879cc018a473b1e022b7be8fa04057625
    pinned_at: 2026-11-24
  - doc: responses-multi-agent
    sha256: 1bb6554687059202a4c92486d39fb2ea42730fb20a85880c33258186872012f8
    pinned_at: 2026-11-24
  - doc: structured-outputs
    sha256: fbabb4598029cba47f3b19e173371da9950e6c9050b5380460b0256b8a08d9fe
    pinned_at: 2026-11-24
  - doc: tools-programmatic-tool-calling
    sha256: cd5027c76f0d5c9473c0333b69dc89af27bf45c356760e2b1628172ef54923a9
    pinned_at: 2026-11-24
targets:
  - gpt-6.2-astra
  - gpt-6.2-sol
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
| `gpt-6.2-astra`, `gpt-6.2-sol` | GPT-6.2 | `model-guidance-gpt-6p2`와 해당 model의 page |

## Per-model facts

각 model page나 계열 guide에서 가져온, 받아들이는 `reasoning.effort` 값과 tool calling
경로다. effort를 생략하면 문서화된 기본값이 적용된다.

| Model | `reasoning.effort` | Tool calling | 공급사 설명 |
| --- | --- | --- | --- |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `none`, `low`, `medium`(기본값), `high`, `xhigh`, `max` | reasoning과 tool을 함께 쓰려면 Responses API; Chat Completions의 function tool은 유효 effort가 `none`일 때만 — effort를 생략하면 `medium`이 되어 이 조합이 깨진다 | Sol은 최상위 성능, Terra는 지능과 비용의 균형, Luna는 효율적인 고용량 작업 |
| `gpt-6.2-astra`, `gpt-6.2-sol` | API는 `none`을 거부하며 허용 목록과 기본값은 문서에 없다. 공급사는 새 integration을 `medium`에서 시작하고 `none`이나 `minimal`은 `low`로 옮기라고 한다. Codex catalog는 `low`부터 `max`와 `ultra`까지 제공한다 | Responses API; Chat Completions는 tool 없는 요청만; Flex processing 미지원 | Astra는 가장 까다로운 과제, Sol은 더 낮은 비용의 복잡한 작업이자 Codex의 일상 model |
| `gpt-6-astra` | `low`, `medium`, `high`, `xhigh`, `max`; `none` 미지원; 문서화된 기본값 없음 | Responses API; Chat Completions는 tool 없는 요청만 | 가장 까다로운 reasoning, 코딩, computer use, 전문 업무 |
| `gpt-6.1-sol` | `low`, `medium`(기본값), `high`, `xhigh`, `max`; `none`과 `minimal` 미지원 | Responses API; Chat Completions는 tool 없는 요청만 | 더 낮은 비용으로 Astra에 가까운 성능 |
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

OpenAI의 GPT-6 prompting document("Using GPT-6")는 GPT-6.2보다 먼저 나왔고, GPT-6.2는
별도 document를 갖는다(다음 section). 그 best practice는 GPT-6
Astra에서 관찰된 동작을 다루고, 계열 전체의 출발점으로 제시되며, 선택한 model과
workload에서 평가하라고 되어 있다. 따라서 아래 다섯 동작 항목은 Astra 관찰이다.
`gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`에 대해 공급사는 model별 prompting 동작을
밝히지 않는다. model마다 다른 것은 위 표의 API 사실이며, 각 model page에서 가져왔다.
Astra가 아닌 GPT-6 model이 자체 prompting document를 갖게 되면 이 section을 다시 도출한다.

- **주도성과 끝까지 수행하기.** Astra는 입력이 결과를 크게 바꿀 수 있을 때 질문할
  가능성이 더 높고, 작업 중에도 진행을 막지 않는 질문을 던진다. 행동 요청에는 context에서
  통상 세부를 추론하고, 답하기 전에 검증을 포함한 승인된 작업을 완료하라고 prompt한다.
  계획이나 계속하겠다는 제안은 행동 요청을 완료하지 않는다. 빠진 정보가 결과를 바꿀 때
  질문하고, 기다리는 동안 독립적인 승인된 작업은 계속한다. 이후 단계에 approval이
  필요하면 먼저 구체적이고 검토 가능한 결과를 준비한다. 기존 permission 경계를 지키고,
  가정적 위험만을 근거로 approval 단계를 추가하지 않는다. Astra는 GPT-5.6 Sol과 이전
  model보다 긴 과제에서 일관성을 더 잘 유지한다.
- **지시와 skill 민감성.** Astra는 긴 지시를 더 잘 따르고 context에 더 민감하다. skill
  file의 불명확하거나 충돌하는 지침은 Astra를 멈추게 하고 작업을 일찍 막을 수 있다.
  로드된 skill과 instruction file을 점검한다. 더 높은 우선순위 지시와 permission 제약
  안에서 명시적 사용자 지시가 skill workflow 선호보다 우선하게 한다. skill이 멈춤,
  approval 요청, 또는 미완료 작업을 초래하면 정확한 skill file을 식별해 링크하고, 해당
  규칙을 인용하고, 그 규칙이 명시적인지 해석인지 말하게 한다. 선택적 지침을 해석한 것은
  요구사항이 아니다.
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
  `configuration_update` item을 넣고(GPT-6 이후 model, 표준 단일 agent 요청, effort와
  response format(`json_schema` 또는 `text`)을 바꾼다) 요청 수준 effort는 그대로 두어
  cache된 prefix를 살린다. 응답은 계속 요청 수준 effort를 보고한다. 그런 history는
  `context_management`로 자동 compaction을 쓸 수 있지만, 자동 truncation과
  `/responses/compact`는 이를 거부한다. 직접 compact하려면 `/responses` 요청에
  `compaction_trigger` item을 넣은 뒤, 다음 user message 전에 바꾼 설정을 format까지
  모두 다시 적은 새 `configuration_update`를 추가한다. effort를 높이기 전에 빠진 성공
  기준, 의존 규칙, 또는 검증 루프를 고친다(GPT-5.6 guidance). effort는 조정 손잡이이지
  품질을 되찾는 주된 수단이 아니다.
- **Codex에서.** `ultra`는 API 값이 아니라 Codex의 effort다 — API의 effort 목록은
  `max`에서 끝난다. 다음 단계가 아니라 다른 mode다. client catalog는 이를 자동 과제
  위임을 곁들인 최대 추론으로 설명하며, 과제를 subagent로 나눠 실행하므로 의미 있는
  부분으로 나뉘는 작업에 맞는다. catalog는 목록에 있는 모든 Astra, Sol, Terra model에
  이를 제공하며 GPT-6.2도 포함된다. Luna는 Max까지 지원하고 Ultra는 거부하며, 대부분의
  과제에는 둘 다 필요 없다. seat가 지원하는 수준은 API 단계표가 아니라 host의 catalog에서
  가져온다. 둘은 서로 다르고, GPT-6.2는 catalog에만 수준 목록이 있다. effort를 생략한
  실행은 client의 기본값을 물려받는데, 이는 API 기본값과 다를 수 있으므로(client catalog는
  `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6-astra`, `gpt-6.1-sol`을 `low`로 두고, 6.1 Sol의
  API 기본값은 `medium`이다) launch config에 고정한다. client의 model catalog는 model별
  instruction도 prompt 아래에 깔아 둔다. GPT-6.2 Astra와 Sol은 공급사의 GPT-6.2 coding
  sample을 담는데, 이 sample은 요청받았거나 repository가 요구하거나 기존 test가 놓칠
  regression을 잡는 데 필요할 때가 아니면 새 test를 만들지 않으므로, test를 추가해야 하는
  6.2 실행은 그 요구를 명시해야 한다. GPT-6 Astra, 6.1 Sol, 6 Sol은 위 GPT-6 testing
  조정을 담고 있고, GPT-6 Luna는 요청받지 않으면 test를 추가하거나 실행하지 말라고
  지시받으므로, 검증이 필요한 Luna 실행은 prompt에 check를 명시해야 한다(Codex client
  catalog, codex-cli 0.171.0, 2026-11-24에 읽음; 공개 document가 아니다).

## GPT-6.2

OpenAI의 GPT-6.2 document("Using GPT-6.2")는 그 prompt를 GPT-6.2 계열 전체의 출발점으로
제시하며, 예시는 GPT-6.2 Astra와 Sol에서 본 동작을 다룬다. delegation과 skill 민감성에
대해서는 말하지 않는다. 이 둘에 대해서는 위 GPT-6 항목이 평가해 볼 GPT-6 Astra 출발점일 뿐
6.2 관찰이 아니다.

- **Writing style.** 이전 model보다 기본적으로 더 간결하고 직접적이다. 오래된 prompt에서
  가져온 "간결하게" 지시는 간결성 압박을 더하지 말고 다시 검토한다. 사용자와 출처가 쓰는
  용어, 핵심 먼저, 추론을 따라갈 만큼의 context를 요청한다. 외부 독자에게 보내는 글이면
  그 독자에게 없는 배경을 채우게 하고, 편집할 때는 저자의 내용과 표현을 지키게 한다.
- **스스로 완결된 최종 답변.** 긴 과제에서 model은 reasoning, tool call, subagent brief의
  약어를 최종 답변에 옮겨 올 수 있다. 진행 보고를 건너뛴 독자도 따라갈 수 있게 그 독자를
  위해 새로 쓴 최종 답변을 요청한다.
- **과제 완료.** 의도가 불분명하면 model은 다음 단계를 제안하고 기다릴 수 있다. 감독
  없이 진행할 수 있는 작업이면 완료할 결과와 사용자가 정할 결정을 밝힌다. 범위 안에서
  되돌릴 수 있는 합리적 가정을 하고, 그 가정을 밝히고, 계속하게 한다. 멈추는 것은 큰 범위
  변경, 구체적인 막힘, 사용자가 내려야 할 결정, 되돌릴 수 없거나 파괴적인 행동일 때뿐이다.
  끝내기 전에 요청의 모든 부분이 끝났는지 확인하게 한다. 더 높은 effort는 그 마지막 확인을
  끝까지 해내는 데 도움이 될 수 있다. 이는 기존 approval 규칙 안에서 동작을 조정할 뿐이며
  규칙은 그대로다.
- **Coding style.** 기본적으로 더 효율적인 code를 쓴다. codebase의 관례와 호출자가 기대는
  동작을 설명한다. 기존 logic을 언제 재사용할지, 변경 범위를 얼마나 좁힐지, test가 언제
  필요한지를 밝힌다. 공급사의 coding sample은 가장 짧은 code보다 읽기 쉬운 code를 요구하고
  가치 없는 간접화를 경고한다. test 규칙은 위 Codex 항목에 있다. 요구된 repository gate는
  그대로 유지된다.
- **Visual work.** 특정한 모양을 원하면 이미지와 typography를 지정하고, 대조해 그려 볼
  참고 자료를 주고 다듬게 한다.

GPT-6.2부터 API에서 달라지는 것:

- **prefix를 고치면 reasoning이 빠진다.** 이전 history를 고치거나(앞선 developer message나
  tool result를 다시 쓰는 것), 일부 model 변경(downgrade 포함), 다른 end user나
  organization(`safety_identifier`)이 있으면 Responses API는 그 뒤의 reasoning item을
  버린다. 답의 질이 떨어지고 model이 작업을 반복할 수 있다. item 전체를 지우거나 새 item을
  덧붙이는 것은 이런 편집이 아니다. 응답 사이의 설정 변경은 prefix를 다시 쓰지 말고
  `configuration_update`로 하고, 제거 여부는 응답의 `input_transformations`로 확인한다.
- **top-level `instructions`가 `input` 뒤로 간다.** 모든 cache breakpoint 뒤에 놓이고,
  cache hit여도 비캐시 요금이 붙고, `previous_response_id`로 이어지지 않는다. 재사용할
  지시는 `input`의 첫 `developer` message에 넣고, top-level `instructions`는 현재 요청에만
  해당하는 지침에 쓴다.
- **caching parameter.** `prompt_cache_options.ttl`이 `prompt_cache_retention`을 대신한다.
  기본은 `"30m"`이고 Responses API에서는 `"12h"`도 된다. cache 쓰기는 30분이 비캐시 입력
  요금의 1.25배, 12시간이 2.5배이고, 6.2 Astra와 Sol의 읽기는 0.05배다.
- **처리 방식.** Flex processing은 없다. background mode는 긴 요청에 할인된 2시간·8시간
  완료 창을 제공한다.
- **Multi-agent beta.** 6.2 Astra와 Sol(그리고 6.1 Sol과 GPT-5.6)에서 쓸 수 있다. 켜면
  `/responses/compact`를 쓸 수 없고, 자동 compaction이 켜지고, `reasoning.summary`와
  `max_tool_calls`를 지원하지 않으며, 기본으로 subagent 셋이 동시에 돈다.
- **Codex에서.** client의 기본 context는 6.2 Astra가 272,000 token, 6.2 Sol이 500,000
  token이다(client catalog). Codex 문서는 두 model을 Codex app과 CLI용으로 적고 IDE
  extension용으로는 적지 않는다.

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

- 범위가 정해진 review packet은 기본적으로 상속된 지시 없이 하나의 자기완결적 실행 —
  hermetic profile — 으로 돌린다(repository 관행).
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
  명시적 breakpoint로 그 경계를 표시한다. 추가 전후로 보고된 `cached_tokens`와 비용을
  확인하고, 그것이 나아지는 곳에만 breakpoint를 남긴다. GPT-6.2에서는 안정적인 지시를
  top-level `instructions`가 아니라 첫 `developer` message에 둔다(GPT-6.2 section). 여러
  turn에 걸친 과제를 이어갈 때는 이전 message와 tool 결과를 고치지 않고 유지해 이후 turn이
  전체 prefix를 재사용하게 한다. 범위가
  정해진 새 과제를 시작할 때는 그 과제에 필요 없는 context를 담은 긴 history를 이어가지
  말고 자기완결적 packet을 보낸다.

## Programmatic tool calling

코드가 여러 tool 결과를 처리해 훨씬 작은 구조화 결과를 돌려주는 제한된 stage다.
핵심 조건은 병렬성이 아니라 **축소**다. 여러 호출이나 병렬 호출만으로는 이를 정당화하지
못하고, 의존 호출은 code가 이후 인자를 끌어낼 수 있고 한도와 실패 동작이 명시적일 때만
해당한다.

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
  GPT-6.1 Sol도 지원한다. GPT-6.2에 대해서는 문서에 없다) 이전 reasoning이 더는 관련 없을 때 `current_turn`으로 둔다.
  매 turn이 아니라 milestone에서 compact하고 compacted item은 불투명한 것으로 취급한다.
- 명시적인 사용자 값을 보존한다. 올바른 값이 암시적일 때는 보편적 기본값이나 keyword
  map을 설치하지 말고 결정 기준을 주어 model이 context나 schema에서 추론하게 한다.
- 시각적 산출물은 마무리 전에 render하고, layout, 잘림, 간격, 빠진 내용, 시각적 일관성을
  살펴 render가 요구사항을 충족할 때까지 고친다.
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
section은 `model-guidance-gpt-6-astra` — GPT-6 prompting document "Using
GPT-6"로, Astra URL이 제공한다 — 에서 파생했고, model별 사실은 `model-gpt-6-astra`,
`model-gpt-6p1-sol`, `model-gpt-6-sol`, `model-gpt-6-luna`에서 가져왔다 — 그 document는
자신의 prompt를 GPT-6 계열 전체의 출발점이라고 부르므로 이 section은 Astra에 한정되지
않는다. effort 의미, `configuration_update` 제한, reasoning item 제거 규칙은 `reasoning`에서,
Codex 전용 effort 값은 `codex-models`에서 가져왔다. GPT-6.2 section은
`model-guidance-gpt-6p2`("Using GPT-6.2")에서 파생했고, 사실은 `model-gpt-6p2-astra`와
`model-gpt-6p2-sol`에서, caching 변경은 `prompt-caching`에서, multi-agent 제한은
`responses-multi-agent`에서 가져왔다. model별 instruction 설명, 기본 effort, 6.2의 context
크기는 Codex client의 local model catalog에서 왔으며, 이 catalog는 어떤 URL도 제공하지 않고
어떤 pin도 추적하지 않는다. 공유 recipe는 GPT-5.6 guidance의 task, evidence, tool,
validation 관행을 유지하고 이를 GPT-6과 GPT-6.2 대상에도
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
