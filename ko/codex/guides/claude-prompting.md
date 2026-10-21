---
guide_id: claude-prompting
language: ko
status: active
use_when:
  - claude 계열 model을 위한 prompt, packet, 또는 tool 설명을 작성할 때
  - Codex main에서 claude 쪽으로 cross-family review를 dispatch할 때
  - claude subagent에 prompt하거나 main이 Claude일 때 자기 자신에게 prompt할 때
  - 구세대 claude model용으로 쓴 prompt를 이식할 때
  - claude 작업의 reasoning effort 수준을 정할 때
core_rules:
  - 실제 대상 model에 맞는 guidance를 고른다 — effort 기본값, thinking 제어, 주도성, 요구할 검증의 정도가 model마다 다르며, 한 model에서 측정한 기법은 다른 model에 적용하기 전에 다시 확인한다
  - effort 수준 이름은 model 사이에 이어지지 않는다. model을 다시 묶으면 이전 model의 설정을 유지하지 말고 수준을 다시 훑는다
  - 목표, 그 이유, 완료의 의미를 밝히고 경로는 model이 고르게 둔다
  - 장기 작업은 전체 과제 명세와 완료 조건을 여러 turn에 나눠 밝히지 말고 첫 turn에 담는다
  - 진행과 완료 주장은 같은 session에서 실행한 확인에 묶고, 확인하지 않은 작업은 그렇다고 밝히게 한다
  - tool 설명은 무엇을 하는지만이 아니라 언제 호출할지를 규정한다 — 강제 tool 선택이 거부되는 model에서는 prompt가 유일한 지렛대다
  - 물려받은 process scaffolding은 유지하거나 제거하기 전에 대상 model에서 비교한다
  - 경계를 명시한다 — 묻지 않고 할 일과 멈춰서 물어야 할 일
  - 대화 history는 append-only로 유지하고, 추론을 응답에 써 내라고 요구하지 않는다
derived_at: 2026-10-21
source_pins:
  - doc: claude-prompting-best-practices
    sha256: e9bd30b6abd49cc42549387cfa7a4cd9946d79d0eb7ed2a1c12f4cf431ee04f4
    pinned_at: 2026-10-21
  - doc: prompting-claude-fable-5-1
    sha256: b921ea4d827411b3f4401fd5c92021eb7166c6c5642688321a3780297d8b5497
    pinned_at: 2026-10-21
  - doc: prompting-claude-opus-5-5
    sha256: 3432e66ac97f77b45e1ecba014c9d6d0001be7ab47b55ebe8c70f5aa55883a14
    pinned_at: 2026-10-21
  - doc: prompting-claude-sonnet-5-5
    sha256: 6886cdd2625b73be5bd74420e31c3a050c1c52b8073b9bebe15f4dcf33e44f91
    pinned_at: 2026-10-21
  - doc: prompting-claude-haiku-5-5
    sha256: e871a37701e88998c5bed2e15c586048c86d3d8ab5c333a67c60ad717e0131fd
    pinned_at: 2026-10-21
  - doc: prompting-claude-opus-5
    sha256: e73cd26863642596486a43f90ff9c04d13f8e4b6cd00ae83546d4d3cd93c5143
    pinned_at: 2026-10-21
  - doc: thinking
    sha256: 8bbc8ed20cffa039e5c2c371c64610c7e4019d2dabf1a01392a87dc0018d9375
    pinned_at: 2026-10-21
  - doc: effort
    sha256: 38cf202f17d28efe5a42f1df1de7f7af5924f76ce05abb7b5989db919ae892e5
    pinned_at: 2026-10-21
targets:
  - claude-fable-5-1
  - claude-opus-5-5
  - claude-sonnet-5-5
  - claude-haiku-5-5
  - claude-fable-5
  - claude-opus-5
  - claude-sonnet-5
  - claude-haiku-4-5
verification_focus:
  - prompt 변경은 가정하지 말고 이전 scaffolding과 A/B로 비교한다
  - effort 변경은 평판으로 고르지 말고 실제 eval set에서 수준을 훑는다
  - model별 제약은 사용 전에 live surface에서 확인한다
  - model별 조언은 조립 뒤에도 명시된 자기 section 안에 둔다
---

# Claude Prompting Guide

이 guide는 전역 Coding Guidelines의 범위 확장이다. claude tier model을 위한 prompt를
작성할 때 사용한다 — cross-family로 dispatch하는 review packet, subagent brief, 또는
main이 Claude일 때 main 자신의 지시.

main과 다른 model을 쓰는 subagent일 때도 prompt를 받는 model의 section과 아래 공유
recipe 및 checklist를 함께 쓴다. section이 있는 model마다 공식 prompting document가
따로 있으며, 한 model에서 측정한 기법은 빌려 오기 전에 대상 model에서 다시 확인한다.
model별 조정은 instructions의 permission 경계와 필수 verification을 보존한다.

| Target | Apply |
| --- | --- |
| `claude-fable-5-1` | 공유 recipe와 Claude Fable 5.1 |
| `claude-opus-5-5` | 공유 recipe와 Claude Opus 5.5 |
| `claude-sonnet-5-5` | 공유 recipe와 Claude Sonnet 5.5 |
| `claude-haiku-5-5` | 공유 recipe와 Claude Haiku 5.5 |
| `claude-opus-5` | 공유 recipe와 Claude Opus 5 |
| `claude-fable-5`, `claude-sonnet-5` | 공유 recipe에 더해, 이 model로 dispatch할 때마다 자체 prompting document(`prompting-claude-fable-5`, `prompting-claude-sonnet-5`)를 읽는다 — 이 guide는 그 model의 조정을 담지 않는다 |
| `claude-haiku-4-5` | 공유 recipe만. model별 문서가 없다. 수동 extended thinking(`enabled`와 `budget_tokens`)을 요청하지 않으면 thinking이 꺼져 있고, adaptive는 400을 반환하며, effort 수준이 없고, thinking이 켜진 동안에는 강제 tool 선택, assistant turn prefill, `temperature`와 `top_k`를 거부하며 `top_p`는 0.95와 1 사이만 허용한다 |

## Default prompt recipe

- `Goal`과 **그 이유** — model이 의도를 추론하지 않아도 되도록 독자, 목적, 관련 맥락을
  제공한다.
- `Success criteria` — 완료의 의미와 확인 방법.
- `Constraints and boundaries` — 허용된 범위와 approval 조건을 밝힌다.
- `Tools` — 각 설명은 무엇을 하는지만이 아니라 **언제 호출할지**를 밝힌다. 정확성이 이에
  달렸다면 선행 retrieval과 validation을 명시한다.
- `Output` — 산출물 형태와 문체. 피할 것이 아니라 할 것으로 표현하고, 말로 설명하기
  어려운 형식은 `<example>` tag 안에 예시를 준다.
- `Long inputs` — 문서 등 긴 자료는 맨 위에, 요청은 맨 끝에 두고, 행동하기 전에 관련
  부분을 먼저 인용하게 한다.
- `Long runs` — harness가 context를 compact하거나 model이 상태를 파일에 저장할 수 있으면
  그렇다고 말한다. 그러지 않으면 context 한도가 다가올 때 일찍 마무리하려 할 수 있다.
  여러 context window에 걸친 작업에는 상태를 둘 곳(`tests.json` 같은 구조화된 상태, 자유
  형식 진행 메모, git)을 주고, 새 window가 시작되면 그곳부터 읽으라고 말한다.

범위가 정해진 review packet은 기본적으로 하나의 자기완결적 실행으로 돌린다 — vendor의
주장이 아니라 repository 관행이다.

## Constraints by model

dispatch가 제약에 의존하기 전에 live surface에서 그 제약을 확인한다.

| Model | 기본 effort | Thinking 끄기 | `tool_choice` `any` / `tool` |
| --- | --- | --- | --- |
| Fable 5.1 | `high` | 거부 — 항상 켜짐 | 거부 |
| Opus 5.5 | `medium` | 거부 — 항상 켜짐 | 거부 |
| Sonnet 5.5 | `high` | 거부. `between_tools`가 `high` 이하에서 선행 thinking을 끈다 | 거부 |
| Haiku 5.5 | `medium` | `high` 이하에서 허용 | 허용 |
| Opus 5 | `high` | `high` 이하에서 허용 | 허용 |

- 강제 tool 선택이 거부되는 model에서는 `tool_choice`를 `auto`로 두고, tool이 언제 해당하는지
  prompt에 밝히며, schema에 맞는 JSON은 strict tool use나 structured outputs가 제공되는
  곳에서 얻는다(모든 platform에서 제공되지는 않으며, 없으면 prompt로 형식을 요청한다).
  허용되는 model에서는 강제 호출이 thinking을 건너뛰므로 `auto`와 지시를 우선한다.
- 수동 thinking(`enabled`와 `budget_tokens`)은 다섯 model 모두에서, 마지막 assistant turn의
  prefill은 Haiku 4.5를 뺀 모든 target에서 400을 반환한다. effort, 지시, structured outputs가
  그 자리를 대신한다.
- 다섯 model과 Fable 5, Sonnet 5에서 `temperature`, `top_p`, `top_k`를 생략한다. 기본값이
  아닌 값은 400을 반환하고, `temperature`와 `top_p`를 함께 보내면 기본값이어도 그렇다.
- thinking은 `max_tokens`에 포함되므로 여유를 두고, 21,333을 넘으면 stream한다(SDK 규칙).
- history는 append-only로 유지한다. 각 assistant turn을 thinking block까지 반환된 그대로
  되돌려 보낸다. Fable 5.1과 5.5 계열에서는 이전 message 편집, `system`이나 `tools` 재구성,
  이전 turn의 제자리 요약이 그 뒤의 모든 thinking block을 무효화한다. turn마다의 reminder는
  turn-scoped system message로 보내고, 정리는 server-side compaction에 맡긴다. thinking
  block은 그것을 만든 model과 일부 다른 model만 읽을 수 있으므로, model을 바꾸면 이전 추론이
  버려질 수 있다.
- 추론을 응답에 그대로 또는 정해진 형식으로 써 내라고 요구하지 않는다. Fable 5.1, Opus 5.5,
  Sonnet 5.5, Opus 5에서는 그런 prompt, skill, tool 설명이 `reasoning_extraction`으로 거절될
  수 있다. 짧은 설명이나 수행한 행동의 요약을 요청하거나, `display: "summarized"` thinking
  block을 읽는다.
- 거절은 `stop_reason: "refusal"`과 `stop_details`의 category로 돌아오며 답이 아니다. 어떤
  category를 server-side fallback이 재시도하는지는 각 model의 문서가 말하고, Haiku 5.5는
  fallback이 없으며 다시 보내도 대개 다시 거절한다.
- 요청 사이에 최상위 `effort`를 바꾸면 prompt cache가 처음부터 다시 시작된다. Fable 5.1,
  Opus 5.5, Opus 5, Sonnet 5.5, Haiku 5.5에서는 대화 중 effort 변경을 message 단위 형식(beta)으로
  하며, 새 입력이 있는 다음 user turn부터 적용된다. 이 형식은 adaptive thinking이 필요하다.
  Haiku 5.5에서 thinking을 끄거나 Sonnet 5.5에서 `between_tools`를 쓰면 400이다.

## Claude Fable 5.1

이 문서는 Claude Mythos 5.1도 다룬다. Fable 5 prompt는 바꾸지 않아도 그대로 쓸 수 있다.

- Effort: 기본값 `high`에서 시작해 나머지 수준을 자체 eval에서 시험한다. 수준 이름이
  model마다 같은 양의 thinking을 뜻하지 않는다. `medium`은 더 낮은 비용으로 Fable 5와
  대략 같고, `low`는 과제당 비용에서 Opus와 Sonnet model과 경쟁할 만하면서 점수는 더 높은
  경우가 많다 — 더 작은 model을 더 높은 수준으로 돌리려던 곳이면 비교에 넣는다.
- 진행 text: 긴 tool 호출 turn에서 사용자에게 보이는 업데이트를 더 적게 쓰며, effort가
  높을수록 더 그렇다. 먼저 client가 progress-update `thinking` block(`display: "updates"`,
  beta)을 표시하는지 확인하고, 다음으로 서술을 억제하는 줄을 지우고, 그다음에 한 줄 시작,
  짧은 업데이트, 홀로 읽히는 마무리 요약을 요청한다. UI가 tool 출력을 숨기면 그렇다고
  말한다. 그러지 않으면 아무도 보지 못할 출력을 "보여 주려고" 명령을 실행한다.
- 묶음 호출: coding과 computer-use loop에서는 과제에 암시된 호출을 turn당 하나씩 낼 수
  있다. 다음에 필요한 것을 나열한 뒤 독립적인 항목을 한 번에 모두 요청하라고 짧게
  유도한다 — tool 결과를 보낼 때마다 turn-scoped system message(beta)로, 또는 `tool_result`
  block 뒤의 text block으로. turn마다 새 복사본을 덧붙이고 이전 복사본은 지우지 않는다.
- 마무리: 긴 비동기 작업에서 다음 단계를 실행하는 대신 예고하거나, 이미 요청된 작업에
  허가를 구할 수 있다. 자율 block(사용자가 지켜보지 않는다; 되돌릴 수 있는 행동은
  진행한다; 파괴적 행동이나 실제 범위 변경에서만 멈춘다; 마지막 문단이 약속한 일을
  한다)이 효과의 대부분을 내고, 두 번째 block은 요청 자체를 범위로 정한다. 두 예외는
  유지한다 — 변경 요청 없이 문제를 설명하거나, 질문하거나, 생각을 소리 내어 말하는 것이면
  수정이 아니라 판단을 내놓는다; 시스템 상태를 바꾸는 명령은 바로 그 행동을 뒷받침하는
  증거가 있어야 한다. 그리고 모호한 요청에서 덜 묻게 되는지 확인한다.
- 요청 밖의 추가 작업: 주변 code를 고치거나 변경에 비해 많은 test를 commit할 수 있다.
  빼야 할 것을 명시한 지시를 주면 과제 성공률의 측정 가능한 변화 없이 둘 다 줄어들고,
  작업 중 발견한 기존 버그나 언급되지 않은 동작은 고치지 말고 후속 과제로 보고하게 한다.
  Fable 5보다 파일 전체를 더 쉽게 다시 쓰므로 부분 편집을 요청한다.
- Compaction: server-side compaction이면 맡겨 둔다. client에서 compact한다면 요약이 보존할
  것을 말한다 — 생긴 문제와 처리 방식, 제기되거나 보류된 선택지, 결정되거나 배제된 것(정확히
  그대로), 현재 위치, 아직 열려 있거나 약속된 것, 다시 만들기 어려운 세부(정확히 그대로).
- 문체: Fable 5보다 조밀하고 formatting을 덜 쓴다 — formatting 금지 규칙은 언제 formatting이
  도움이 되는지로 바꾼다. "Please remove all mannered prose."가 통한다. 요약에서 출처
  구절을 인용 표시 없이 옮길 수 있으므로, 올바른 응답과 그 이유를 담은 완전한 예시 하나를
  준다.
- `low`의 검색: 기억에서 더 쉽게 답한다. 해당 turn만 effort를 올리거나, 이름을 안다는
  것이 현재 상태를 안다는 뜻은 아니며 쓰인 그대로 검색하라고 말한다.
- `xhigh`/`max`의 긴 산출물: thinking에서 초안을 쓰고 다시 한 번 쓸 수 있다. `high`에서
  실행하거나, `max_tokens`를 thinking과 답변에 맞춰 잡고 둘이 하나의 한도를 공유한다고
  말한다.
- Subagent: lead가 계속 일하게 둔다 — 시작 tool은 즉시 반환하고, 결과는 나중 user
  message로 전달하며, 기다리는 tool을 따로 둔다. 그래도 스스로 기다리는 때가 많다.
- 조밀한 이미지: crop해 확대하는 tool 하나만으로도 효과의 대부분을 얻는다. 오탐 거절은
  compile 확인식 표현(대신 "버그가 있는가"로 묻는다), 덜 알려진 언어(맥락을 준다), tool
  출력의 base64(제거한다)에서 늘어난다.

## Claude Opus 5.5

Opus 5 prompt는 그대로 쓸 수 있고, Opus 5 section은 여전히 합리적인 출발점이다.

- Effort: 기본값은 `medium`이다(Opus 5는 `high`). Opus 5 값을 넘겨 쓰지 말고 명시적으로
  설정해 훑는다. coding과 knowledge-work eval에서 `medium`이 Opus 5의 `high`와 같거나
  그보다 낫고, 여러 coding eval에서는 `low`도 그에 근접한다. 같은 수준에서 Opus 5보다
  turn당 thinking이 많으며 `xhigh`/`max`에서 가장 그렇다 — Opus 5 값을 그대로 두면 turn이
  길어지고 출력 token이 는다. 따라서 `max_tokens`에 여유를
  두고(긴 agentic coding turn에는 128,000이 잘 맞았다), `xhigh`/`max`는 품질 향상을 측정한
  곳에만 쓰며, thinking을 줄이려면 prompt보다 effort를 먼저 낮춘다.
- Thinking은 항상 켜져 있다. Opus 5에서 thinking을 끄고 돌리던 prompt라면 `low`에서
  시작해 측정하고, thinking을 대신하던 지시를 지우고, Opus 5의 thinking-off 완화책은 다시
  시험하되 "생각하지 말라"는 규칙은 어느 경우든 지우며, 응답은 block type으로 읽는다.
  chat에서는 "신중히 생각하라"는 줄을 지운다. 이전 답을 확정된 것으로 다루라고 하면
  후속 turn의 thinking이 줄지만, 긴 분석과 agentic 작업에서는 빼고, model 스스로의 정정을
  막는지 시험한다.
- 무인 실행: 일부 진행 업데이트가 text로 turn을 끝낸다(`end_turn`). text로만 끝난 turn은
  완료의 증거가 아니라 보고로 취급한다. 과제 항목을 model이 갱신하는 checklist에 두고,
  열린 항목을 이름 붙인 짧은 user message를 보내며, 자동 계속은 두세 번에서 멈추고, model이
  시작한 background 명령이나 subagent는 끝나길 기다린다. 피해야 할 조기 중단(다음 단계를
  예고하며 끝나는 요약, 계속할지 묻는 제안, 막지 않는 결정 목록, 이정표에서 멈춤)과
  원하는 중단을 이름 붙인 system prompt 문단은 조기 중단을 더 드물게 만든다. 첫 요청부터
  넣고, 위험한 행동에는 자체 확인 단계를 유지하며, 사람이 답할 수 있는 곳에서는 뺀다.
- 진행 text는 progress-update `thinking` block으로 오며 기본 display에서는 비어 있다 —
  `display: "updates"`(beta)를 설정한다. 그대로 전달할 내용을 위한 send-to-user tool은 첫
  요청부터 선언한다. 조용한 tool 단계가 다섯 번쯤 이어지면 한 줄 reminder를 turn-scoped
  system message로 두세 번까지 덧붙인다. 지우지 않고 덧붙이므로 cache와 thinking block이
  유지되며, 긴 침묵을 비용 변화 없이 대략 절반으로 줄였다.
- 빨리 일에 착수한다. 명세가 느슨한 다중 앱 과제에서는 과제가 이름 대지 않은 출처까지
  관련 출처를 먼저 살핀 뒤 행동하라고 말한다 — 찾은 것을 그대로 행동에 옮기므로, 검색하는
  기록에서 신뢰할 수 없는 내용은 빼 둔다.
- 경과 시간에 맞춰 속도를 낸다. `elapsed 340s / 1200s` 같은 harness 줄은 agent team이 비슷한
  품질로 더 일찍 끝내게 한다. 예산은 권고일 뿐이므로 자체 timeout을 유지하고, 검색과
  검증이 조금 줄 수 있다.
- 붙여넣은 text: 하나의 무작위 id를 단 `<pasted_content id="…">` tag로 감싸고, 그 안의 지시는
  사용자가 요청한 곳에서만 따르라고 system prompt에 적는다. tag는 흉내 낼 수 있으므로 여러
  방어책 중 하나일 뿐이다.
- 안전 classifier가 생물학, 사이버보안, 추론 추출을 다룬다. 생물학 safeguard는 Fable 5.1과
  같으며 Opus 5에서 넘어오면 새로 생긴 것이다.
- 조밀한 이미지: tool 없이도 chart, diagram, screenshot을 더 정확히 읽으므로 이전 model용
  scaffolding은 다시 시험한다. 가장 조밀한 입력에는 고해상도와 crop·측정 tool이 여전히
  도움이 되며(effort가 높을수록 더), effort만 올리면 기술 도면에는 도움이 되지만 chart에는
  아니다. Frontend: "generic한 느낌을 피하라"는 기본값 하나를 다른 기본값으로 바꿀 뿐이다
  — 피할 pattern을 이름 대고, 결과를 살핀 뒤 목록을 늘린다.

> **2026-10-21 model-currency 도출(3e62fbd)에서 이어 온 내용이다. 현재 pin한
> `prompting-claude-opus-5-5`는 이를 말하지 않는다. 다음 재도출 때 다시 도출하거나 지운다.**
>
> - Opus 5의 effort 수준을 그대로 가져가면 더 깊어지는 것이 아니라 turn만 길어진다.

## Claude Sonnet 5.5

Sonnet 5 prompt는 그대로 쓸 수 있다. 가장 어려운 장기 작업에는 Opus model이 더 나은
선택이다.

- Effort: 수준이 재보정되었으므로 새로 훑는다. agentic이거나 지연에 민감한 작업이 아니면
  기본값 `high`에서 시작한다. agentic coding은 명세가 분명하면 `medium`, 더 어렵거나 길면
  `high`, chat은 `medium`이나 `low`. `low`에서는 thinking을 짧게 유지하고 변경 검증을
  건너뛸 수 있으며, `low`와 `medium`에서는 긴 과제를 끝내기 전에 확인하러 멈출 가능성이
  더 크다. agentic coding에는 `max_tokens`를 128,000으로 두고 stream한다. prompt로 thinking을
  줄여 달라는 요청은 안정적으로 듣지 않는다.
- 주도성: `low`/`medium`에서 작업을 끝까지 끌고 가려면 먼저 더 높은 effort를 시험한다.
  effort를 유지하려면, 요청된 것이 모두 끝날 때까지 계속하고 사용자 없이는 진행할 수
  없거나 위험한 단계 앞에서만 멈추라고 말한다. 모든 effort에서 test, 문서, 보조 파일을 덧붙이며 높을수록 더하다. "요청한 작업이 끝나고
  확인되면 멈춰 보고하고, 추가 작업은 하지 말고 언급만 하라"가 이를 제한한다.
  `xhigh`/`max`에서는 스스로 review 회차와 reviewer subagent를 시작하므로 일상 작업은
  `high` 이하에서 돌린다. 한 문단 — 요청한 작업이 끝나고 그 check가 통과하면 멈춰 보고하고,
  사용자가 요청하지 않았으면 추가 review 회차를 시작하거나 reviewer subagent를 띄우지 마라 —
  을 넣자 `max`에서 reviewer subagent가 멈췄고 session 비용이 약 3분의 1 줄었으며 품질
  변화는 없었다. 스스로 시작하는 review 회차는 줄었지만 사라지지는 않았다.
  아이디어나 계획을 원하면 거기서 멈추라고 말한다.
- `between_tools`는 가장 낮은 thinking 설정이며 `high` 이하에서 허용된다. 이 설정에서는
  message 단위 effort가 400을 반환하고, 생각하지 말라는 지시는 내부 XML tag를 새어 나오게
  하므로 지워야 한다. tool 없는 요청에서는 thinking을 전혀 하지 않는다는 뜻이다.
- 추론 과제의 JSON 출력: structured outputs를 쓰면 `low`와 `medium`에서 thinking을 자주
  건너뛴다. "답하기 전에 문제를 끝까지 생각하라"를 넣거나(`high`에서 `xhigh`에 가까운
  정확도) `xhigh`로 실행하되, `between_tools`가 아니라 adaptive thinking을 쓴다. `stop_reason`
  이 `"max_tokens"`이면 text에 유효한 JSON이 있어도 실패로 취급한다. structured outputs를
  쓸 수 없으면 최종 JSON 앞에 풀이를 쓰는 일이 잦아 응답 전체를 JSON으로 기대하는 parser가
  실패한다. 첫 중괄호부터 마지막 중괄호까지 자르지 말고, 문서의 추출 절차(겹치지 않게
  parse한 마지막 값 또는 여러 record 답에서는 마지막 값 묶음, field 확인, 한 번 재시도)를
  따른다.
- 한두 문장을 넘는 진행 text는 progress-update `thinking` block으로 온다 — adaptive
  thinking에서는 `display: "updates"`(beta)를 설정한다. `between_tools`에서는 요약 text가
  어차피 돌아오고 `display`는 거부된다. "발견을 최종 응답까지 보류하라"는 줄은 지운다.
  조용한 단계가 다섯 번쯤 이어지면 한 줄 reminder를 turn-scoped system message로 두세
  번까지 덧붙인다.
- turn 도중 입력: tool 결과 뒤의 harness text를 injection으로 읽을 수 있다. 사용자 text를
  `tool_result` 안에 넣지 않는다. 마지막 `tool_result` 뒤에 text block으로 덧붙이고, harness
  알림은 별도 system message에 두며, 대화형 session에서는 tool 결과 뒤에 token countdown을
  넣지 않는다.
- 검증: `low`에서는 변경을 실행해 보는 확인 없이 완료로 보고할 수 있다. 실제 test,
  type-check, build를 요구하는 문단을 넣으면 비용이 조금 늘면서 그 경우가 드물어진다.
  구문만 확인하거나 시작에 실패한 명령은 인정하지 않고, 선언된 의존성이 빠진 것뿐이면
  project 자체의 package manager와 lockfile로 설치하되(sudo나 시스템 package manager로는
  하지 않는다), 건너뛴 확인은 완료로 보고하는 대신 그 이유와 함께 이름 댄다.
- tool 이름: 선언된 tool을 대소문자가 틀린 이름으로 부르거나, 알려진 parameter를 조금 다른
  이름으로 넘기는 때가 있다. 대응이 모호하지 않으면 받아들이거나, 정확한 기대 이름을 적은
  `is_error` 결과를 돌려준다. 보통 다음 turn에 호출을 고친다.
- chat과 knowledge work: 검색하면 바뀐 세부를 잡을 수 있는데도 학습 지식으로 답하는 때가
  있다. "tool 호출을 최소화하라"는 표현을 지우고, 바뀌었을 수 있는 세부(허용·요구·요금)는
  검색하라고 말한다.
- 조밀한 이미지: crop, zoom, 또는 code 실행 tool을 준다. chart에서는 모든 effort에서 tool이
  도움이 되고(`high`에 tool을 준 쪽이 `max`에 tool 없는 쪽보다 낫고 더 싸다), 기술 도면에서는
  `high` 이상에서만 그렇다.

## Claude Haiku 5.5

Haiku 4.5 prompt는 그대로 쓸 수 있다. effort 수준이 있는 첫 Haiku이며, effort가 Haiku 4.5의
thinking budget을 대체한다. system prompt text 추가는 새 대화에서만 한다.

- Effort: `low`는 chat, 짧은 tool 과제, 대량 요청용(긴 agent prompt에서는 검색 건너뛰기,
  조기 중단, 확인 생략이 더 잦아진다). 기본값 `medium`은 agentic coding을 포함한 대부분의
  작업용. `high`는 knowledge work, 더 긴 agent 과제, 엄격한 instruction following용.
  `xhigh`/`max`에서는 Sonnet 5.5에서도 eval을 돌려 성능, 비용, 속도를 비교한다. 바로 답하라고 해도 thinking을
  멈추지 않았으므로 effort를 낮춘다. 다중 turn chat의 `xhigh`에서는 답 전체를 thinking에
  쓰고 보이는 text 없이 turn을 끝내는 일이 있으므로 빈 답을 확인한다.
- 검색: 오늘 날짜를 준다. 한 번 렌더링해 이후 요청에서도 바꾸지 않고 보내고, 날이 바뀐
  뒤 이어지는 대화에서는 새 날짜를 가장 최근 turn에 준다. prompt가 길거나 `low`라면
  날짜 뒤에, 학습 데이터는 오늘보다 훨씬 전에 끝나며 바뀔 수 있는 사실은 확신이 들어도
  검색하라고 덧붙인다. "사실 질문은 무엇이든 검색하라"는 일괄 규칙은 검색이 필요 없는
  prompt의 절반에서 검색했고 정답은 늘지 않았다.
- 자체 tool과 JSON: thinking을 끄면 필요한 tool 호출을 건너뛸 수 있다. adaptive thinking을
  쓰거나, tool이 반드시 실행돼야 하는 요청에서 `output_config.format`을 빼거나,
  `tool_choice`로 호출을 강제한다. thinking을 꺼야만 한다면 JSON 형식은 최종 답에만
  해당하며 tool은 앞에 text 없이 먼저 호출하라고 말한다.
- 조기 중단: 긴 coding-agent prompt에서 `low`일 때 과제를 사용자에게 되돌릴 수 있다. 끝날
  때까지 계속하고 막혔거나 위험한 단계 앞에서만 멈추라고 말한다. `low`에서 `medium`으로
  올리면 조기 중단이 대략 절반으로 줄고 출력 token은 두 배 넘게 는다. `low`/`medium`에서는
  확인 없이 변경을 완료로 보고할 수도 있다. Sonnet 5.5와 같은 실제 확인 문단을 넣자 더
  자주 확인했고, token이 늘면서 결과도 좋아졌다.
- 거절: 안전 classifier가 `stop_reason: "refusal"`로 거절한다. Haiku 4.5에서 넘어오면 이런
  거절은 새로 생긴 것이며, server-side fallback이 없으므로 client가 처리한다.
- turn 도중 입력과 chatbot: 사용자 text를 `tool_result` 안에 넣지 않는다. 마지막
  `tool_result` 뒤에 덧붙이고 알림은 별도 system message에 둔다. chatbot이라면 system
  prompt의 규칙이 반박, 동정을 구하는 이유, 반복 요청에도 대화 내내 유지된다고 말하고,
  준수가 가장 중요할 때는 `high`를 쓴다. 답에 추론 같은 text가 보이면 adaptive thinking과
  `medium`으로 바꾼다.

## Claude Opus 5

지금 `claude-opus-5`를 묶는 tier는 없다. 이 section은 아직 그 model로 보내는 prompt를
위해 남긴다.

- Effort: 기본값 `high`에서 시작해 다시 훑는다. `low`와 `medium`은 token의 일부만으로
  강한 품질을 유지하고, `xhigh`는 까다로운 coding과 agentic 작업용이다. 전체 명세를 먼저
  주고 맡겨 두었을 때 가장 잘한다.
- Review: 실제 버그를 높은 비율로 찾고 오탐이 적으며, 정확도는 낮은 effort에서도 유지된다.
  증거 기준과 판정 형식을 밝힌다. "high-severity만 보고"는 문자 그대로 따라 보고를 줄이므로, 모두 보고하게 하고 별도
  단계에서 filtering한다.
- 검증: 시키지 않아도 자기 작업을 검증한다. 검증하라고만 말하는 scaffolding — 모든 과제의
  자기 점검 단계, verifier subagent, "다시 확인" 규칙 — 은 지운다. 지워도 품질 손실 없이
  token이 줄어든다. repository의 필수 check와 사용자의 명시적 요청은 그런 scaffolding이
  아니다. 이는 일반적인 자기 점검 조언과 반대이므로, 그 조언을 모든 model에 적용하는 prompt
  library에서는 이 model을 예외로 둔다. 스스로 판단해 과제를 넓힐 수 있으므로 좁은 과제는
  범위를 명시해 제한한다.
- 위임: 쉽게 위임하며, 작은 과제에서는 비용과 시간이 곱절로 는다. 어떤 작업이 subagent에
  적합하고 어떤 작업이 아닌지 말하고, 결정적인 cap을 선호한다 —
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, SDK의
  `max_budget_usd`(Claude Code 2.1.217 이상). Claude Code는 `claude_code` preset을 쓸 때만
  자체 위임 지시를 추가한다.
- 길이: 응답과 파일이 이전 Opus model보다 길고, effort를 낮춰도 보이는 응답이 안정적으로
  짧아지지 않는다. 간결함을 명시적으로 요청하고, 작성 문서의 길이는 대화의 길이와 따로
  조정한다.
- 긴 context: instruction following, tool 호출, 추론이 1M token window 전체에서 일관되므로
  일반적인 규칙은 끝부분에 다시 말할 필요가 없다. 문서화된 예외는 간결함 지시 하나다. 긴
  system prompt에서는 그 지시에 끝부분의 짧은 reminder를 짝지어 둔다.
- 서술: 하려는 일을 예고한다. 원하는 cadence를 설명한다(첫 호출 전 한 줄, 발견이나 방향
  전환 때 업데이트, 마지막에는 결과부터). 긍정적인 예시가 하지 말 것의 목록보다 낫다.
  정정 서술은 독자의 code나 결정을 바꿀 오류로 한정한다.
- 조밀한 이미지: chart, 문서, diagram 이해와 UI 재현에 강하다. 이전 model용 workaround는
  이제 오히려 품질을 깎을 수 있으므로 다시 검증한다. crop하고 시각적으로 확인하는 tool이
  thinking만 하는 것보다 비용 대비 효과가 크다.
- Thinking 끄기는 `high` 이하에서 허용되지만 보통 잘못된 지렛대다. 비슷한 비용에서는
  `low`에 thinking을 켠 편이 낫다. 끄면 tool 호출을 text로 쓸 수 있고 — 그 호출은 실행되지
  않으며 text가 history에 남아 이후 turn에도 영향을 주고, 검색처럼 tool을 많이 쓰는 작업에서
  가장 잦다 — 내부 XML tag를 새어 나오게 할 수도 있다. 한 지시가 둘 다 완화하고(tool 호출 전에 짧은 문장을 말해도 된다;
  맞는 tool이 없으면 그렇게 말한다; 내부 XML tag는 넣지 않는다), 일반형이 tag 이름을
  대는 것보다 낫고, "생각하지 말라"는 규칙은 지워야 한다.

> **2026-09-07 도출에서 `prompting-claude-opus-5`의 이전 판(65be3e…)을 근거로 이어 온
> 내용이다. 현재 pin한 문서는 이를 말하지 않는다. 다음 재도출 때 다시 도출하거나 지운다.**
>
> - Review: 모든 발견에 confidence와 severity를 붙여 보고하게 한 뒤 filtering한다.
> - 위임: spawn할 때마다 context를 다시 쌓고, 보고하고, 그 보고를 다시 읽으므로 제한 없는
>   위임은 비용과 지연을 곱절로 늘린다. 결정적인 cap은 model이 말로 넘어설 수 없는 한도다.
>   spawn하고 기다리는 방식보다 비동기 subagent를 선호한다. 오래 사는 agent는 하위 과제마다
>   context를 다시 쌓지 않고, orchestrator가 가장 느린 agent에 묶이지 않는다.
> - 파일 기반 memory와 custom tool에는 언제 쓸지에 대한 명시적 trigger가 필요하다. 배운 것을
>   적을 곳을 주고, 나중에 그곳을 참고하라고 말하고, 파일 형식을 정해 준다. memory surface가
>   있으면 눈에 띄게 더 잘한다.
> - 지켜보는 사람이 없는 자율 실행: 그렇다고 말한다. 그러지 않으면 필요 없는 허락을 구하며
>   멈춘다. 사소한 선택(이름, 기본값, 동등한 접근)에는 자율을 주고, 범위 변경과 파괴적 행동은
>   계속 묻게 한다.
> - 긴 turn을 예상한다. 어려운 과제의 요청 하나가 높은 effort에서 몇 분씩 걸릴 수 있으므로,
>   조용한 호출을 멈춤으로 보지 말고 timeout, streaming, 진행 표시를 그에 맞춘다.
> - "N번 tool 호출마다 요약하라"는 scaffolding을 넣지 않는다. 스스로 서술한다. coding agent가
>   너무 많이 서술하면 침묵을 기본으로 둔다. 발견, 방향 전환, 막힘이 있을 때만 text를 쓴다.
> - 마지막 message에서는 작업 중에 쓰던 약칭을 뺀다.
> - 남은 context countdown을 보여 주지 않는다. 아끼기 시작하고 끝내는 대신 새 session을
>   제안할 수 있다.

## Prompt assembly checklist

1. 목표, 그 이유, 성공 기준을 쓴다.
2. 경계를 명시한다 — 자유롭게 할 일과 멈춰 물을 일.
3. 각 tool에 언제 호출할지가 담긴 설명을 주고, dispatch가 의존하는 tool과 출력 설정을
   대상 model이 받아들이는지 확인한다.
4. 마지막 message에 무엇이 담겨야 하는지, 진행과 완료 주장을 무엇에 근거시키는지, 산출물이
   어떻게 읽혀야 하는지 말하고, 작업이 남은 채 text로 끝난 turn을 harness가 어떻게 다룰지
   정한다.
5. 대상 model의 section을 적용하고 모순을 확인한다. 같은 과제에서 변경을 비교하고, 대상
   model이 이득을 볼 때만 물려받은 scaffolding을 제거하며, 필수 repository check와
   permission 경계는 그대로 둔다.

## Sources

공유 recipe와 append-only·추론 규칙은 `claude-prompting-best-practices`에서, 제약은
`thinking`, `effort`, model 문서에서, 각 model section은 자체 문서(`prompting-claude-fable-5-1`,
`prompting-claude-opus-5-5`, `prompting-claude-sonnet-5-5`, `prompting-claude-haiku-5-5`,
`prompting-claude-opus-5`)에서 파생했다. 첫 turn 명세와 확인된 주장에 관한 핵심 규칙은
Opus 5, Opus 5.5, Sonnet 5.5, Haiku 5.5 문서가 각자 자기 model에 대해 하는 말을 일반화한
것이다. `source_pins`는 이 도출에 쓴 정확한 byte를 기록하며, `targets`의 model 이름이 다른
model의 주장을 그 model로 확장하지는 않는다. vendor의 문서들이 effort 기본값과 기대할
주도성의 정도에서 서로 다르기 때문이다.

`targets` model이 바뀌거나, 여기 section이 없는 대상이 자체 prompting 문서를 갖게 되면, 그
문서에서 조언을 다시 도출하고 공유 recipe와의 모순을 확인한다. `launch/check-prompting-targets.sh`는 launch config가 이 guide에
없는 model을 bind하면 실패한다. 이 check는 **naming**에 관한 것이며 `targets:`에 model을
추가하면 영구히 만족한다. guidance가 실제로 다시 도출되었는지는 결정할 수 없고
어디에서도 gate하지 않는다.
