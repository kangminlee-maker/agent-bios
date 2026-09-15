---
created_at: 2026-09-15T08:51:50+09:00
head: 35c75ca
kind: design
status: scoped-projection-not-runtime-or-human-validation
supersedes: 2026-09-15T0815--35c75ca--tui-entry-wireframes.md
source: 2026-09-15T0851--35c75ca--consolidated-design-ssot.md#s05-decision-arbitration
---

# Decision-use arbitration projection

The nine source positions remain. Instructions/knowledge retain repository-first
application. An actual use of conflicting decisions opens the bounded choice below;
ordinary startup and source inspection do not require this question.

```text
재시도 선택 · 일반 요청
payments · 제품팀

어느 결정을 참고할까요?
○ 레포 · 재시도 결정 3판       2회
  이유: 빠른 오류 보고
○ 팀 · 팀 결정 기록 2판        3회
  이유: 일시적 오류에 재시도 기회 제공
○ 직접 결정

다음에 참고할 때
○ 관련 결정 변경 전까지 유지
○ 사용할 때마다 묻기

[돌아가기]                                         [적용]
```

No source/mode is initially selected as consent. A direct resolution requires its
own nonempty text. The button admits this user's application only; it does not
publish or revise an original ADR. Missing choice/cancel leaves this use pending.

With keep-mode and an unchanged comparison basis, a new use returns the recorded
application. With ask-mode, a new use asks for the application again while retaining
the already selected ask policy; it does not require choosing the policy repeatedly.
The same pending logical use returns to its existing question/answer after navigation
or retry. A changed basis creates a new question version under that use.

```text
재시도 선택 · 일반 요청
관련 결정이 바뀌었습니다.

○ 레포 · 재시도 결정 3판       2회
○ 팀 · 팀 결정 기록 3판        4회
○ 직접 결정

다음에 참고할 때
○ 관련 결정 변경 전까지 유지
○ 사용할 때마다 묻기

[돌아가기]                                         [적용]
```

An unchosen participant's change also invalidates both the stored application and
mode. A later return to old bytes does not revive invalidated consent. Unrelated
records and presentation settings do not force requestions. A past resolved-use
view remains a historical snapshot, with a later-change indication where relevant;
the next use evaluates the current basis independently.

The [interactive projection](2026-09-15T0851--35c75ca--tui-entry-prototype.html)
provides a conflict's `참고하기` / `다시 참고하기` paths, keep/ask/custom choices and
external fictional source-update controls. Its prototype label stays outside the
depicted product. The update controls demonstrate related Team changes, reversion
and an unrelated personal-record update; they are not source-authoring actions.

Actual source change/coverage evidence, private durable preference storage, host
question delivery and genuine user answers remain the implementation/evidence
requirements in the [SSOT](2026-09-15T0851--35c75ca--consolidated-design-ssot.md#s05-decision-arbitration)
and selected development specification. This browser projection is not an IME,
terminal, persistence or human-comprehension qualification.
