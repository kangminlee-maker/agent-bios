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
  - 실제 대상 model에 맞는 guidance를 고른다 — bind된 tier마다 vendor document가 따로 있고, effort와 주도성과 검증에서 서로 어긋난다
  - effort level 이름은 model 사이에서 이어지지 않는다. rebind 후에는 이전 model의 설정을 그대로 쓰지 말고 level을 다시 쓸어본다
  - 목표, 제약, 요청의 이유를 밝히고 경로는 model이 고르게 둔다
  - 물려받은 process scaffolding은 유지하거나 제거하기 전에 대상 model에서 비교한다
  - 장기 과제는 여러 turn에 걸쳐 드러내지 말고 첫 turn에 전체 과제 명세를 준다
  - tool 설명은 무엇을 하는지만이 아니라 언제 호출할지를 규정한다
  - 진행 보고는 같은 session의 tool 결과에 대조해 검증하도록 요구한다
  - 경계를 명시한다 — 묻지 않고 할 일과 멈춰서 물어야 할 일
derived_at: 2026-10-21
source_pins:
  - doc: prompting-claude-opus-5
    sha256: e73cd26863642596486a43f90ff9c04d13f8e4b6cd00ae83546d4d3cd93c5143
    pinned_at: 2026-10-21
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

이 guide는 전역 Coding Guidelines의 범위 확장이다. claude tier model을 위한
prompt를 작성할 때 사용한다 — cross-family로 dispatch하는 review packet,
subagent brief, 또는 main이 Claude일 때 main 자신의 지시.

main과 다른 model을 쓰는 subagent일 때도 prompt를 받는 model의 section과 아래
공유 recipe 및 checklist를 함께 쓴다. model별 조정은 instructions의 permission 경계와
필수 verification을 보존한다.

| Target | Apply |
| --- | --- |
| `claude-fable-5-1` | 공유 recipe와 Claude Fable 5.1 |
| `claude-opus-5-5` | 공유 recipe와 Claude Opus 5.5 |
| `claude-sonnet-5-5` | 공유 recipe와 Claude Sonnet 5.5 |
| `claude-haiku-5-5` | 공유 recipe와 Claude Haiku 5.5 |
| `claude-opus-5` | 공유 recipe와 Claude Opus 5 |
| `claude-fable-5`, `claude-sonnet-5`, `claude-haiku-4-5` | 공유 recipe. 다른 model의 조정을 빌리기 전에 대상 model 자체의 guidance를 확인한다 |

## Default prompt recipe

- `Goal`과 **그 이유** — model이 의도를 추론하지 않아도 되도록 독자, 목적, 관련
  맥락을 제공한다.
- `Success criteria` — 완료의 의미와 확인 방법.
- `Constraints and boundaries` — 허용된 범위와 approval 조건을 밝힌다.
- `Tools` — 각 설명은 무엇을 하는지만이 아니라 **언제 호출할지**를 밝힌다.
  정확성이 이에 달렸다면 선행 retrieval과 validation을 명시한다.
- `Output` — 산출물 형태와 문체.

## Claude Fable 5.1

- effort 실험은 `high`에서 시작하고 지원되는 수준을 새로 비교한다. 같은 effort
  이름이라도 model마다 비용이 같을 필요는 없다.
- 짧은 시작, 진행, 최종 업데이트를 요청한다. 먼저 client가 업데이트를 표시하는지
  확인하고 충돌하는 침묵 지시는 제거한다.
- 독립적인 tool 호출은 묶는다. subagent가 실행하는 동안 lead가 독립 작업을 하게 둔다.
- 약속한 다음 단계를 포함해 승인된 요청을 완료한다. 실제 approval 경계와 사람이
  있는지를 밝히고 불필요하게 멈추지 않는다.
- 문자 그대로의 prose와 유용한 formatting을 요청한다. retrieval한 인용문을 어떻게
  표시하고 출처를 붙일지 예시로 보인다.
- 편집은 요청한 동작에 맞춰 좁게 하고 test는 비례하게 한다. 관련 없는 문제는 따로
  보고한다.
- `low`에서는 이름 인식에 기대지 말고 현재 사실을 위한 retrieval을 명시적으로
  유발한다. retrieval이 계속 실패하면 더 높은 effort와 비교한다.
- compaction summary에는 결정, 제약, 열린 작업, 정확한 세부를 보존한다.
- API history는 바꾸지 않고 append한다. 편집한 prefix에 대해 thinking을 재생하지 말고
  지원되는 compaction을 쓴다.
- `xhigh`/`max`에서는 thinking과 산출물에 쓸 token을 예산에 넣는다. 긴 출력은
  `high`와 비교한다.
- 조밀한 이미지 작업에는 crop과 zoom tool을 준다.

- `medium`은 더 낮은 비용으로 Claude Fable 5와 비슷한 결과를 내고, `low`는 작업당
  비용에서 더 작은 model들을 자주 앞선다. 더 작은 model을 높은 level로 돌릴 자리라면
  `low`도 함께 비교한다.

이는 configured seat의 effort나 permission을 바꾸는 것이 아니라 prompt와 harness의
조정 선택이다. 다른 model section의 조언은 이 model로 옮겨오지 않는다.

## Claude Opus 5.5

- 기본값은 `medium`이고, Claude Opus 5는 `high`였다. **같은** level에서 이 model이 turn당
  더 많이 생각하므로, Opus 5의 level을 그대로 가져오면 깊이가 아니라 더 긴 turn과 더 많은
  output token을 산다. `xhigh`와 `max`는 품질 이득을 측정한 작업에만 쓴다.
- thinking은 항상 켜져 있고 `thinking: disabled`는 거부된다. thinking을 대신하던 지시와
  "생각하지 말라"는 규칙은 지운다.
- tool call 사이의 진행 메모는 progress-update thinking block으로 오고, 기본 display에서는
  그 text가 비어 있다. text만 render하는 client는 긴 turn 내내 조용해 보인다.
- 무인 loop에서 text만 있는 turn 종료는 보고일 뿐 완료의 증거가 아니다. 항목을 checklist로
  들고 남은 것만 다시 지시하되, 자동 재개는 두세 번에서 멈춘다.
- 안전 classifier는 `stop_reason: "refusal"`과 분류 이름으로 거절한다. Opus 5에서 올라온다면
  생물학 관련 안전장치가 새로 생긴 부분이다.
- 도표와 스크린샷을 보조 도구 없이도 훨씬 정확히 읽는다. 이전 model용으로 만든 시각
  scaffolding은 유지하기 전에 다시 시험한다.
- multi-agent harness에서는 예산 대비 경과 시간을 한 줄 주면 팀이 더 빨리 끝낸다. 그
  예산은 권고일 뿐이므로 자체 timeout은 그대로 둔다.
- 사용자가 붙여넣은 text는 tag block으로 표시하고 system prompt에 그렇게 적는다.
- frontend 작업에서는 피할 기본 양식을 구체적으로 지목한다. "흔한 모양을 피하라"는 지시는
  기본값을 다른 기본값으로 바꿀 뿐이다.

## Claude Sonnet 5.5

- level이 Claude Sonnet 5 기준으로 다시 보정되었으므로 level을 옮겨오지 말고 다시 쓸어본다.
  사양이 분명한 agentic 작업은 `medium`에서, 더 어렵거나 긴 작업은 `high`에서 시작한다.
- `low`에서는 검사를 돌리지 않고 변경을 완료로 보고할 수 있고, `low`/`medium`에서는 긴 작업을
  끝내기 전에 되묻는다. 먼저 effort를 올리고, 그래도 필요하면 끝까지 진행과 범위 경계를
  system prompt에 적는다.
- `xhigh`와 `max`에서는 스스로 review round를 시작하고 reviewer subagent를 띄우기도 한다.
  요청한 작업의 검사가 통과하면 멈추라고 지시하자 vendor 시험에서 품질 변화 없이 session
  비용이 약 3분의 1 줄었다.
- 요청하지 않은 test, 문서, 보조 file을 모든 level에서, 높은 effort일수록 더 많이 추가한다.
  요청한 범위로 한정하려면 그렇게 명시한다.
- 여러 단계를 거쳐야 하는 추론 작업의 JSON 답에는 먼저 문제를 끝까지 생각하라는 줄을
  더하거나 `xhigh`를 쓴다. `stop_reason: "max_tokens"`는 text가 parse되더라도 실패로 다룬다.
- 때때로 tool을 대소문자가 다른 이름이나 비슷한 parameter 이름으로 호출한다. 모호하지 않으면
  받아주거나, 정확한 기대 이름을 담은 error를 돌려준다.
- 사용자 text를 tool result 안에 넣지 않는다. turn 중간 입력은 user turn으로 전달하고,
  harness 공지는 별도 message로 분리한다.

## Claude Haiku 5.5

- effort level을 갖춘 첫 Haiku이고 thinking budget을 대체하므로 이어받을 이전 설정이 없다.
  기본값은 `medium`이다.
- `low`는 가장 싸지만 검색을 건너뛰거나 일찍 멈추거나 검사를 거를 가능성이 더 크다. 지시를
  엄격히 따라야 하면 `high`를 쓴다. `xhigh`나 `max`에 비용을 치르기 전에 Claude Sonnet 5.5와
  품질·비용·속도를 비교한다.
- 검색 tool에는 오늘 날짜를 함께 준다. system prompt가 길거나 effort가 `low`면 바뀌었을 수
  있는 것을 검색하라고 명시한다. "항상 검색하라"는 포괄 지시는 필요 없는 검색만 늘리고 답을
  개선하지 않는다.
- 긴 agent prompt의 `low`에서는 일찍 멈추고 작업을 되돌려준다. 끝까지 진행하라는 지시를
  더하거나 effort를 올린다.
- `low`와 `medium`에서는 변경을 실제로 검사하지 않고 완료로 보고할 수 있다. 진짜 검사를
  요구하고 무엇이 검사로 인정되는지 적는다.
- 안전 classifier는 Haiku 4.5에서 올라오면 새로 생긴 것이고, 이 model에는 server-side
  fallback이 없으므로 거절은 client에서 처리한다.

## Claude Opus 5

다음 동작 주장과 조정 권고는 `claude-opus-5`에 적용한다. 오늘 이 model을 bind하는 tier는
없지만, 여전히 선택할 수 있으므로 남겨 둔다.

### When to add blocks

- 장기 또는 자율 작업: 잘 명세된 하나의 turn에 전체 명세를 먼저 주고 높은 effort로
  실행한다. 자기 점검 주기나 전용 verifier subagent를 **넣지 않는다**. helm binding은
  시키지 않아도 자기 작업을 검증하므로, 검증하라는 지시는 과잉 검증만 산다.
  물려받은 verification scaffolding을 지워도 능력이 줄지 않는다. 이는 보통의
  self-check 조언을 뒤집으므로, 그 조언을 일률 적용하는 prompt library에서는 이 tier를
  분리한다.
- Review: 근거 기준과 verdict 형태를 명시한다. 이 tier는 severity filter를 문자 그대로
  따르므로 “high-severity만 보고”는 버그 탐지가 좋아져도 측정 recall을 떨어뜨린다.
  모든 finding에 confidence와 severity를 붙여 보고하게 하고 filtering은 downstream에서
  한다.
- Delegation: 언제 위임하지 *않을지*를 말하고 spawn 수에 상한을 둔다. helm binding은
  subagent에 쉽게 손을 뻗는다 — 교체한 binding과 반대다 — 그리고 spawn마다 맥락을
  다시 세우고, 보고를 받고, 그 보고를 다시 읽는다. 따라서 상한 없는 delegation은
  비용과 지연을 곱한다. harness가 결정적인 cap을 제공하면 prose보다 그것을 선호한다.
  Claude Code와 Agent SDK에서는 `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`,
  `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, SDK의 `max_budget_usd`가 이에 해당한다 —
  model이 말로 넘어갈 수 없는 한계다. 의존하기 전에 harness version이 이를 지원하는지
  확인한다. 파일 기반 memory와 custom tool은 반대 경우다. 여전히 명시적인
  when-to-use trigger가 필요하다.
- 사람이 지켜보지 않는 자율 실행: 그렇다고 말한다. 그러지 않으면 필요 없는 허가를
  묻고 막힌다. 사소한 선택(명명, 기본값, 동등한 접근)에는 자율을 주되, 범위 변경과
  파괴적 행동에는 묻도록 유지한다.
- 진행 보고: 각 주장이 session의 tool 결과까지 추적 가능하고 검증하지 않은 작업은
  그렇게 표시하도록 요구한다.

### How to choose prompt shape

- 자기완결적 packet을 가진 하나의 제한된 질문 → 단일 실행. review의 기본값이다.
- 독립적인 작업 흐름 → 위임하되 spawn-and-block보다 비동기 subagent를 선호한다.
  오래 사는 agent는 subtask마다 맥락을 다시 세우지 않고 유지하며 orchestrator가 가장
  느린 하나에 묶이지 않는다.
- effort 실험은 `high`에서 시작한다. 대표 과제에서 더 낮은 설정과 비교하고, 품질이
  좋아질 때 까다로운 coding 또는 agentic 작업에서는 `xhigh`까지 올린다. 물려받은
  기본값은 다시 시험한다. configured seat의 effort는 여전히 명시적인 workload 선택이다.
  effort는 응답 길이를 제어하지 않는다 — Working rules 참고.
- model별 제약은 `targets` binding마다 다르다. thinking 구성, sampling parameter,
  effort 지원은 균일하지 않고 sweep binding이 가장 제약이 많다. 예를 들어 helm
  binding은 thinking이 기본으로 켜져 있으며 끄는 것은 `high` 이하 effort에서만
  받아들여진다. dispatch에서 의존하기 전에 live surface에서 제약을 확인한다. frontier
  binding의 규칙이 sweep binding에도 적용된다고 가정하지 않는다.

### Working rules

- 긴 turn을 예상한다. 어려운 작업의 단일 요청은 높은 effort에서 수 분 걸릴 수 있다.
  조용한 호출을 hang으로 여기지 말고 timeout, streaming, 진행 UX를 그에 맞춰 설계한다.
- “N번의 tool 호출마다 요약” 같은 scaffolding을 넣지 않는다. 이 tier는 스스로
  서술한다. coding agent에 서술이 너무 많다면 대신 발견, 방향 전환, 막힘에서만
  텍스트를 내는 침묵 기본값을 둔다. 원하는 cadence는 예시로 설명한다. style을
  긍정적으로 설명하는 편이 하지 말 것의 목록보다 낫다.
- 길이는 effort 지렛대가 아니라 prompting 지렛대다. 이 tier는 이전 세대보다 더 긴
  답과 파일을 쓰며 `effort`를 낮춰도 보이는 출력이 안정적으로 짧아지지 않는다.
  명시적인 지시만 그렇게 한다. 산출물 길이는 대화 길이와 따로 조정한다.
- 자기 정정의 범위를 좁힌다. 두면 이 tier는 이전 실수를 길게 서술해 헛도는 것처럼
  읽힌다. 독자의 결정을 바꿀 것만 고치고 평이하게 말한 뒤 계속하게 한다.
- learning을 쓸 곳을 주고 나중에 그곳을 참고하라고 말하며 파일 형식도 준다. memory
  surface가 있으면 눈에 띄게 더 잘한다.
- 산출물의 가독성을 지킨다. 마지막 메시지는 지켜보지 않은 작업을 독자가 처음 보는
  자리다. 결과부터 말하고 작업 중 약어는 뺀다.
- 남은 context countdown을 보여 주지 않는다. 이 tier는 아끼기 시작해 끝내는 대신 새
  session을 제안할 수 있다.
- 이전 binding에서 가져온 prompt 측 vision workaround를 다시 검증한다. 이 tier는 chart,
  document, diagram, UI 복제에 강하므로 workaround가 이제는 품질을 해치는 쪽일 수
  있다. crop하고 시각적으로 확인할 수 있는 tool이 여기서는 thinking만 하는 것보다 낫다.
- instruction following은 전체 context window에 걸쳐 일관되므로 긴 session 끝에서도
  규칙이 살아남게 하려고 다시 말할 필요가 없다.

### Running with thinking disabled

thinking을 끄는 것은 `high` 이하 effort에서만 받아들여지며, 보통은 잘못된 지렛대다.
비슷한 비용에서는 `low` effort에 thinking을 켠 편이 대체로 thinking을 끈 것보다 낫다.
switch보다 낮은 effort를 먼저 택한다.

끄면 두 가지 현상이 나타나며 둘 다 prompt로 고칠 수 있다.

- structured call 대신 **사용자에게 보이는 text**로 쓴 tool call. turn은 끝나지만 call은
  실행되지 않고, agentic loop에서는 새어 나온 text가 history에 남아 이후 turn을
  오염시킨다. tool이 많은 작업에서 가장 흔하다.
- 내부 XML tag가 보이는 응답으로 새어 나옴.

한 지시가 둘 다 완화한다 — call 전에 말할 수 있는 허용, 맞는 tool이 없을 때의 출구,
내부 tag의 일반적 금지다.

> tool을 쓸 때는 먼저 짧은 문장을 말해도 된다. 어떤 tool도 사용자가 요청한 일을
> 표현할 수 없다면 추측하지 말고 그렇게 말한다. 응답에 내부 또는 system XML tag를
> 넣지 않는다.

두 가지 함정이 있다. tag를 구체적으로 이름 붙이는 것은 일반형보다 **덜** 효과적이다.
그리고 prompt 어디에서든 이 tier에게 생각하지 말라거나 추론하지 말라고 하면 지운다.
그 지시는 tag 누출을 억제하는 대신 늘린다.

## Prompt assembly checklist

1. 목표, 그 이유, 성공 기준을 쓴다.
2. 경계를 명시한다 — 자유롭게 할 일과 멈춰 물을 일.
3. 각 tool에 언제 호출할지가 담긴 설명을 준다.
4. 진행 보고를 어떻게 근거지을지와 산출물이 어떻게 읽혀야 할지를 말한다.
5. 대상 model의 section을 적용하고 모순을 확인한다. 같은 과제에서 변경을 비교하고,
   대상 model이 이득을 볼 때만 물려받은 scaffolding을 제거하며, 필수 repository check와
   permission 경계는 그대로 둔다.

## Sources

공유 recipe는 `claude-prompting-best-practices`에서, 각 model section은 그 model 자체의
document — `prompting-claude-fable-5-1`, `prompting-claude-opus-5-5`,
`prompting-claude-sonnet-5-5`, `prompting-claude-haiku-5-5`, `prompting-claude-opus-5` —
에서 파생했다. `source_pins`는 이 도출에 쓴 정확한 byte를 기록한다. `targets`의 model
이름이 한 model의 동작 주장을 다른 model로 확장하지는 않는다. vendor의 page들 자체가
effort 기본값과 기대할 주도성의 정도에서 서로 어긋나므로 section을 일부러 따로 둔다.

`targets` model이 바뀌면 해당 model의 자체 current document에서 조언을 다시 도출하고
공유 recipe와의 모순을 확인한다.
`launch/check-prompting-targets.sh`는 launch config가 이 guide에 없는 model을 bind하면
실패한다. 이 check는 **naming**에 관한 것이며 `targets:`에 model을 추가하면 영구히
만족한다. guidance가 실제로 다시 도출되었는지는 결정할 수 없고 어디에서도 gate하지
않는다.
