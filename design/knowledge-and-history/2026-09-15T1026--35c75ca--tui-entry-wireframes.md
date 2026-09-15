---
created_at: 2026-09-15T10:26:27+09:00
head: 35c75ca
kind: design
status: scoped-projection-not-runtime-or-human-validation
supersedes: 2026-09-15T0851--35c75ca--tui-entry-wireframes.md
source: 2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s06-consumer-interaction
---

# Management source-inspection projection

The host launcher enters preparation directly. Generic Studio enters its existing
management hub. Neither route asks the user to arbitrate Decision memory. The nine
source positions remain independently inspectable and selectable for the next
environment; selecting a memory source makes its records available to lookup, not
an application decision. Instructions and knowledge retain repo → personal → team
precedence. Memory records have no automatic scope winner.

```text
agent-bios / Studio                                      메뉴  잠금

payments                                                   기록
로컬 레포 · main
9/14 14:20 · 검토 메모

환경·자료                                  자료 구성 보기
지침·지식: 레포 → 개인 → 팀 · 제품팀
범위   지침              지식 자료           결정 자료
레포   [x] 응답 지침     [x] 재시도 기준     [x] 재시도 결정
       4판               7판                3판
개인   [x] 개인 지침     [x] 검토 원칙       [x] 검토 기록
       2판               1판                1판
팀     [x] 팀 지침       [x] 팀 업무 기준    [x] 팀 결정 기록
       5판               6판                2판

실행                                                       설정
도구       Codex CLI · 새 세션
구성       단독
파일 변경  변경 전 확인

                                                 [새 세션 시작]
Tab 이동 · Enter 열기 · Space 선택 · Esc 뒤로
```

Opening a source reads its permitted original content and revision. Disabling a
source changes this preparation only; it does not edit an original or create user
consent. Lower-ranked I/K originals remain inspectable, subject to their own
metadata/body rights. Their unrelated units still accumulate. Missing required
selected instructions, locked state, and an unknown earlier start result retain
their distinct handling. A memory conflict alone does not block startup.

```text
agent-bios / Studio                                      메뉴  잠금

자료 구성
지침·지식: 레포 → 개인 → 팀

결정 기록
재시도 선택 · 일반 요청
서로 다른 결정 기록

레포 · 재시도 결정 3판       2회       조회 대상
팀 · 팀 결정 기록 2판       3회       조회 대상

돌아가기
```

Both source names open their originals. The source detail shows recorded content
and reason where body access permits it. There is no `참고하기`, application button,
keep/ask choice, direct-decision entry, or simulated memory-use result in this
management view. The comparison uses an explicit example key; it does not infer
equivalence from titles or prose.

The [interactive projection](2026-09-15T1026--35c75ca--tui-entry-prototype.html)
covers preparation and source inspection. Its outer label identifies fictional
data and no real execution. Tweak controls select the entry route, source scenario,
and layout only. Start-result views are launcher placeholders and preserve lookup
references; they do not claim a memory application or a user's answer.

The actual working CLI/app asks at the point where it needs to apply conflicting
decisions. That interaction belongs to P10's host adapter and shared consumption
contract, separately specified in the
[SSOT](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s06-consumer-interaction)
and development specification. Removing its simulation here does not remove the
user's choice, direct decision, keep/ask policy, related-change invalidation, or
immutable receipt requirements. This browser projection supplies no evidence of
real host question delivery, terminal/IME behavior, durable storage, or human
comprehension.

The [17-case DOM-stub check](2026-09-15T1026--35c75ca--tui-entry-check.cjs)
and [dated evidence](2026-09-15T1026--35c75ca--tui-entry-evidence.json) verify this
fictional management projection only; they do not qualify real consumption.
