---
guide_id: implementation-map
language: ko
status: active
use_when:
  - 구현 코드가 있는 레포에서 IMPLEMENTATION_MAP.html 생성·갱신
  - 그 안의 단일 SVG service blueprint 구축
  - current-state dashboard에 무엇을 넣고 무엇을 격리된 history note로 뺄지 결정
---

# Implementation Map 가이드

전역 지침의 **Implementation Map** 섹션의 scoped extension이다. 구현 코드가 있는 레포에서 `IMPLEMENTATION_MAP.html`을 생성·갱신할 때 쓴다.

## Purpose

`IMPLEMENTATION_MAP.html`은 **current-state dashboard**다 — "이 작업이 지금 어디에 있고, 다음을 무엇이 결정하며, 무엇이 위험한가"에 답하지, "무슨 일이 있었나"에 답하지 않는다. changelog, handoff log, 누적 project diary가 아니다.

## Build / rebuild rules

- 현재 작업, 현재 architecture, 현재 위험, 현재 결정, 현재 verification 상태를 중심으로 다시 만든다.
- 완료된 history는 가장 작은 유용한 요약으로 압축한다; 상세 과거 진행, 폐기된 대안, 긴 완료-작업 목록은 격리된 note(`docs/`, `design/`, `archive/`)에 둔다.
- 첫 viewport는 현재 목표, phase, health, 다음 결정, 주요 위험을 보여야 한다.
- status, architecture, roadmap, 결정, 위험, verification, 변경 영향에 대한 compact한 visual 섹션을 가진 self-contained HTML view로 만든다.
- commit 전, handoff 작성 시, 또는 의미 있는 architecture·roadmap·위험·결정·verification 변경 뒤에 갱신한다.

## The SVG service blueprint

전체 서비스나 구현된 시스템을 적절한 추상화 수준에서 시각화하는 self-contained SVG service blueprint를 **정확히 하나** 포함한다. `${CODEX_HOME:-$HOME/.codex}/guides/svg-visualization-guide.md`를 써서 만든다.

- blueprint는 하나의 판단 질문에 집중한다; 파일·작업을 망라하지 말고 compact한 node를 쓴다.
- 안정적인 lane, legend, 고정 role color, 짧은 label, 명시적 arrow로 다음을 분리한다: input, runtime/tool, LLM work, canonical artifact, view, gate, quality check, 보류 작업, downstream/future 작업.
- time flow와 authority flow를 구분하고, canonical artifact와 JSON/YAML/Markdown/HTML projection을 구분한다.
- 실용적일 때 SVG 문법·layout hygiene를 검증한다; 텍스트가 겹치지 않게 하고, hot-path 작업을 보류·제외 작업과 시각적으로 분리한다.
