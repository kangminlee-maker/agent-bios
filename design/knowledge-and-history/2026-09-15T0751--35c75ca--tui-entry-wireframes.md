---
created_at: 2026-09-15T07:51:51+09:00
head: 35c75ca
kind: design
status: scoped-projection-not-implemented-or-human-validated
supersedes: 2026-09-14T2033--35c75ca--tui-entry-wireframes.md
source: 2026-09-15T0751--35c75ca--consolidated-design-ssot.md#s11-tui-entry
---

# TUI entry projection

The three comprehension questions are criteria for designers and reviewers.
The screen names product objects and actions. It does not repeat the criteria,
explain ordinary navigation, or require a ceremony of preview/confirm/start.
These fictional Korean examples project the [current SSOT](2026-09-15T0751--35c75ca--consolidated-design-ssot.md#s11-tui-entry).

## Launcher

```text
agent-bios / Studio                                   [메뉴] [잠금]

payments · main                                           [기록]
최근 기록  9/14 14:20 · 검토 메모 저장

환경                                                     [변경]
  변경 점검 · 3판 / 제품팀
  지침        변경 점검 지침 · 5판
  지식 자료   업무 확인 기준 · 7판
  결정 자료   팀·레포 기록

실행                                                     [설정]
  도구        Codex CLI
  세션        새 세션
  구성        단독
  파일 변경   변경 전 확인

                                                [새 세션 시작]
Tab 이동 · Enter 선택 · Esc 뒤로
```

The primary action checks current environment/start conditions and dispatches
without another generic confirmation screen. The action itself remains explicit.
Environment browsing or focus movement never executes it. Recent records are
scoped observations; no business goal is inferred or requested here.

## A condition that matters now

Only a relevant condition introduces additional copy and a remedy. It occupies
the affected row or action area, not a permanent teaching panel.

```text
업무 확인 기준 · 7판 — 본문 없음                   [자료 받기]
```

```text
실행 07 — 응답 미확인                              [결과 확인]
```

```text
구성  검토자 1명 추가
      검토 모델 호출이 추가됩니다.
```

Offline status retains the last-observed date. Access-denied sources keep their
protected names hidden. Unknown execution checks retain the exact request and
its original settings. Simplifying visible text does not weaken those contracts.

## Studio menu

```text
agent-bios / Studio
개인

  시작
  환경·자료
  기록
  변경 검토
  팀
  동기화·복구

Tab 이동 · Enter 선택 · Esc 뒤로
```

The menu offers product operations, not a questionnaire about the user's current
work. Detailed Team administration and installation remain in the complete design;
this projection focuses on entry and selected local interaction paths.

The [interactive projection](2026-09-15T0751--35c75ca--tui-entry-prototype.html)
uses one prototype label outside the depicted app. Product buttons and messages
use normal product language, including the simulated result states. Actual product
execution, terminal/IME behavior and human comprehension remain unverified.

N16 tests direct-start behavior, owner revalidation and targeted refusals. N26
tests real comprehension. Neither depends on the former explanatory headings,
fixed panel count or mandatory preview page. Wider screens can place environment
and execution side by side; compact text layouts retain all essential fields.
