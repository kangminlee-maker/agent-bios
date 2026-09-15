---
created_at: 2026-09-14T20:33:47+09:00
head: 35c75ca
kind: design
status: illustrative-projection-not-implemented-or-human-validated
source: 2026-09-14T2033--35c75ca--consolidated-design-ssot.md#s11-tui-entry
---

# TUI entry wireframes

This is a scoped projection of the [SSOT entry contract](2026-09-14T2033--35c75ca--consolidated-design-ssot.md#s11-tui-entry),
using fictional Korean interface examples. It does not replace the current
launcher or certify terminal rendering. Commands and entrance bindings are frozen
by P01; existing bare `agent-bios` currently displays help.

The information order is **observed location/checkpoints → environment and
start choices → next effect**. Current business intent is not known at entry. The two entrances below serve different known user intent. The compact
examples are candidates for an 80×24 terminal, including their visible action/help
lines; long/error content must use in-place detail rather than push actions out.

## A. Host launcher: work preparation is the first screen

The invoked tool and observable location can be known; the current goal and business
target are not. No goal form is shown. Selected environment and execution choices
are separate from read-only location/checkpoint evidence. This example has selected
sources but no task-specific K/M query; its next action checks startup conditions.
A new session is a selected start mode, not an inferred new-task intention.

```text
agent-bios · 환경 준비
현재 위치: payments · 로컬 레포                     [기록 자세히]
최근 기록: 9월 14일 14:20 · 검토 메모 저장
  기록된 범위만 표시 · 현재 할 일과 업무 완료 여부는 알 수 없음

선택한 업무환경: 제품팀 · 개발 환경 7판              [환경 선택]
  작업 지침       팀 개발 지침 7판 · 선택됨
  도메인 지식     결제 지식 3판 · 업무별 조회 전
  결정 기록       팀 + 레포 자료 연결 · 업무별 조회 전

실행 방법                                          [구성 변경]
  도구 / 방식     Codex CLI / 새 세션으로 시작 (선택)
  구성            단독 · 추가 검토 없음
  파일 변경       실행 도구에서 확인

다음 행동: 환경과 시작 조건 확인
  필수 초기 자료·접근 조건과 선택한 실행 설정을 확인합니다.
  구체적인 할 일과 필요한 자료는 세션 시작 후 정합니다.

[시작 조건 확인]    [다른 기능]    [나가기]
Tab 이동 · Enter 표시된 동작 · Esc 뒤로
```

Opening `환경 선택` shows available environment/source choices and the actual
selected values, with owner/edition and permitted personal/unadopted alternatives.
Moving focus previews a candidate; choosing it changes this preparation only.
Returning preserves the explicit choice and invalidates any affected old preview.
Instructions may be absent without claiming the host has no native instructions.
No independent Team hierarchy or task registration is required.

`구성 변경` keeps the supported tool/model/preset/delegation/review options. Their
effect descriptions disclose changed permission or additional model calls. It
does not use a profession label to conceal Instructions loading behavior. The
most consequential resulting choices remain visible on return; exact commands
and measurements belong in detail.

Startup checking then replaces the main body with its resolved environment
conditions, gaps, intended session mode and action. Task support stays unassessed
until the user and worker establish an actual host request. Its primary button may be `새 세션 시작`, `자료 확보 방법 보기`
or `선택 다시 확인`, according to current evidence. There is no decorative always
green “ready” badge. Existing work and current/child recipients use their exact
target/action rather than silently following this new-session example.

## B. Generic Studio: choose a job with a visible outcome

A generic entrance exposes product functions; it does not ask the user to
register or explain a business task. A short hub exposes the available functions and
explains the selected route without running it. Once a job opens, the list is
replaced by its body and a compact `다른 할 일` return route.

```text
agent-bios · Studio
살펴보는 범위: 개인                                 [범위 변경]

agent-bios에서 할 수 있는 일
> 환경 준비·시작        환경과 세션 시작 조건 확인
  환경·자료            업무환경 구성, 지식과 결정 찾기·고치기
  변경 검토            제안 내용과 내 검토 권한 확인
  팀 관리              팀 만들기·참여, 구성원·권한 관리
  동기화·복구          미전송·누락 자료와 요청 결과 확인

살펴보는 항목: 작업 준비·이어가기
  개인 또는 팀 환경과 실행 설정을 고르는 화면을 엽니다.
  기존 작업이 있다면 그 작업의 실제 전달 내역을 확인합니다.

현재 선택: 개인 범위 · 업무환경은 아직 선택하지 않음
다음 행동: 작업 준비 화면 열기

[작업 준비 열기]    [설정·도움말]    [나가기]
↑↓ 항목 살펴보기 · Enter 열기 · Esc 뒤로
```

The hub does not require environment selection before Team management or a project
before reading material. Team creation/invitation remains discoverable for a personal
user. Locale, shell connection and installation are in settings/support; they are
not alternative professional roles. A received invitation or exact material/review
link goes straight to its permitted target instead of replaying the hub.

## C. Outcome states that change the next action

These replace the relevant body/summary; they are not extra permanent panels.

| State | Visible message and next action | Meaning preserved |
| --- | --- | --- |
| First personal start | `개인 범위 · 기준 선택 안 함` → `기준 고르기` or permitted personal environment/startup preparation | No Team/account/network prerequisite; no fabricated environment |
| Existing repository, no environment | `폴더 확인됨 · 채택된 환경 정보 없음` → permitted source/basis choice | Repository existence is not adoption or recorded rationale |
| Offline with complete permitted local evidence | `로컬 환경으로 시작 가능 · 원격 변경 미확인` → local preparation | No global-latest claim or forced login |
| Missing required body | `환경의 필수 초기 자료가 이 기기에 없음` → `자료 확보 방법 보기` | Missing is distinct from empty history or a missing Team |
| Unknown request result | `이 요청의 결과 확인 필요` → `같은 요청 확인` | No new-ID replay; original target remains visible where permitted |
| Locked protected scope | `잠긴 범위 · 다시 접근하려면 잠금 해제` → explicit reentry | No private title/count; no auto-unlock |
| Changed selection after preview | `선택이 바뀌어 다시 확인이 필요함` → `준비 다시 확인` | Old result does not describe the new selection |

## D. Installation remains a separate job

The installer uses the same information order with installation-specific fields:
what is required/already present, which optional additions are selected, and what
the setup action writes or connects. Locale is readily changeable. Expand package,
source and dependency choices in-place; return to a selected-effect summary.
`설치 완료` is not `현재 작업에 적용 완료`. This projection does not invent a
Team or start a host to demonstrate setup success.

## Alternatives and evaluation

Use one-column replacement in compact terminals. A wider terminal can show choices
beside the expected effect; both must preserve target, selection and keyboard
order. The [interactive projection](2026-09-14T2033--35c75ca--tui-entry-prototype.html)
allows these design states to be explored with fictional inputs. It does not
model every detailed editor, Team lifecycle or provider implementation.

P11/N16 verifies options, focus/selection, source/state distinctions and actual
operation effects. M1/M2/M3 verify the appropriate real joined scopes. P17/N26
requires actual first-exposure comprehension and actual Korean terminal input.
An AI inspecting this mock cannot substitute for those observations. The complete
engineering owner and acceptance contracts remain in the selected development
specification, graph and catalog.
