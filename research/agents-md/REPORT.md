# 권위 있는 AGENTS.md / CLAUDE.md 12,749개의 목적 분류

2026-07-26 · 데이터·스크립트: `research/agents-md/`

---

## 1. 무엇을 모았나

**자격 기준**: repo star ≥ 1,000 **또는** 소유자 follower ≥ 1,000 (fork·archived 제외, 2025-01-01 이후 push).

GitHub 웹 검색(`path:AGENTS.md`)은 API로 재현되지 않는다. REST 코드검색의 `path:`는 구 인덱스의 디렉터리 의미이고(실측 131건), 실제 모집단은 `filename:AGENTS.md` = 168,768건인데 **쿼리당 1,000건 상한 + 분당 10요청**이라 열거가 불가능하다. 그래서 방향을 뒤집어 **자격 조건을 먼저 전수 열거한 뒤 파일 존재를 확인**했다. 이 방식은 기준을 정의상 100% 커버한다.

| 단계 | 규모 | 완전성 검증 |
|---|---|---|
| follower ≥ 1K 유저 | **8,364** | API 총계와 정확히 일치 |
| star ≥ 1K repo | **38,851** | API 총계·버킷 합계 모두 38,851 |
| 유저 소유 최근 repo | 84,577 (6,983명) | 유실 배치 1건을 보정 패스로 회수 |
| 파일 판정 대상 | **123,428 repo** | **실패 배치 0 / 6,172** |
| 파일 보유 repo | 11,694 | star 경로 14.4%, follower 경로 7.0% |
| **최종 코퍼스** | **12,749 파일 / 11,374 repo** | |

경로 8종을 모두 조회한 결과 **514개(4%)가 루트가 아닌 위치**(`.claude/CLAUDE.md` 208, `docs/AGENTS.md` 129, `agents.md` 79, …)에서 나왔다. `AGENTS.md`/`CLAUDE.md`만 봤다면 통째로 놓쳤을 분량이다.

**stub 배제**: `vercel/next.js`의 `CLAUDE.md`는 9바이트(`AGENTS.md`라는 문자열 포인터)다. 존재 여부만 세면 CLAUDE.md 채택률이 크게 부풀려지므로 200바이트 미만은 제외했다.

### 코퍼스 크기 분포

| p25 | 중앙값 | p75 | p95 | 최대 |
|---|---|---|---|---|
| 2,192 B | **4,474 B** | 8,571 B | 22,759 B | 288,888 B |

파일의 **8.7%(1,112개)는 다른 파일과 완전히 동일한 복붙**이다. 섹션 단위로는 21,284개가 중복 클러스터에 속한다. 빈도를 그대로 세면 템플릿 확산이 "관행"으로 둔갑하므로, 표본에서는 중복 클러스터당 최다 star 파일 1개만 남겼다.

---

## 2. 어떻게 분류했나

**분석 단위** = 헤딩 섹션 하나 (헤딩이 없거나 3,000자를 넘으면 빈 줄 기준 ~1,500자로 분할). 총 172,279 단위.

1. **개방코딩** — 서로 격리된 분석가 3명이 **동일한 45파일**(18개 층 비례배분)을 각자 읽고 독립적으로 분류체계를 도출. 기존 문서 분류 체계 사용을 프롬프트에서 명시적으로 금지.
2. **병합** — 3안의 수렴 지점을 codebook v1(13범주)으로 확정.
3. **폐쇄코딩** — 고정된 codebook으로 층화 표본 180파일 / **2,577단위** 전수 라벨링. 규칙 밖은 `OTHER` + 사유 필수.
4. **검증 3축** — (a) 표본 밖 무작위 450단위 커버리지 검증, (b) 150단위 이중라벨 κ, (c) 상위 800헤딩 → 코퍼스 40.4% 전수 매핑.

### 수렴 결과

격리된 3명 중 **7개 범주는 3/3 전원**이 독립적으로 도출했고, `completion-gates`는 이름까지 동일했다.

| 개념 | A | B | C |
|---|---|---|---|
| 레포 오리엔테이션 | .21 | .19 | .15 |
| 명령 레시피 | .17 | .14 | .11 |
| 표기 형식 | .11 | .10 | .13 |
| 완료 게이트 | .05 | .08 | .07 |
| 컨텍스트 라우팅 | .06 | .06 | .07 |
| 함정 경고 | .06 | .06 | .05 |
| 동반 수정 의무 | .05 | .03 | .05 |

병합 시 내린 판단 3건:
- C의 `capability-surface` → `context-routing`에 흡수 (A·B 모두 라우팅 정의에 스킬·도구를 이미 포함)
- A의 `engineering-values` → `agent-conduct`에 흡수
- A의 `ai-contribution-governance` + B의 `contribution-protocol` → 하나로 통합 ("사람에게 수용되게 만든다"는 같은 일)
- `project-invariants`와 `hard-boundaries`는 **분리 유지** — C는 묶었으나 "코드가 만족해야 할 속성"과 "에이전트가 하면 안 되는 행동"은 다른 질문에 답한다

---

## 3. 결과 — 13개 목적 범주

라벨 2,577건 중 본문 없는 헤딩 컨테이너 281건 제외, **2,296단위** 기준.

| # | 범주 | 하는 일 | 단위 비중 | **파일 채택률** | 평균 star |
|---|---|---|---|---|---|
| 1 | `repo-orientation` | 무엇이 어디 있는지 — 탐색 없이 길 찾기 | 33.5% | **80.0%** | 8,554 |
| 2 | `command-recipes` | 정확한 실행 명령 | 12.5% | 71.7% | 8,122 |
| 3 | `house-form` | 산출물의 표기 형식 | 11.1% | 50.6% | 11,023 |
| 4 | `project-invariants` | 코드가 만족해야 할 의미 계약 | 10.4% | 43.3% | 7,742 |
| 5 | `context-routing` | 언제 어떤 문서·스킬·도구를 부를지 | 5.2% | 33.3% | 14,925 |
| 6 | `task-procedure` | 작업 유형별 순서 | 5.1% | 35.0% | 12,927 |
| 7 | `pitfall-warnings` | 오진을 유발하는 함정·환경 특성 | 4.1% | 26.1% | 6,481 |
| 8 | `contribution-protocol` | 변경이 프로젝트에 수용되는 절차 | 3.5% | 25.0% | **24,235** |
| 9 | `completion-gates` | "완료" 선언 전 통과 기준 | 2.6% | 24.4% | 8,828 |
| 10 | `agent-conduct` | 에이전트 자신의 운영 방식 | 2.4% | 18.3% | **25,571** |
| 11 | `cochange-duties` | X를 고치면 Y도 고쳐라 | 2.2% | 21.1% | 13,063 |
| 12 | `hard-boundaries` | 절대 하지 말 것 | 2.0% | 18.3% | 12,461 |
| 13 | `human-authority` | 멈추고 사람에게 넘길 지점 | 0.6% | **6.7%** | 7,181 |
| — | `OTHER` | 지침이 아닌 내용 | 5.0% | 42.8% | 8,833 |

상위 800헤딩을 코퍼스 전체(40.4%)에 매핑한 결과가 **동일한 순위**를 재현했다 — `repo-orientation` 22,434파일 > `command-recipes` 11,967 > `house-form` 6,687 > `task-procedure` 4,974. 180파일 표본에서 얻은 순위가 12,749파일에서도 성립한다.

---

## 4. 검증

| 검증 | 결과 | 판정 |
|---|---|---|
| 표본 내 OTHER | 5.0% | — |
| **표본 밖 무작위 405단위 OTHER** | **6.2%** | **+1.2%p — 일반화 확인** |
| 이중라벨 일치도 (138단위) | **κ = 0.786**, 관측 82.6% | substantial (0.8 근접) |
| 전수 헤딩 매핑 | 표본과 순위 동일 | 독립 재현 |
| 배치 무결성 | 18/18, 출력 라인 수 = 입력 | 유실 0 |

**표본 밖에서 OTHER가 거의 오르지 않은 것이 핵심 결과다.** 45파일에서 도출한 분류가 12,749파일에 통한다는 직접 증거다. 커버리지 검증 배치 3개 모두 "새 범주가 필요한 단위는 없었다"고 독립 보고했다.

### 알려진 한계

- **`agent-conduct`는 두 개의 다른 목적을 합쳐 놓았다 (확정된 결함).** 병합 시 A의 `engineering-values`를 `agent-conduct`에 흡수하면서 "OTHER로 대량 재출현하면 승격"이라는 조건을 걸었는데, 조건 설정이 틀렸다. 실제로는 OTHER가 아니라 **`agent-conduct`를 부풀리는 형태**로 나타났다. 코퍼스의 `agent-conduct` 64단위는 헤딩이 61개로 거의 전부 다른데, `KISS`·`SOLID (apply pragmatically)`·`Pure Functions`·`Design Philosophy`(에이전트가 *만드는 산출물*의 설계 교리)와 `Agent roles for complex tasks`·`Thread management`·`Compact instructions`(에이전트 *자신*의 운영 설정)가 한 범주에 섞여 있다. 따라서 본 리포트의 `agent-conduct` 수치(2.4% / 18.3%)는 두 목적의 합이며, v2에서 분리해야 한다. 분리 시 각각의 채택률은 이 값보다 낮아진다.
- **`house-form` vs `project-invariants` 경계가 약하다.** 세 독립 축(라벨러 보고 · κ 불일치 행렬 최다 5건 · 커버리지 배치)이 같은 지점을 지목했다. 원인은 판별 질문("어기면 *틀린* 것인가 *어긋난* 것인가")이 **블록만 보고는 확인할 수 없는 런타임 결과를 추측하라고 요구**한다는 것. 다음 개정에서는 블록 자체로 결정 가능한 기준(규칙이 이 생태계 어디서나 성립하는가 vs 이 코드베이스의 특정 모듈·래퍼를 지목하는가)으로 교체해야 한다.
- **star 상위 구간 표본이 작다** (10k–50k는 14파일, 50k+는 8파일). 아래 구간별 수치는 경향으로만 읽어야 한다.
- **분석 단위가 job-density를 과소계상한다.** 블록의 15.1%가 두 가지 일을 겸하는데 스키마는 primary+secondary로 2개까지만 담는다. 3개 이상을 하는 블록이 실제로 존재한다.
- 채택률은 **층화 표본 180파일** 기준이므로 각 층의 비중이 모집단과 다르다. 순위 해석은 헤딩 전수 매핑으로 교차 확인했다.

---

## 5. 발견

### 5.1 AGENTS.md와 CLAUDE.md는 다른 용도로 쓰이고 있다

같은 규격의 두 이름이 아니라, 실제 사용이 갈렸다 (파일 채택률, n=98/80).

| 범주 | AGENTS.md | CLAUDE.md | 배율 |
|---|---|---|---|
| `contribution-protocol` | 0.35 | 0.14 | **2.5×** |
| `pitfall-warnings` | 0.35 | 0.16 | 2.2× |
| `completion-gates` | 0.33 | 0.15 | 2.2× |
| `hard-boundaries` | 0.23 | 0.12 | 1.9× |
| `cochange-duties` | 0.27 | 0.15 | 1.8× |
| `task-procedure` | 0.43 | 0.26 | 1.7× |
| `repo-orientation` | 0.77 | 0.86 | 0.9× |

**CLAUDE.md는 설명서, AGENTS.md는 규율 문서에 가깝다.** CLAUDE.md만 `repo-orientation` 쪽이 높고 나머지 12개 범주 전부에서 AGENTS.md가 우세하다.

### 5.2 프로젝트 규모가 커지면 대상이 코드베이스에서 에이전트로 옮겨간다

`agent-conduct`(평균 star 25,571)와 `contribution-protocol`(24,235)은 코퍼스 평균의 약 3배 지점에 몰려 있고, `pitfall-warnings`(6,481)와 `project-invariants`(7,742)는 최하위다.

대형 프로젝트는 **에이전트를 행위자로 규율**한다 — 운영 방식, 기여 절차, 무엇이 수용 가능한 기여인지. 소형 프로젝트는 **코드베이스를 설명**한다 — 함정 메모, 불변식. 개방코딩 A가 독립적으로 같은 것을 관찰했다: AI 기여 거버넌스(중복작업 확인, "순수 코드에이전트 PR 불가", DCO)는 **대량의 원치 않는 AI PR을 받는 고star 인프라 repo에만** 나타나고, 개인 repo에는 전무하다.

### 5.3 `human-authority`가 사실상 부재하다

채택률 **6.7%**로 압도적 최하위. 헤딩 전수 매핑에서도 94파일로, `repo-orientation`(22,434)의 0.4% 수준이다.

즉 **거의 아무도 "언제 멈추고 사람에게 물어라"를 쓰지 않는다.** 금지(`hard-boundaries` 18.3%)는 쓰지만 에스컬레이션 경로는 안 쓴다. 에이전트가 자율적으로 판단하다 막혔을 때 어떻게 해야 하는지가 업계 전반의 공백이다.

### 5.4 파일당 중앙값 4개 목적, 그리고 지시 없는 서두

파일당 다루는 목적 수는 중앙값 4개(평균 4.59). 15개 파일은 단 1개만 다룬다.

두 검증 모두에서 **OTHER 1위 사유가 `claude init` 스캐폴드의 보일러플레이트 서두**였다 — "This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository." 커버리지 표본 150단위 중 6회, 즉 **파일마다 거의 한 번씩** 지시 내용 0인 문장이 자리를 차지한다.

### 5.5 회람되는 룰팩이 통째로 복붙된다

개방코딩 A와 B가 각각 독립적으로 지목했다. `whyphp.dev`는 100% Laravel Boost 벤더 보일러플레이트이고, 무관한 8개 repo에 동일 계보의 블록이 반복된다. `Kingfisher`의 `AGENTS.md`는 여전히 "# CLAUDE.md ... guidance to Claude Code"로 시작한다(파일 복사). **파일명이 대상 도구를 뜻하지 않는다.**

---

## 6. 이 저장소의 글로벌 지침 파일 진단

`claude/CLAUDE.md`와 `codex/AGENTS.md`를 **동일한 분할 규칙·동일한 codebook**으로 라벨링했다 (26단위).

**비교 전제 교정**: 코퍼스는 **repo별** 지침이고 이 두 파일은 **글로벌 사용자 지침**이다. 따라서 `repo-orientation`·`command-recipes`·`project-invariants`·`contribution-protocol`이 없는 것은 누락이 아니라 **구조적 해당 없음**이다. 글로벌 파일이 특정 repo의 아키텍처를 서술할 수는 없다.

**크기 교정**: 두 파일은 diff 23줄(경로 변수 치환 + codex 전용 위임 권한 1줄)의 **쌍둥이**다. 고유 내용은 25.6KB가 아니라 **약 12.8KB** — 코퍼스 p75(8,571 B)와 p95(22,759 B) 사이다.

### 결과

| 범주 | 이 파일 | 코퍼스 채택률 |
|---|---|---|
| `agent-conduct` | 14/26 (54%) | 18.3% |
| `human-authority` | 2 | **6.7%** |
| `completion-gates` | 2 | 24.4% |
| `pitfall-warnings` | 2 | 26.1% |
| `house-form` | 2 | 50.6% |
| `cochange-duties` | 2 | 21.1% |
| `context-routing` | 2 | 33.3% |
| `hard-boundaries` | **0** | 18.3% |

**강점** — 코퍼스에서 가장 드물면서 가장 큰 프로젝트에만 나타나는 범주를 의도적으로 두껍게 쓰고 있다. `human-authority`는 코퍼스의 6.7%만 다루는 공백 영역이고, `Multi-Model Workflow`의 위임 게이트는 코퍼스에 사실상 대응물이 없다. `Tooling and Operational Safety`는 바이트당 페이로드가 가장 높다 — `input_tokens:0`이 사전 거절을 증명한다, `origin/base..HEAD`, I/O 대기와 행 구분 같은 **증상 결합형 함정**은 거의 모든 절이 구체적 판단을 바꾼다.

**갭 1건 — `hard-boundaries` 부재.** 무조건 금지 목록이 독립적으로 없고 `Tooling and Operational Safety` 안의 조건절로만 존재한다. 이건 원칙에 따른 선택이다(`LLM And Capability Boundary`가 "금지는 텍스트 반복이 아니라 capability surface로 강제하라"고 명시). 다만 잔여 위험은 실재한다 — **판단 조건부 규칙("자기 소유 대상으로 범위를 좁혀라")은 컨텍스트 압력에서 열화하지만 평문 금지("never force-push")는 그렇지 않다.**

**길이 대비 페이로드가 낮은 구간** (분석가 지적, 섹션명 명시):
- `LLM And Capability Boundary` — 약 15개 불릿이 "LLM은 판단, 코드는 결정적 산출물 소유"라는 한 규칙을 선회. 프론티어 모델은 대체로 지시 없이 수행함
- `Concept Economy` — 약 16개 불릿 ≈ "새로 만들기 전에 재사용, 행동이 달라질 때만 분리"
- `Decision Framing` — `Problem Solving`의 선택지 비교·기본값 선정·막힐 때만 질문 루프를 다른 대상 독자용으로 재진술
- **중복 지불 패턴**: `LLM And Capability Boundary`·`Coding Guidelines`·`Verification Discipline`이 가이드로 라우팅하면서 **동시에 그 가이드의 압축본을 인라인**한다 — 같은 교리에 컨텍스트를 두 번 낸다. `Verification Discipline`은 "green을 믿지 말라"를 세 불릿에 걸쳐 세 번 말한다

**해석 주의**: 54%라는 `agent-conduct` 집중도는 절반이 §4에 기록한 코드북 결함 때문이다. `LLM And Capability Boundary`와 `Concept Economy`는 에이전트를 행위자로 설정하는 게 아니라 산출물의 설계 교리이므로, `engineering-values`를 분리하면 실제 `agent-conduct` 비중은 약 30%가 된다. 이 파일은 그 결함을 드러낸 사례이자 분리의 근거다.

---

## 7. 재현

```
scripts/enumerate.py     # S1 모집단 전수 열거 (star/follower 구간 적응형 스윕)
scripts/probe.py         # S2 파일 존재 판정 (GraphQL, resumable)
scripts/fetch.py         # S2b 원문 수집
scripts/normalize.py     # S3 섹션 분할 · 중복 클러스터링 · 헤딩 어휘
scripts/sample.py        # S4a 층화 표본 · 리더 패킷
scripts/make_label_batches.py
scripts/aggregate.py     # 빈도 · 채택률 · κ
scripts/heading_map.py   # 전수 헤딩 매핑
scripts/report_stats.py  # 리포트 수치 (수기 입력 없음)
prompts/                 # 개방·폐쇄코딩 프로토콜
derived/codebook-v1.json # 13범주 정의 · 포함/제외 · 판별 질문
```

리포트의 모든 수치는 위 스크립트 출력에서 나왔다.
