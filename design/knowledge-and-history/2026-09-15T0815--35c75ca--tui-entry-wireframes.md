---
created_at: 2026-09-15T08:15:40+09:00
head: 35c75ca
kind: design
status: scoped-projection-not-runtime-or-human-validation
supersedes: 2026-09-15T0751--35c75ca--tui-entry-wireframes.md
source: 2026-09-15T0815--35c75ca--consolidated-design-ssot.md#s05-scope-composition
---

# Scoped environment projection

Original material stays in nine separately addressable scope/role positions.
The actual application order is a product setting; the screen does not repeat
the designer's comprehension questions. These are fictional examples of the
[scoped composition contract](2026-09-15T0815--35c75ca--consolidated-design-ssot.md#s05-scope-composition).

```text
agent-bios / Studio                                      [메뉴]
payments · main                                          [기록]

적용 순서: 레포 → 개인 → 팀

범위      지침              지식 자료         결정 자료
레포      개발 지침 4판     재시도 2회        재시도 ADR
개인      응답 지침 2판     검토 원칙 1판     응답 방식 ADR
제품팀    팀 지침 5판       재시도 3회        공통 재시도 ADR

[자료 열기]    [적용 자료 보기]

실행      Codex CLI · 새 세션 · 단독                      [설정]
파일 변경 변경 전 확인

                                                [새 세션 시작]
Tab 이동 · Enter 선택 · Esc 뒤로
```

A source cell opens that collection's actual originals and enabled selections.
Focus changes do not select, rewrite source data or switch an existing session.
At narrow sizes, scope sections can stack with the same three role labels; the
repository/personal/Team distinctions do not collapse into one unlabeled list.

The effective-material view shows actual overlaps and retained lower sources:

```text
적용 자료

응답 언어      한국어        레포 지침
검토 방식      변경 부분     개인 지침
보고 형식      근거 요약     제품팀 지침
재시도 기준    2회           레포 지식
재시도 선택    2회           레포 결정

재시도 기준: 제품팀의 3회 기준은 이 환경에서 대체됨  [원본]
                                                   [돌아가기]
```

These sample concerns have explicit matching keys. Ordinary unkeyed prose is
still delivered as separate layers with repository-first application; a lack of
machine keys does not require a new form or revert to no precedence. The effective
view is not a new editable source, and lower decisions are not marked withdrawn.

Relevant states retain concrete wording: `레포 없음`, `팀 연결 안 함`, `자료 없음`,
`미확인`, `접근 제한`, `본문 없음` and `사용 안 함` are different. Turning off a
source excludes that source; another layer may still supply the concern. A missing
winning startup unit cannot be silently replaced and reported as satisfied.
A shadowed lower Team unit cannot block startup merely because it is marked
mandatory or its body is missing/denied.

The [interactive projection](2026-09-15T0815--35c75ca--tui-entry-prototype.html)
demonstrates scoped originals, derived selection and relevant failure states.
It does not implement production storage, publication, host delivery or Team ACLs.
Those retain their P03/P06/P11 and M1/M2/M3/P17 implementation/evidence owners.
