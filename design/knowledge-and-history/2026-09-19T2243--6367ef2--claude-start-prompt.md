---
created_at: 2026-09-19T22:43:44+09:00
head: 6367ef2
kind: handoff
status: user-paste-start-prompt
---

# Claude Code 시작 프롬프트

저장소 `/Users/kangmin/Documents/agent-bios-personal`에서 Claude Code를 시작하고,
아래 내용을 새 대화에 붙여 넣는다. handoff 본문과 연결된 파일을 읽는 방식이며,
Codex의 세션 ID를 Claude의 재개 ID로 사용하는 방식이 아니다.

```text
agent-bios의 Team 업무환경 확장 작업을 이어서 진행해줘.

우선 이 handoff를 읽어줘:
@design/knowledge-and-history/2026-09-19T2243--6367ef2--claude-handoff.md

루트 AGENTS.md와 CURRENT.md, handoff의 읽기 순서에 따라 최신 SSOT를 읽고, 개발스펙의 P01 관련 계약·실행계획의 P01 노드와 의존관계·해당 테스트 프로필·실제 P00 증거를 확인해줘. 큰 JSON 전체는 검사 도구로 확인하고 필요한 항목을 추출해 읽어줘. 중요한 사용자 결정과 실패에서 얻은 교훈은 handoff에 있고, 전체 이력과 원문 위치는 handoff-context.json 및 로컬 context archive에 있어. 처음부터 모든 과거 문서를 넣지 말고 현재 규칙을 먼저 읽은 다음 필요한 근거를 찾아줘.

이어서 작업하기 전에 현재 목적, 확정된 사용자 제약, 구현된 것과 미구현인 것, accepted/ready 상태, 현재 작업 트리와 P00 기준선의 차이, 다음 작업을 짧게 설명해줘. 문서가 이미 답하는 내용을 다시 질문하지 말고, 실제 증거가 일치하면 P01 계약·사례 연결 확정부터 진행해줘. R0는 P01 뒤이며 무인 실행을 할 때만 필요해.

기존 설계를 처음부터 다시 만들지 말고, 충돌하면 최신 사용자 결정과 SSOT를 기준으로 원인을 찾아줘. 호환 계층은 요구하지 않지만 기존 작업·선택된 데이터는 보존해줘. 다른 작업의 output/와 research/fde-ui/, 공유 index를 건드리지 말아줘. 새 기능이나 실제 호스트 검증을 문서·목업만으로 완료했다고 처리하지 말아줘. 변경과 검증 결과, 미해결 사항을 다음 작업자가 다시 이어갈 수 있게 남겨줘.
```
