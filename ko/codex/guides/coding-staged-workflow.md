---
guide_id: coding-staged-workflow
language: ko
status: active
use_when:
  - execution depth·review loop·정지 조건이 필요한 의미 있는 개발 작업
  - architecture 변경, 신규 기능, cross-module·ontology 변경, review 기반 수정
  - 사용자가 구현 전에 "설계"를 요청할 때
  - review finding의 materiality 판단, 정지·재설계 시점 결정
  - 작업 계획에서 각 단계의 verification 지점과 review gate를 어디 둘지 정할 때
---

# Coding Guidelines: Staged Workflow

이 문서는 전역 Coding Guidelines의 scoped extension이다. 의미 있는 개발 작업에서 execution depth, review loop, 정지 조건을 고르는 데 사용한다.

기존 전역 규칙(요청 scope, concept economy, LLM/tool/code 경계, verification discipline, documentation hygiene) 안에서 동작한다.

사소한 편집은 경량 inspect-edit-verify 경로를 쓴다 — 여기에 전체를 정의한다:
바꾸려는 표면을 먼저 읽고; 요청이 둘 이상으로 읽히면 어떤 읽기로 행동하는지 말하고;
surgical edit을 한다 — 바뀐 모든 줄이 요청으로 추적되고, 인접 코드는 건드리지 않는다;
편집이 틀렸다면 실패할 가장 좁은 신뢰 가능한 check로 검증하고; 자신의 변경이 만든
것만 정리한다. 아래 단계들은 이 한 문장을 넘어서는 작업을 위한 것이다.

사용자가 "설계"나 design을 요청하면 design 모드에 머문다. high-level 설계와 구현 프로세스 설계에 집중한 뒤 계획, tradeoff, review gate, 구현 트리거를 제시한다. 구현은 사용자가 구현을 요청하거나 계획을 승인한 뒤 진행한다.

업무용 UI의 작업 흐름, 정보 배치, 시각적 계층이나 상호작용을 설계할 때는
`${CODEX_HOME:-$HOME/.codex}/guides/ui-design.md`를 사용한다.
범위가 정해진 작은 수정은 경량 경로로 처리한다. 이 연결이 전체 UI 재설계를
요구하는 것은 아니다.

## When To Use

- 이 워크플로는 architecture 변경, 신규 기능, cross-module 동작 변경, ontology 변경, review 기반 수정, 또는 사용자에게 보이는 동작·authority·lifecycle·validation·failure handling·roadmap 약속에 영향을 주는 작업에 쓴다.
- 완료 기준과 verification이 자명한 작은 텍스트 편집, 좁은 config 변경, 단일 파일 조정에는 경량 경로를 쓴다.
- 초기 요청보다 넓은 위험이 새 evidence로 드러나면 워크플로 깊이를 높인다.

## Stages

1. High-level 설계: 목표, scope, architecture 방향, 영향받는 concept, tradeoff, 완료 기준을 정의한다.
2. 구현 프로세스 설계: 설계를 의존성·verification 지점·review gate·재설계 트리거를 가진 순서 있는 작업 계획으로 바꾼다.
3. 구현: 승인된 설계와 프로세스 계획을 만족하는 가장 작은 viable functional 변경을 만든다.

**"최소"**는 surface area, 설정, abstraction, 선택적 scope, 구현 분산을 제한한다. 요구된 동작, runtime authority, evidence 품질, verification 깊이를 줄이는 것이 아니다 — 그것들을 덜 담은 변경은 더 작은 것이 아니라 덜 끝난 것이고, 그때 "가장 작은 viable"은 규율이 아니라 변명이 된다.

**"viable"**은 실제 동작을 뜻한다: 변경이 real input, real authority, 의도된 runtime path에 대해 돈다. mock은 테스트, fixture, 명시적으로 요청된 시뮬레이션의 자리다 — mock-backed path는 verification을 지원하지만, 아무것도 그것을 mock이라 라벨링하지 않았더라도 제품 완성으로 치지 않는다; 전체 경계는 `${CODEX_HOME:-$HOME/.codex}/guides/mock-realization-boundary.md`에 있다.

여러 단계의 작업은 시작 전에 성공 기준을 정의하고, 결국 만들어낸 것이 아니라 그 기준에 대해 검증한다. 나중에 쓴 기준은 구현을 서술하므로 구현을 실패시킬 수 없다.

pipeline을 simplify할 때, processing을 downstream으로 옮기는 것과 capture된 source field를 버리는 것은 별개의 결정이다: relocation은 공짜 simplification이지만, capture된 정보를 줄이는 것은 더 위험하며 명시적 확인이 필요하다 — "현재 consumer가 없음"은 미래 가치가 없다는 근거가 아니다.

## 변경을 만드는 일

무엇을 만들지 정하는 것과 만드는 것은 다른 규율이다. 이 절은 **요청받은 변경으로 읽히는 변경**을
남기는 쪽이다.

**가정 위에서 행동하기 전에 그 가정을 말한다.** 낭비되는 구현의 대부분은 질문에 대한 틀린 답이
아니라, 아무도 하지 않은 질문에 대한 맞는 답이다. 요청이 두 가지로 읽힐 수 있으면 어느 쪽을
택했는지 말하고 계속한다 — 일찍 드러내면 문장 하나가 들고, 작업 뒤에 드러내면 그 작업이 든다.

**surgical은 최소가 아니라 읽히는 것이다.** 요청이 요구하는 것을 건드리고, 자기 취향이 아니라 그
파일의 기존 스타일을 따르고, 인접 코드는 지금 넣는 것보다 나빠 보여도 그대로 둔다. 요청되지 않은
refactor를 실은 diff는 reviewer에게 둘을 손으로 분리하라고 강요하고, 인내심이 떨어질 때 버려지는
쪽은 개선이다.

**이번 변경이 만든 것을 정리하고, 그것만 정리한다.** dead code, 안 쓰는 import, 자기 편집이 만든
잔해는 같은 변경에 넣는다. 발견한 잔해는 문장에 넣는다 — 보이도록 이름을 대고, 그것을 소유한
사람이 결정할 수 있게 그 자리에 둔다.

**버그는 실용적일 때 고치기 전에 재현한다.** 수정 뒤에 쓴 테스트는 코드가 지금 하는 일을 한다는
걸 증명한다. 수정 전에 쓴 테스트는 실패를 이해했음을 증명하고 — 그 수정이 불필요했다거나, 보고된
것과 다른 버그를 건드렸다는 걸 알려줄 수 있는 유일한 버전이다.

**증상이 드러난 자리가 아니라 authority에서 원인을 고친다.** downstream을 깁고 있다는 신호가
둘이다: 나쁜 입력 주변에 보정 코드가 계속 쌓이는 것, 그리고 각 수정이 같은 결함의 또 다른 사례를
드러내는 것. 첫째는 값이 만들어지는 upstream으로 가라는 뜻이고, 둘째는 그 사례들이 하나의
class라는 뜻이다 — 값을 single-source로 만들고 class를 고친다. 하나씩 깁는 건 다시 차는 큐다.

**빠져 있던 공유 dependency를 공급하면 지금 고치는 하나가 아니라 모든 consumer가 깨어난다.** 어떤
수정이 여러 경로가 읽으면서 그동안 없던 값을 공급할 때 — secret, packaged file — 그 consumer들을
열거하고 각자가 무엇을 시작하는지 말한다: 과금되는 호출, 외부 쓰기, 사용자에게 보이는 출력. 그
발동이 지금 고치는 기능보다 크면, 그 목록을 수정 안의 한 줄이 아니라 결정으로 소유자에게 넘긴다.
전부 read-only이고 비용이 없는 consumer라면 gate는 필요 없다.

**flip은 그 활성화를 설계하기 전에 측정한다.** version bump, 기본값 변경, severity 재매핑이
예정되어 있으면 먼저 flip해서 전체 suite를 돌리고 모든 실패를 분류한 뒤(cascade, pinned control,
진짜 탐지, 진짜 regression) 되돌린다 — 그 개수가 활성화의 blast radius다. level 재매핑은 그 field를
읽는 모든 reader를 열거할 의무를 지운다. 하나의 level이 shipping, 수리, retry, 표시를 한꺼번에
gate하는 일이 흔하기 때문이다. 미뤄 둔 결함은 조용한 통과가 아니라 strict expected failure로
고정한다.

## Review Loop

- 각 단계에서 적절히 review loop을 돈다: self review, 가능하면 subagent review, 레포·도메인이 지원하면 structured multi-lens review(구체 tool은 아래 Environment Binding).
- material 이슈가 0이 될 때까지 반복한다: review → material 이슈 식별 → 수정 → 재review.
- "material 이슈 0"은 선언된 defect criterion의 stop-relevant class 위에서 센다; 그 criterion의 선택과 선언은 `${CODEX_HOME:-$HOME/.codex}/guides/review-defect-criteria.md`가 소유한다.
- materiality는 severity 계약을 쓴다 — canonical 정의는 아래 사다리이며, 외부 review tool은 자기 level을 여기에 매핑한다: blocker·high·medium은 material, low·info는 non-material.
- blocker는 주요 happy-path 또는 core-contract 실패로 다룬다.
- high는 지원되는 사용자·환경·데이터·실행 경로 실패로 다룬다.
- medium은 신뢰·auditability·재현성·완전성·결정 품질의 의미 있는 약화로 다룬다.
- low·info는 요청되거나 새 evidence로 승격되지 않는 한 non-blocking으로 다룬다.
- 문서가 어떤 규칙에 대해 여러 섹션을 co-authoritative로 선언하면(fixture block, conformance appendix), 모든 occurrence를 하나의 replicated value로 취급한다: 같은 pass에서 선언된 모든 위치에 편집을 전파하고, review에서 전파 완전성을 명시적으로 확인한다.

## Verification

verification은 그 자체로 하나의 주제다 — 깊이, 도메인별 메뉴, 케이스 공간 도출, 그리고 green이
무슨 값어치인지. `${CODEX_HOME:-$HOME/.codex}/guides/verification-discipline.md`에 있다.
각 단계의 verification 지점에서 그것을 돌리고, mix는 그 문서의 Verification Menus에서 고른다.

## Stop Conditions

- 이슈 경계가 이전 review보다 넓어지면 멈추고, 재설계/재작업 대 현재 iteration 지속 중 무엇을 할지 사용자에게 묻는다.
- review가 더 넓은 영향 목적, 실패 조건, 영향 영역, concept 경계, architecture 경계, severity 계급을 드러내면 경계가 넓어진 것으로 본다.
- review 라운드가 계속 material 발견을 낼 때는 고치기 전에 분류한다: 직전 라운드의 수정이 만든 회귀인지, 사전 존재하던 하나의 근본원인의 새 사례인지. 회귀면 증분을 조이고 계속한다; 회귀 0건에 사례만 재발하면 인스턴스별 패치는 다시 차는 큐다 — 위의 재설계-vs-지속 정지를 발동한다.
- 작업 완료를 선언하기 전에 현재 단계, review 결과, 남은 material 이슈, verification 결과, 정지 사유를 보고한다.

## Environment Binding (환경마다 수정)

이 가이드에서 구체 tool 이름이 나오는 유일한 섹션이다. 날짜를 붙인다; 날짜로부터 ~8주가 지나거나 bound된 tool이 바뀌면 만료로 본다.

Binding (2026-07):

| Slot | Binding | Notes |
|---|---|---|
| Structured multi-lens review | agent-launch review methods: isolated panel + Codex deep exec(`codex exec` ultra effort) + Claude ultracode workflow | Review Loop에 정의된 severity 계약을 소비/산출한다; 개인 도구는 user-owned `review-methods.local.toml`에 등록 |
| Subagent review | host CLI의 네이티브 review 메커니즘 | 예: Claude Code `/code-review` 또는 Agent-tool reviewer |
