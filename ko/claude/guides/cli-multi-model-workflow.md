---
guide_id: cli-multi-model-workflow
language: ko
status: active
use_when:
  - 여러 model 또는 CLI agent를 함께 사용
  - context reset을 넘는 handoff 또는 병렬 worktree branch
  - unattended LLM batch 또는 orchestrated subagent fleet
  - tier 배정, subagent spawn, model switch 계획
  - 중단된 pipeline resume 또는 handoff 작성
---

# CLI Multi-Model Workflow

Global Multi-Model Workflow 규칙의 scoped extension이다. 규칙은 portable role slot을 사용하며, 구체적 tool/model은 **Driving Codex CLI Directly**와 **Environment Binding**만 소유한다.

## When To Use

- 여러 model/agent, clear/new session을 넘는 handoff, unattended fleet, 병렬 worktree에 사용한다. 일반 auto-compaction은 handoff가 아니다.
- handoff 없는 single-session, single-model 작업에는 사용하지 않는다.

## Role Slots And Tiers

- FRONTIER: 최고난도 bounded design, authority-changing decision, triage, final verdict.
- HELM: standing main/judgment seat; orchestration과 bounded escalation.
- WORKHORSE: 구현량과 per-item judgment. SWEEP: 항목마다 명시적 규칙 하나를 적용하는 읽기 전용 작업이며, 모호함은 exception으로 반환한다.
- VERIFIER-A/B: 서로 다른 review kind, 가능하면 cross-family. INDEPENDENT-PR-REVIEWER: 구현자와 다른 family의 최종 review.

- 구체 model은 Environment Binding에 bind하고 **difficulty × blast radius**로 배정한다. Main은 HELM이 기본이며 first-of-kind/authority-changing main은 session boundary에서 FRONTIER를 사용한다. 사소한 작업은 직접 한다.
- 같은 배정을 subagent에도 적용한다. Loaded main을 switch하기보다 bounded FRONTIER judgment를 spawn한다. Context는 자기 model을 바꿀 수 없다.
- Architecture, interface, scope, tradeoff, user-facing decision은 main이 보유하고 volume work만 위임한다.
- 저렴한 구현 tier에는 더 강한 verification을 배정한다. 구현과 검증을 동시에 절약하지 않는다.

## When To Spawn

Main context pollution이 보통 spawn overhead보다 비싸다. 다음 gate를 순서대로 적용하고 처음 발동한 것이 결정한다.

1. **Independence:** verification/review는 자신의 대화 밖이 아니라 자신의 추론 밖으로 나간다. 자식은 양쪽 host에서 standing instructions를 지닌다 — 단 Claude 내장 `Explore`와 `Plan`은 CLAUDE.md 계층을 뺀다. 그 외에 Claude의 자식은 새 대화로 시작하지만, Codex `spawn_agent`은 기본이 fork다: `fork_turns`의 기본값이 `all`이라, 호출이 `none`이나 turn 수를 넘기지 않으면 자식이 부모의 turn 입력까지 지닌다. spawn이 사들이는 것은 seat으로 채점되지 spawn했다는 사실로 채점되지 않는다.
   spawn 여부는 아티팩트로 확인한다: Claude는 자식을 session transcript 옆 `agent-<id>.jsonl`에 쓰고, Codex는 헤더에 `parent_thread_id`·`agent_nickname`·`agent_path`·`agent_role`을 지닌 rollout을 쓴다. Codex의 `--json` 스트림으로는 spawn을 볼 수 없다 — `collab_tool_call` 객체가 spawn 유무와 무관하게 동일하다.
2. **Parallelism:** 독립 item은 per-item tracking과 함께 병렬 spawn한다.
3. **Residual context:** main이 보존할 결론보다 working log가 훨씬 큰 wide read, search, test, implementation burst를 spawn한다.
4. **Specifiability:** main의 live context나 unresolved round-trip이 필요한 deep debugging은 local에 둔다. Grind만으로 FRONTIER를 쓰지 않는다.
5. **De-minimis:** dispatch packet이 작업보다 크면 직접 한다.

- **Escalation:** material stakes(irreversible하거나 authority를 바꾸는 action을 앞두었거나, architecture나 public-interface commitment, 또는 downstream unit 2개 이상의 invalidation)와 명명된 residual-risk signal(두 번의 실패한 시도, 두 개의 지속되는 대안, 상충하는 evidence, 또는 결정을 뒤집을 수 있는 unverified assumption)이 있는 bounded judgment를 위해 먼저 FRONTIER를 spawn한다. 무엇을 바꿀 finding인지 미리 적어 두고, blind packet — evidence, constraint, rubric, neutrally ordered alternative, main의 draft 결론은 절대 포함하지 않음 — 을 보내고, 이후에 disposition(무엇이 바뀌었는지, 또는 왜 아무것도 바뀌지 않았는지; 지속적인 no-change는 gate나 packet의 결함을 가리킨다)을 기록한다. judgment가 위임 불가능할 때만 main을 switch한다.
- 모든 spawn에 bounded report, pasted context 대신 artifact path, 명시적 model/effort pin을 준다. Worker transcript를 main에 dump하지 않는다.
- 명시적 no-fan-out은 standing authorization보다 우선한다.
- gate 결정마다 한 줄을 기록한다 — `SpawnGate: <gate> <tier> spawn|inline — <why>` — 그리고 FRONTIER disposition도 함께 기록한다. launch contract의 `Delegation=off`는 spawn 의무를 해제하지만 기록 의무는 해제하지 않는다.

### Cost-Driven Down-Spawn (bounded implementation work)

이미 bounded implementation work로 분류된 단위에는 이 규칙이 위 gate 4·5를 대신한다. gate 1–3과 Escalation은 여전히 먼저이고, 명시적 no-fan-out 지시는 여전히 이긴다. 측정된 텍스트이므로 바꿔 말하지 말고 그대로 적용한다:

> This rule applies at a work-unit boundary of bounded implementation work; an explicit instruction not to fan out always wins. Spawn a WORKHORSE for the unit when it has 5 or more items and is decision-complete, has a machine-checkable done-when, and is self-contained; otherwise do it inline. An unstated count is below 5.

2026-09-08에 dependent L2 edit family에서 claude-opus-5 (xhigh) 부모와 claude-sonnet-5 WORKHORSE 자식으로 측정: 5개 항목 단위를 위임하면 규칙 자체 비용을 뺀 뒤 단위당 약 $0.05, 10개 항목 단위는 $0.14–0.18을 절감했고, 1개 항목 단위는 위임이 $0.05 더 들었으며 3개 항목 단위는 등록된 표본에서 판정되지 않았다. 검증하지 않은 크기(6–9, 10 초과)는 5와 10에서의 절감이 그 사이와 그 위에서도 성립한다는 가정에 기댄다. 위 gate들과의 순서, 이 가이드를 읽는 비용, 규칙의 발동 빈도는 측정하지 않았다. 글로벌이 아니라 가이드에 실었다(결정 D-20260908-2186cd).

## Delegation Mechanics And Teammate Persistence

Decision이 아니라 execution을 위임한다. Unit은 decision-complete, self-containedly specifiable, machine-checkable done-when, bounded blast radius를 모두 만족해야 한다. 위임된 output은 main이 accept할 때까지 staged 상태로 남는다 — worker는 external irreversible action을 취하지 않는다 — 그리고 handling(brief, verify, correct, integrate)은 작업 자체보다 분명히 subordinate해야 한다. SWEEP-bound unit은 item마다 하나의 명시적 규칙을 적용하고, ambiguity를 해결하지 않고 exception으로 반환한다.

- Unresolved choice, discovery-before-spec, 검증 불가능한 완료, unfrozen interface가 있으면 re-cut한다. Worker가 방향을 물으면 sizing failure이며 decision은 main으로 돌아온다.
- De-minimis task는 decision-complete ceiling까지 묶는다. Scout는 read-only이며 main이 이름 붙인 pending decision에 file:line evidence를 주고 kill-risk가 가장 큰 unknown부터 확인한다.
- Prompt constant, threshold, signature, judgment criterion도 코드 안의 decision이다. Decision-tainted output은 clean re-dispatch보다 review가 비싸면 폐기한다.
- Worker 비용은 request count × transcript prefix로 증가한다. 독립 read를 batch하고 edit round를 줄이며 독립 worker/message를 한 turn에 dispatch한다.
- **dispatch 전에 tier를 pin한다.** pin하지 않으면 tier가 작업을 본 뒤에 정해지고, 작업의 난이도가 아니라 크기를 따라간다. 비용 우위는 해당 작업의 근거가 있을 때에만 주장한다.
- Codex `spawn_agent`은 부모의 무엇이 얼마나 넘어갈지를 정한다: `fork_turns`의 기본값은 `all`이고 `none` 또는 turn 수를 받는다. 그 host의 `SubagentStart` hook은 `agent_type`을 받고 `continue: false`를 반환할 수 있으므로, tier 규칙을 문장이 아니라 강제로 둘 수 있다.
- 어느 host에도 spawn 단위의 instructions 억제 수단은 없다: subagent 정의는 model과 effort를 담을 뿐 scope를 담지 않는다. standing instruction 배제는 프로세스 수준의 행위이며(`claude --setting-sources ''`, 또는 `auth.json`만 든 디렉터리를 가리키는 `CODEX_HOME`), tier 정의도 함께 사라지므로 instructions 없는 reader와 pin된 tier를 한 프로세스에서 얻을 수 없다. `auth.json` 없이 비운 `CODEX_HOME`은 401로 실패하고, skill은 그래도 로드된다.
- Resident teammate는 한 burst의 dependent slice에만 쓴다. CLI가 model/context를 보존하는지 확인한다. Resume-after-completion은 둘 다 바꿀 수 있다. Burst/cache TTL 뒤 retire하고 durable knowledge는 파일에 둔다.
- Discard/direction change 뒤 routine round가 fresh slice와 비슷하게 비싸지면 respawn한다. 유일한 in-flight state는 먼저 파일로 회수한다.
- Busy worker redirect는 preempt하지 않고 queue될 수 있다. Destructive redirect 전에 artifact를 확인하고 조건부로 표현하며, 실제로 해로운 worker는 PID/worktree 단위 권한으로 중단한다.
- Idle/progress notification은 hypothesis다. 재위임 전에 repo artifact를 확인한다. 유휴 신호는 보고와 분리된 생존 신호다: subagent는 결과를 전달하지 않은 채 유휴가 될 수 있으므로, 보고 없는 유휴를 완료로 간주하지 말고 기다리는 대신 보고를 명시적으로 요청한다. 전달된 report도 marker 없이 표 중간이나 finding 중간에서 잘려서 도착할 수 있으며, inline으로 다시 요청해도 같은 방식으로 잘린다. report가 짧은 요약보다 길거나 turn을 넘겨 남아야 한다면 brief에 output file을 명시한다: worker는 전체 report를 그 파일에 쓰고 path와 한 줄 요약을 반환한다. item 중간에서 끝나는 report는 incomplete로 간주하고, inline으로 재요청하지 말고 file로 전환한다. Cross-reset state는 transcript/task board가 아니라 파일에 둔다. 동시 실행되는 async job을 poll할 때는 dispatch 시점에 받은 정확한 id/handle을 고정한다 — "latest" 편의 selector는 조용히 sibling job을 가리켜 그럴듯하지만 틀린 결과를 반환할 수 있다.
- Reviewer/subagent에는 main이 편집 중인 live tree가 아니라 read-only diff, snapshot, 또는 isolated worktree를 주고, uncommitted work가 있는 tree에서는 destructive git 작업(checkout --, reset --hard, stash, clean)을 금지한다; mid-edit 상태에서 생성된 결과를 신뢰하기 전에 tree integrity를 재확인한다.
- Review 비용은 diff에 비례하므로 layered review는 delegation 절감을 유지한다. Review kind를 없애기 전에 tier를 낮춘다.

## Driving Codex CLI Directly

Instruction/config reach는 invocation마다 정한다. AGENTS.md 규칙은 hermetic worker에 닿지 않으므로 필요한 규칙을 prompt/schema에 넣는다.

| Profile | Reach | Use |
|---|---|---|
| inherit | real `CODEX_HOME`, project cwd | global/project AGENTS.md와 user config 전체 |
| hermetic | temp home, auth only, user config 제외 | prompt-owned criteria의 independent lens |
| custom | caller-populated home | 선택한 instruction/config만 적용 |

- Instruction home, cwd, config override, task prompt, output schema를 독립적으로 제어한다. Repo wrapper가 setup/teardown을 소유한다.
- Inherit review는 discipline-aware이고 hermetic review는 independent kind다. AGENTS.md 고유 문구의 contrast로 reach를 확인한다.
- 구체 flag/version/sandbox/dispatch binding은 Environment Binding에 둔다.

## Default Frame

| Stage | Owner | Artifact / exit |
|---|---|---|
| 0 Triage | current session | difficulty/blast-radius 판단; dial 고정 |
| 1 Design | FRONTIER | measured background, done-when, concept map, allocation이 있는 dated design; owner approval |
| 2 Design verify | VERIFIER-A+B | findings union과 revision; material issue 0 |
| 3 Implement | WORKHORSE | smallest viable diff; deterministic gate green |
| 4 Implementation verify | SWEEP → WORKHORSE → FRONTIER | reviewer kind 2개 이상; strongest model은 verdict에 |
| 5 PR review | INDEPENDENT-PR-REVIEWER | clean cross-family review |
| 6 Merge verify | implementing session | freshly fetched merged state green |
| 7 Close | current session | docs/handoff sync; silently parked item 없음 |

- T1+ kickoff는 session model, orchestration authorization, 이 guide, main-as-orchestrator delegation mode를 명시한다.
- T0 mechanical/low-risk는 stage 3→4(공유 merge면 →5), T1 normal은 lightweight design을 포함한 full skeleton, T2 authority-changing/first-of-kind/release는 design/verdict review를 강화한다.
- Stage transition을 context-reset boundary에 두어 model change를 무료로 하고 design을 handoff로 겸한다. Live state가 load-bearing일 때만 loaded session을 유지한다.
- **Convergence heuristic by reviewer kind**: same-kind convergence는 신뢰도를 높이지만 blind spot을 공유한다. Different-kind divergence는 정상 신호이므로 union에 대응한다.
- Verification이 issue boundary를 넓히면 design으로 돌아가 re-triage한다. 같은 loopback 두 번째에는 owner 선택을 받는다. Halt는 valid artifact에서 resume하고 per-item outcome을 보존한다.

## Model Switching And The Prompt Cache

- Prompt cache는 model별이다. Mid-session switch마다 loaded transcript를 한 번 재처리하므로 model별로 batch하고 reset boundary에서 switch한다.
- 먼저 FRONTIER decision을 spawn한다. Context fidelity가 handoff 비용보다 중요하고 judgment가 위임 불가능할 때만 main을 switch한다.
- 계획되지 않은 반복 alternation을 피한다. Budget한 escalate/return과 명시적 A/B 비교는 허용한다.
- Fork는 양쪽 host에서 대화 내용을 보존하지만 prompt cache는 한쪽에서만 보존한다. Claude `--fork-session`은 같은 model이면 거의 전부를 재사용하고 model을 바꾸면 잃는다; Codex `exec fork`는 어느 model이든 다시 보낸다. 즉 "fork할 때 model을 바꾸지 마라"는 Claude의 규칙이고, Codex에서 fork는 새 dispatch와 같은 값이다.

## Cross-Verification Economy

- Cross-verification이 필요하면 kind diversity를 유지하고 effort부터 낮춘다. Kind를 잃으면 error class를 잃는다.
- LLM review 전에 deterministic gate를 실행한다. SWEEP finder → WORKHORSE judgment → FRONTIER triage/verdict funnel을 쓴다.
- Family collapse는 기록하고 diversity 회복 전 clean verdict를 PROPOSED로 둔다.
- Silent/dead lens는 incomplete이지 clean이 아니다. Usage/error/report evidence로 liveness를 확인하고 rerun, provider swap, 또는 PROPOSED를 기록한다.
- Kind label이 서로 다른 backend를 보장하지 않는다: wrapper와 rate-limit fallback은 두 "different-kind" verifier를 조용히 같은 model/provider로 라우팅할 수 있다. 고위험 verdict에서 diversity를 신뢰하기 전에 각 verifier의 실제 backing model을 live process나 usage evidence로 확인한다; collapse 시 그 쌍을 하나의 kind로 취급하고 PROPOSED로 표기한다. 무엇이 돌았는지 기록하는 runner에도 같은 읽기가 필요하다: identity는 runner 쪽 literal이 아니라 실행 시점의 target에서 취하고, 요청된 것과 같은지 assert한다 — fallback seat은 존재 확인을 통과한다.
- **Evidence access는 그 자체로 별개의 축이다.** 모든 reviewer가 blind packet만 봤다면, provider를 넘은 수렴이라도 그것은 packet의 프레이밍에 대한 evidence이며 그 packet이 빠뜨린 것까지 포함한다. code seat, 측정된 사실, 또는 constraint 목록에 기대는 수렴된 verdict를 채택하기 전에, 그 사실들을 반증할 수 있도록 live read 접근을 가진 seat 하나를 태운다: 실제 constraint를 인용한 단 하나의 반대가 blind majority를 이긴다. 그리고 빠져 있던 사실은 packet으로 돌아간다. 이것은 independence 등급의 한 칸이 아니라 그 옆에 나란히 놓인 별개의 축이다.

## Dual-Provider Design Drafts

- Trigger: 작업이 설계이고(코드를 쓰기 전의 high-level shape과 구현 프로세스) 두 개 이상의 provider가 frontier tier로 접근 가능하다. OAuth 세션을 통한 접근은 구독 커버라 한계 지출이 없어 승인도 질문도 필요 없다: 메인 컨텍스트 외의 OAuth frontier provider가 존재하면 곧바로 dual-provider 설계를 진행한다. 승인 게이트는 오직 metered API key로만 도달하는 provider에만 적용된다: 거기에 dispatch하려면 그 지출에 대한 사용자의 명시적 건별 승인이 필요하다(건별이며 상시 아님 — 과거 승인은 다음 설계로 이월되지 않는다). 두 번째 provider에 도달하는 유일한 방법이 승인되지 않은 metered API 지출뿐이라면, 설계를 막지 말고 single-provider로 진행한다.
- Mechanics: blind packet 하나를 구성해(evidence, constraint, rubric, 중립적 대안 — escalation-gate packet 형태) provider별 frontier-tier model 하나에 변경 없이 dispatch한다; 초안은 독립을 유지한다 — 서로의 출력을 보지 않는다. 그 다음 판정한다: 두 dual-provider frontier design drafts를 rubric에 대조해 비교하고, 우승안을 뼈대로 삼고 패자의 더 나은 부분을 접붙이고, 무엇이 달랐고 종합이 왜 그렇게 선택했는지 기록한다(FRONTIER disposition line).
- Packet injection: dispatch된 designer는 hermetic하다 — 자기 packet만 읽고 이 instructions를 로드하지 않는다. instructions가 공급했을 설계 원칙을 주입한다: concept economy(reuse/extend/rename/split, compact concept graph), LLM/tools-code capability boundary, staged 설계 규칙(smallest viable path, falsifiable done-when), 그리고 설계가 건드리는 도메인별 원칙. 원칙 없이 만들어진 초안은 원칙과 함께 만들어진 초안과 비교 가능하지 않다.

## Unattended Batch Safety

- Parent가 per-item completion과 **code-level circuit breaker**를 소유한다. 통제하지 않는 dispatcher는 동등한 보호를 확인하거나 attended로 실행한다.
- 기본 breaker는 bounded backoff 뒤 서로 다른 item에서 provider limit/auth/transport failure가 연속 3회면 halt한다. Undone item을 저장하고 알리거나 provider를 바꾼다.
- Item-specific failure는 poison item이다. 2–3회로 제한한 뒤 complete-with-failure dead-letter로 보낸다. Unfinished/invalid item만 resume하며 whole-batch rerun은 cheap idempotence가 필요하다.
- enumeration run은 수집된 개수를 같은 filter에 대해 source가 스스로 보고한 총계와 대조해 assert했을 때만 done이다. retriable failure는 열거된 code 목록이 아니라 class로 — 즉 server-side transient 전부로 — 분류한다. 빠뜨린 code 하나가 item을 조용히 떨어뜨리기 때문이다; 어떤 batch가 실패했는지 저장하고 완료를 선언하기 전에 reconcile한다; 그리고 불일치나 범위가 다른 population에서 나온 총계는 각주가 아니라 결함으로 다룬다. 선언된 partial이나 sampled scope는 여기서 제외다.
- Per-item outcome/token/cost를 recalibration용 artifact로 저장한다.
- metered batch를 첫 item 너머로 풀어놓기 전에, 그 item으로 item logic이 아니라 batch 기계장치를 probe한다: real runner를 통해 side effect까지 end to end로 돌린 뒤, 이후 분석이 의존하는 모든 값 — treatment knob, run identity, 비용 — 이 예상한 channel을 통해 저장된 record에 도달했는지 확인한다. 첫 실패들에서는 runner의 status classifier가 아니라 raw run log를 읽는다 — classifier는 출력이 없다는 데서 원인을 추정한다. cheap idempotent batch에는 이 gate가 필요 없다.

## Halt And Resume

- Parse/schema를 통과하고 기록된 source/config/HEAD fingerprint와 맞는 artifact에서 resume한다. 검증 불가능하면 invalid다.
- cache-hit이나 fingerprint predicate은 artifact의 내용을 결정하는 모든 값을 덮어야 한다 — upstream input의 content identity, cap, template, model id, config — 존재 여부나 mtime, 크기만으로는 안 된다; 출력을 결정하는 값을 새로 추가할 때는 같은 변경 안에서 key의 pre-image를 검사하고 그 값이 움직이면 key도 움직인다는 것을 assert한다. upstream input이 바뀌어 다시 돌리기 전에, predicate이 그 input의 identity를 빠뜨린 intermediate는 무효화한다: 존재로 keying된 cache 위에서의 regenerate는 옛 input에서 다시 도출한다.
- Invalid unit 하나만 resubmit한다. 다수 unit의 correlated failure는 structural defect이므로 halt한다.
- Halt→continue를 정상 operation으로 설계한다.
- Tool이 관리하는 temp/cache 출력 위치는 ephemeral로 취급한다 — tool 자체 일정으로 garbage-collect된다. Pending되거나 handoff된 결정이 의존하는 artifact는 나중에 의존하기 전에 project-owned durable path로 복사한다.
- Bounded-size cross-session index(memory index file)는 read limit을 넘으면 조용히 truncate된다. 주기적으로 크기를 limit과 비교하고, compact하기 전에 index-only detail을 per-item file로 이관한 뒤 link와 orphan 없음을 검증한다.

## Sessions, Branches, Worktrees

- Session은 시작 directory에 bind된다. CLI native relocation/resume을 사용하고 transcript file을 복사하지 않는다.
- 새 worktree에는 native relocate하거나 handoff 후 fresh session을 연다. Branch를 serial하게 integrate하고 merge마다 다시 검증한다.
- 충돌 없는 merge와 green build는 배치가 아니라 텍스트에 대한 evidence다. base 쪽이 주변 코드를 재구조화했다면 — 섹션 재편, module 분할, variant마다의 새 container — merge된 추가분을 새 구조 안에서 하나씩 찾아 그 scope가 여전히 담긴 container의 scope와 맞는지 확인한다: 전역 설정이 variant 전용 container 안에 들어가서는 안 되고, 중복이나 orphan 사본이 남아서도 안 된다. layout이 그대로인 곳으로의 merge는 평소의 green-state 확인이면 충분하다.
- Superseded worktree/handoff를 dead로 표시해 미래 resume가 고르지 못하게 한다.
- Resume/clear/relocation 뒤 pwd, branch, HEAD를 pinned handoff와 대조한다.
- 병렬 session의 동작(commit, branch, resource)은 그 session 자신의 transcript에 있는 execution evidence로 귀속시키고, token 언급으로는 절대 귀속시키지 않는다 — 공유된 handoff/memory 파일은 모든 session의 context에 같은 token을 주입한다.

## Context Budget And Reset

Context 증가는 host가 아니라 작업의 성질이다: 양쪽 CLI에서 request 50개 이상인 session
1,075개를 측정한 결과 request당 ~2,400 token(IQR 1,850-2,950)이고 두 host 차이는 7% 이내다
(Claude 2,280, Codex 2,450); 가장 긴 session(request 400개 이상)은 ~1,800으로 낮다. 따라서
budget은 하나로 충분하며, host마다 다른 것은 그것을 무시했을 때 치르는 대가다. 이 수치는
prior이고, 진행 중인 session의 실측은 아래에서 다룬다.

- **Automatic compaction은 window가 거의 찬 뒤에야 발동한다** — Claude는 84-87%(window는
  200K과 1M 두 무리), Codex는 transcript가 `model_context_window`로 기록한 window의 ~95%(측정한
  세션은 258,400, 이후 Codex/모델 조합은 353,400을 기록 — 값을 읽지, 가정하지 않는다). Cache read는
  request마다 loaded context 전체에
  대해 과금되므로, reset을 host에 맡기면 그 이전 모든 request에서 최대치를 지불한다. 측정값:
  input이 session cost의 92-94%, output이 6-8%, cache hit 95-97% — context가 곧 비용이고
  uncached input은 0.0%다.
- 대신 의도적으로 reset한다. Request당 비용은 867K auto-compact 지점에서 200K로 내리면 ~4배
  줄어든다. 비용 이론상 최적은 ~65K이지만 request 32개마다 2-3분짜리 compaction을 사므로,
  실용 구간은 150-250K이고 그 아래 꼬리는 쫓을 가치가 없다.
- **Budget을 제약하는 것은 token 수가 아니라 reset에서 살아남는 것이다.** Compaction은 ~14K
  요약과 최근 message 3-4개만 남기고 나머지를 버리며, 스스로 발동할 때는 지시도 없다. 파일에
  쓴 것은 모든 reset을 견디므로, 가장 이른 안전한 임계는 durable state가 이미 disk에 있는
  지점이다. 이것이 비용과 손실을 분리한다 — 그렇지 않으면 자주 reset할수록 그만큼 더 잃는다.
- Context가 얼마나 커졌는지가 아니라 무엇을 아는지로 방식을 고른다:

| 상황 | 방식 |
|---|---|
| Stage가 끝났고 남길 것을 안다 | clear + dated handoff file — 가장 싸고, 손실이 손실이 아니다 |
| Stage 중간이고 남길 것을 안다 | handoff를 먼저 쓰고 명시적 지시와 함께 compact |
| Stage 중간이고 필요한 detail을 아직 특정할 수 없다 | 지시와 함께 compact; 요약은 파일이 아직 이름 붙일 수 없는 범위를 덮는다 |
| 원본 detail이 나중에 필요할 것 같다 | clear하되 transcript 경로를 handoff에 남긴다 — transcript는 disk에 남는다 |
| 다음 질문이 무엇일지 모른다 | 새 session + messaging; 왕복이 가능한 유일한 방식 |
| 증가의 원인이 tool output이다 | 애초에 subagent로 offload — 측정상 ~20배 저렴(tier ~5배, context 격리 ~4배) |
| 판단 이력 자체가 load-bearing이다 | session을 유지하고 2-5배 resume 비용을 지불한다 |

- 추정하지 말고 측정한다: `agent-bios cost --context <transcript>`(`session-cost.py`의 설치된 진입점)는 양쪽 host의 transcript를
  읽어 현재 context, 증가율, compaction 횟수, budget까지 남은 request 수를 보고한다. Codex는
  `model_context_window`를 직접 기록하지만 Claude는 기록하지 않으므로, 도구는 window를 가정하는
  대신 관측된 auto-compaction 지점을 보고한다.

## Handoff Contract

Narrative가 아니라 다음 agent와 re-verification을 위해 쓴다. 필수 내용:

1. One-line current state.
2. Pinned worktree, branch, HEAD, upstream/merge-base, author tier, active fallback/family collapse.
3. Cited command나 anchored file evidence만으로 재확립 가능한 CONFIRMED claim. 코드 인용은 나중 편집에서 조용히 어긋나는 bare line number가 아니라 안정적인 symbol 이름(grep으로 재도출 가능)으로 anchor한다.
4. 이번 session에서 재검증하지 않은 inherited claim을 포함한 별도 PROPOSED/OPEN.
5. Ordered next action과 literal first command: T1+이면 model, orchestration authorization, guide load.
6. Credential은 env-var/gitignored slot으로만 가리키고 excerpt/command에서 secret을 제거.

- 이 기록 자체를 담을 commit의 hash는 절대 기록하지 않는다 — 구조적으로 불안정하다. substantive 변경을 먼저 반영하고 후속 commit에서 확정된 hash를 참조하거나, 상대적 표현("이 handoff를 담은 commit에서 resume")을 쓴다.
- Broken evidence anchor는 CONFIRMED를 PROPOSED로 내린다. Pinned state가 틀리거나 신뢰할 handoff가 없으면 source artifact에서 재구축하고 fresh handoff를 쓴 뒤 행동한다.
- Handoff는 working repo의 isolated dated docs에 두고 이 instruction-SSOT repo에는 두지 않는다. Resume 때 load-bearing claim을 재검증한다.

## Environment Binding (환경마다 이 섹션만 수정)

Concrete model/tool의 human-readable projection은 이 표가, machine launch authority는 `launch/agent-launch.toml`이 소유하며 parity check가 둘을 정렬한다. Binding이 약 8주보다 오래됐거나 observable model/tool surface가 바뀌면 재확인한다. 배포 기본값은 원본 repo에서 편집하고, 개인 launch binding은 사용자 소유 launcher 설정에 둔다. Private 설치는 immutable release를 저장하고 개인 상태를 보존한다. 새 configured session에서 binding을 선택하며 기존 session pin은 유지한다.

Binding (2026-09-08):

| Slot | Binding | Notes |
|---|---|---|
| FRONTIER | Claude Fable 5.1 · GPT-6 Astra (read-only; max default, task-fit effort including Ultra) | bounded hardest decision/verdict |
| HELM | Claude Opus 5 (xhigh) · GPT-5.6 Sol (xhigh main; main Ultra는 명시 선택 필요; bounded FRONTIER Ultra allowed) | standing main; Codex 기본 bypass, explicit sandbox로 축소 |
| WORKHORSE | Claude Sonnet 5 (xhigh) · GPT-5.6 Terra (xhigh) | implementation/per-item judgment |
| SWEEP | Claude Haiku 4.5 (effort 생략) · GPT-5.6 Luna (max) | 읽기 전용; 항목마다 명시적 규칙 하나 적용; 리바인드 후보 아님 |
| VERIFIER-A | plain `codex exec` deep pass — GPT-5.6 Sol, ultra effort, packet은 stdin(`-c service_tier="fast"`는 명시적 fast opt-in) | 가장 강한 single reader; Claude main에서 cross-family |
| VERIFIER-B | Claude Code ultracode workflow (keyword로 열리는 many-agent) | code/execution kind; fan-out 대응물 |
| INDEPENDENT-PR-REVIEWER | Codex CLI | adversarial `gh pr diff` review |
| Claude relocation | EnterWorktree, `/cd`, `--worktree`; resume는 directory-scoped | verified 2.1.207 |
| Codex relocation | `codex resume` (cwd-filtered; `--all` lifts), fork | verified 0.144.1 |
| Claude teammate | named mailbox continuation; completed-agent message는 main model로 cold rerun 가능 | resident 유지; completed resume 회피 |
| Rate-limit fallback | OpenAI 제한 → VERIFIER-B(Anthropic workflow); Claude 제한 → VERIFIER-A(Codex exec) | family collapse 기록 |

Codex direct-drive(0.144.1, 2026-07-12 확인):

- `codex-helm`은 HELM main을 기본 `--dangerously-bypass-approvals-and-sandbox`로 시작하며 explicit `--sandbox`는 flag 순서와 무관하게 우선한다. Non-Ultra는 native multi-agent 기본 off, explicit main Ultra는 기본 on이다.
- HELM에게 내부 `codex-run`으로 tier를 dispatch하도록 지시하고 adapter가 model/effort/sandbox를 pin한다. FRONTIER는 별도 `gpt-6-astra`, read-only root이며 기본 max, 분할 가능 작업은 Ultra, 비용/latency 우선이면 낮은 effort다. Nested multi-agent는 Ultra에서만 켠다. Native `codex exec` spawn은 role/effort를 pin하지 못한다.
- 이는 security boundary가 아니라 instruction-backed, live-E2E-verified default다. Main bypass와 임의 expert `-c`는 의도적으로 남는다. `frontier.toml`은 direct native FRONTIER의 기본 effort를 max로 고정하고, launcher projection은 선택한 tier 값으로 덮어쓴다.
- `codex-run`은 reach, stdin, schema, profile, expert `-c`, channel, exit status를 소유하는 internal adapter다.
- `claude-run`은 그 Claude 쪽 쌍이며, composable review 계약이 그 host의 panel dispatch에 지목하는 명령이다. 형태가 같다: prompt는 stdin, 최종 메시지는 stdout, exit status 그대로, `--model`/`--effort`로 seat을 pin하고, 인식하지 못하는 인자는 전부 `claude`로 forward한다. 기본으로 mutating tool을 거부하지만 이는 `codex-run`이 받는 OS 수준 sandbox가 아니다 — 두 기본값을 동등한 보장으로 읽지 않는다. 맨 CLI가 아니라 **계약이 지목한 명령**을 dispatch한다: dispatch가 실제로 무엇을 했는지 보고할 수 있는 것은 adapter뿐이고, receipt 없는 review는 PROPOSED로 남는다.

Dispatch packet:

| Target | Required packet / default |
|---|---|
| GPT-6 Astra FRONTIER | outcome, evidence, decision boundary, stop/verification; max default; read-only |
| GPT-5.6 Terra WORKHORSE | outcome, frozen scope/input, authority, done-when, evidence/report, escalation; xhigh |
| GPT-5.6 Luna SWEEP | exact search space, 항목마다 규칙 하나, ambiguity behavior, stop, output; max; 읽기 전용; architecture/debugging 제외 |
| Claude Opus 5 HELM | agentic work xhigh; sensitive judgment high 이상; bounded/cost-led일 때만 낮춤 |
| Claude Sonnet 5 WORKHORSE | exact scope, apply-to-all rule, tool, verification, report; xhigh 기본 |
| Claude Haiku 4.5 SWEEP | 항목마다 명시적 규칙 하나를 적용하는 읽기 전용 작업; effort 파라미터 생략; 모호함은 exception으로 반환 |

Task-relevant tool만 노출하고 독립 call을 병렬화한다. Worker report: `status`, `files_or_items_touched`, `evidence`, `verification`, `risks_or_escalations`. 공식 근거: OpenAI [model](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6), [migration](https://developers.openai.com/api/docs/guides/upgrading-to-gpt-5p6-sol), [prompting](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6), [Codex models](https://learn.chatgpt.com/docs/models); Anthropic [subagents](https://code.claude.com/docs/en/sub-agents), [model effort](https://code.claude.com/docs/en/model-config).

## Evidence Base

Numeric default의 single owner다. 각 관측에 날짜와 작업 범위를 명시하고, recalibration 시 이 표와 연결된 inline threshold를 함께 갱신한다.

| Evidence | Result / supported rule |
|---|---|
| Claude M=40 확인 실험(2026-09-06), 오너 정정으로 반영(2026-09-08) | Opus 5/xhigh 부모 아래 Sonnet 5/xhigh 자식: 새 paired block 5개에서 KEEP 확정. 동등 수준 도달까지의 모델링 비용 45.5% 절감, 하한 40.4%. 이 작업군의 비용 근거이며 일반 품질·청구액 보장은 아니다. |
| 오너 티어 정정(2026-09-08), Codex discovery 셀 미완료 | Terra/xhigh는 측정된 실험 effort를 오너 지시로 채택한 값이며 Codex KEEP 확정 판정은 아니다. 두 HELM 부모 좌석은 유지한다. SWEEP은 리바인드 후보가 아니며 항목별 규칙 하나를 적용하는 읽기 전용 작업으로 한정한다. |
| 15 sessions, 3,758 requests, 10 switches | switch가 uncached input의 13.9%; unplanned switch 회피 |
| 285-call limit incident | first limit 뒤 208 dispatch, 34/35 item loss; breaker 3 |
| 99 staged reviews | 15.2%가 대부분 compute 뒤 halt; resume-first |
| three-task delegation probe | batched worker 5 request/$0.23 vs loaded FRONTIER direct 6/$3.35; cache TTL 5분; completed resume 2–5× |
| two live delegation sessions | tiering 약 3.3× 절감; discarded prefix는 respawn보다 비싸짐; unpinned reviewer가 FRONTIER 상속 |
| Codex reach contrast | inherit 약 16.5K vs hermetic 약 8.7K token; schema와 stdout/stderr contract 확인 |
| Codex native-spawn probe + HELM E2E | native max/Ultra child가 xhigh/role null 기록; 별도 read-only root는 max와 Ultra 기록 성공 |
| 양쪽 host, request 50개 이상 session 1,075개 (2026-08-16; 이전의 크기 상위 62개 표본은 ~1,800-2,000) | context는 request당 ~2,400 token 증가(IQR 1,850-2,950), host 차이 7% 이내, request 400개 이상 session은 ~1,800; auto-compaction은 window의 84-95%에서 발동하며 그보다 이르지 않다 |
| Cost 요소별로 분해한 session 2개 (2026-08) | input이 비용의 92-94%, output 6-8%, cache hit 95-97%, uncached input 0.0%; 867K→200K budget은 request당 비용을 ~4배 줄인다 |
| Independence gate를 발동시키도록 만든 상황 3개 + positive control, dispatch 4회 (2026-09-01) | 3개 중 spawn 0회, control 1회; de-minimis가 셋 모두를 흡수했고 inline 답은 모두 정확 — 항상 발동한다고 쓴 spawn 의무가 발동하지 않았다 |
| 60/150 파일 mechanical scan, load-bearing cell은 N=5 (2026-09-02) | inline $0.627→$0.919; tier를 pin한 위임 $0.665→$0.921; pin하지 않으면 +57-73%; 같은 cell의 N=2 최초 판독은 19%·36% 절감을 보고했고 N=5가 둘 다 지웠다 |
| 양쪽 host의 fork cache 재사용 (2026-09-02) | Claude 같은 model 98.9%, 다른 model 0-26%; Codex는 어느 model이든 14-18% (Codex cell은 각 N=1) — fork 지침은 host 한정 |
