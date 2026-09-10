---
guide_id: svg-visualization-guide
language: ko
status: active
use_when:
  - architecture, pipeline, artifact, runtime/LLM boundary, service blueprint를 SVG로 만들 때
  - IMPLEMENTATION_MAP.html에 blueprint SVG를 추가할 때
  - before/after 구조, hot path, 보류 작업, gate, quality check, artifact authority를 시각화할 때
  - prose-heavy implementation status를 compact visual decision aid로 바꿀 때
core_rules:
  - 각 SVG는 하나의 judgment question에 답한다
  - time flow와 authority flow가 다르면 분리해서 보여준다
  - input, runtime/tools, LLM, artifact, view/UI, gate, quality, postponed work, downstream work에는 stable role color를 사용한다
  - canonical artifact와 projection이 혼동되지 않도록 format과 authority를 따로 label한다
  - hot-path work는 postponed 또는 excluded work와 시각적으로 분리한다
  - dense prose보다 lane, legend, short label, explicit arrow, compact node를 우선한다
  - 가능한 경우 SVG syntax와 visual layout을 검증한다
verification_focus:
  - SVG가 하나의 clear question을 가진다
  - input과 output이 명확하다
  - runtime/tools와 LLM 책임이 시각적으로 구분된다
  - canonical artifact와 projection이 별도로 label되어 있다
  - hot path와 postponed work가 분리되어 있다
  - gate와 quality check가 서로 다른 의미로 표현된다
  - text가 겹치지 않고 arrow가 읽기 쉽다
---

# SVG Visualization Guide

복잡한 pipeline 설계, artifact 관계, runtime/LLM 책임 경계, input/output 흐름을
한 장짜리 SVG로 설명할 때 사용한다.

목표는 예쁜 그림이 아니라, 독자가 다음을 빠르게 판단할 수 있게 하는 것이다.

- 무엇이 input이고 무엇이 output인가?
- 어느 단계가 runtime/tools 작업이고 어느 단계가 LLM 작업인가?
- LLM output이 직접 artifact인가, runtime submit/validation을 거친 candidate인가?
- artifact format은 JSON, YAML, Markdown, HTML 중 무엇인가?
- 어떤 항목이 hot path에 있고 어떤 항목이 보류/사후 처리되는가?
- 어디서 runtime gate가 block하고 어디서 quality review가 disclosure하는가?

`IMPLEMENTATION_MAP.html`에는 전체 서비스 또는 구현 시스템을 적절한 추상화
수준에서 설명하는 self-contained SVG service blueprint를 포함한다.

## 슬라이드와 프레젠테이션 작업

슬라이드나 프레젠테이션 자료를 만들거나, 수정하거나, 검토할 때는 visual expression을
고르기 전에 `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/slide-writing.md`의 일반
guide를 읽어 semantic criteria를 적용한다. 명시적으로 적용 가능한 정적 HTML/PDF job
경로일 때만 그 companion runbook을 읽는다. 이 guide는 logical relationship을 화면에서
읽기 쉽게 만드는 데 도움을 주지만, 해당 guide의 source fidelity, hierarchy,
spacing, review criteria를 대체하지 않는다.

## 언제 SVG를 쓰는가

SVG를 우선 사용한다.

- before/after 구조 비교가 필요할 때
- 순차 pipeline 흐름을 설명할 때
- layer, artifact, gate, quality report, UI projection이 동시에 등장할 때
- Mermaid보다 세밀한 lane, badge, legend, arrow, exclusion box가 필요할 때
- 사용자가 브라우저나 문서에서 바로 열어볼 self-contained 시각 자료가 필요할 때

Markdown 표나 Mermaid가 더 적합한 경우:

- 개념 수가 적고 계층이 얕을 때
- 5개 이하 항목의 단순 비교일 때
- 시각적 배치보다 정확한 텍스트 diff가 중요할 때

## 기본 원칙

### 하나의 판단 질문

좋은 SVG는 "무엇을 이해하면 되는지"가 분명하다.

좋은 질문:

- Source authority가 어떻게 canonical artifact가 되는가?
- Pipeline은 왜 chunk pass와 bridge pass가 모두 필요한가?
- Before/after에서 input authority가 어떻게 바뀌었는가?
- 현재 service blueprint에서 hot path와 gate는 어디인가?

SVG가 여러 node를 포함하더라도 모든 node는 같은 질문에 답해야 한다. 상세 이력,
전체 task list, 긴 설명은 SVG 밖의 문서에 둔다.

### 시간 흐름과 권위 흐름

시간 흐름과 권위 흐름이 다르면 SVG에서 lane을 나누거나 arrow style을 달리한다.

시간 흐름:

```text
input -> stage 1 -> stage 2 -> stage N
```

권위 흐름:

```text
source/chat/decision/config
  -> canonical JSON artifact
  -> runtime projection
  -> confirmed handoff
```

### Stable Role Colors

색상 체계는 매번 동일하게 쓴다.

| 역할 | 색 | 의미 |
|---|---|---|
| Input | Blue | 사용자 source, chat, decision, config snapshot |
| Runtime/tools | Green | deterministic parse, merge, projection, id/ref/digest 생성 |
| LLM | Amber | semantic interpretation, drafting, relation judgment |
| Artifact | Slate/gray | canonical or generated file |
| View/UI | Purple | HTML review, confirmation UI, user-facing projection |
| Gate | Red | deterministic blocking check |
| Quality | Cyan | non-blocking quality report, competency question |
| Postponed/excluded | Orange | 사후 결정, 사후 수집, hot path 제외 |
| Future/downstream | Dashed gray | 다음 단계, downstream system, future redesign |

색만으로 의미를 전달하지 않는다. Legend와 node label을 함께 둔다.

### Format And Authority

중요한 node에는 가능하면 다음 중 최소 2개를 표시한다.

- 사람이 읽는 이름
- artifact 또는 concept id
- format
- owner
- authority 여부

예:

```text
Confirmed Planning Input
JSON canonical + YAML projection
Runtime owns schema/ref/digest
```

YAML, Markdown, HTML은 projection일 수 있다. Canonical artifact와 projection은
직접 label로 구분한다.

### Hot Path And Postponed Work

복잡도를 줄이는 설계에서는 "무엇을 하지 않는가"가 중요하다. Hot path와
postponed/excluded work를 같은 SVG에 보여주되, 별도 lane이나 side box로 분리한다.

예:

```text
post_decision: fields resolved by a later decision
post_collection: assets gathered in a later step
placeholder_need: reserve context for later collection
```

보류 항목은 main flow 안에 섞지 않는다.

## 권장 SVG 구조

### Title And Subtitle

제목은 대상과 목적을 함께 담는다. Subtitle은 하나의 판단 질문을 담는다.

```xml
<text class="title" x="70" y="72">Input Authority Rebuild Plan</text>
<text class="subtitle" x="72" y="108">How confirmed source authority becomes a canonical artifact</text>
```

### Legend

상단 근처에 compact legend를 둔다. Legend는 다음을 설명한다.

- role color
- artifact format
- arrow meaning
- 필요한 경우 hot path와 postponed work

### Lanes

복잡한 설계는 lane으로 읽는다. Lane 수는 작게 유지한다.

권장 lane:

```text
Inputs
Runtime/tools
LLM semantic work
Canonical artifacts
Views, gates, and quality
Postponed or downstream work
```

Before/after 비교라면 많은 lane보다 좌우 2-column을 쓴다.

### Nodes

각 node는 3-5줄 이내로 제한한다.

권장 줄 구성:

```text
Node title
Plain behavior
Important constraint
artifact_id or format
```

긴 설명은 SVG 밖의 문서에 둔다.

### Arrows

Arrow 의미를 고정한다.

- Slate arrow: 일반 dataflow
- Green arrow: runtime-owned deterministic flow
- Amber 또는 blue arrow: LLM semantic submit/candidate flow
- Red arrow: gate or blocking condition
- Dashed gray arrow: optional, future, downstream, projection-only flow

Arrow가 복잡하게 교차하면 lane, hub node, intermediate artifact를 추가한다.

## Implementation Map Blueprint

`IMPLEMENTATION_MAP.html`의 blueprint SVG는 모든 file과 task가 아니라 현재 서비스
또는 구현 시스템을 설명해야 한다.

답해야 하는 질문:

- 무엇이 service에 들어오는가?
- 무엇이 service에서 나가는가?
- 어느 step이 runtime/tools work인가?
- 어느 step이 LLM semantic work인가?
- 어떤 artifact가 canonical인가?
- 어떤 view가 generated projection인가?
- 어떤 gate가 progress를 block하는가?
- 어떤 quality check가 block하지 않고 risk를 disclosure하는가?
- 어떤 항목이 postponed, excluded, downstream, future work인가?

Blueprint는 의사결정을 도와야 한다. 긴 progress log를 읽지 않아도 현재
architecture, hot path, authority boundary, main risk를 이해할 수 있어야 한다.

## Layout Rules

권장 기본값:

```xml
<svg width="1900" height="1640" viewBox="0 0 1900 1640">
```

원칙:

- 복잡한 blueprint는 1800-1900px 폭을 기본으로 한다.
- Lane 간 여백은 30-40px 이상 둔다.
- Node 간 여백은 60-80px 이상 둔다.
- Node width는 240px 이상을 기본으로 한다.
- Font size는 고정한다.
- Letter spacing은 0 또는 작은 badge용 값만 쓴다.
- 긴 문장은 수동 줄바꿈한다.
- Text가 overflow할 수 있으면 box를 키운다.
- Arrow가 많이 교차하면 hub node를 둔다.

## Accessibility And Visual Hygiene

SVG에는 `role`, `title`, `desc`를 넣는다.

```xml
<svg role="img" aria-labelledby="title desc">
  <title id="title">...</title>
  <desc id="desc">...</desc>
</svg>
```

읽기 쉬운 visual을 사용한다.

- 단순한 fill/stroke
- 넓은 margin
- 명확한 lane
- 고정 색상 체계
- 짧은 label
- text overflow 없음
- decorative gradient, orb, blob, 과한 shadow, nested card 없음
- 불필요한 icon 없음

## 작성 절차

1. Judgment question을 한 문장으로 적는다.
2. Concept을 최대 5-6개 lane으로 나눈다.
3. Lane마다 3-5개 node를 둔다.
4. 각 node owner를 표시한다: input, runtime/tools, LLM, artifact, view, gate,
   quality, postponed, downstream.
5. Machine-consumed output에는 format과 authority를 표시한다.
6. Postponed 또는 excluded work를 별도 lane이나 side box에 둔다.
7. Arrow meaning을 일관되게 그린다.
8. Syntax와 layout을 검증한다.

## Verification

가능하면 syntax와 diff check를 실행한다.

```bash
xmllint --noout path/to/file.svg
git diff --check -- path/to/file.svg
```

SVG가 HTML에 embedded되어 있고 layout이 중요하면 browser나 screenshot으로 확인한다.

- text가 겹치지 않는다
- arrow가 의미를 가리지 않는다
- lane title과 node title을 빠르게 scan할 수 있다
- hot path와 postponed work가 시각적으로 분리되어 있다
- runtime/tools, LLM, gate, quality, artifact, view 색상이 legend와 일치한다

## Completion Criteria

SVG는 다음을 만족할 때 완료로 본다.

- 하나의 judgment question에 답한다
- input과 output이 명확하다
- runtime/tools와 LLM 책임이 label과 color로 구분된다
- canonical artifact와 projection이 구분된다
- 필요한 JSON/YAML/Markdown/HTML format이 표시된다
- hot path와 postponed/downstream work가 분리된다
- gate와 quality review가 다른 시각적 의미를 가진다
- text가 겹치지 않는다
- 가능한 경우 syntax와 diff check를 통과한다
