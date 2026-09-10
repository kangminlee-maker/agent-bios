# 3계층 정리 — 전역 / 생태계·도메인 / 레포

2026-07-26 · 근거 데이터: `REPORT.md`(13범주, κ=0.786), `derived/scope_split.json`(이전율), 생태계 채굴(`scripts/scope_split.py` 계열)

## 0. 모델

리서치의 13개 목적 범주는 대부분 **계층을 관통**한다 — 같은 목적이 세 계층에 서로 다른 내용으로 존재한다. 계층을 가르는 실측 축은 **교차-repo 이전율**(무관한 repo에 글자 그대로 재등장하는 비율, 전체 파일 복제 884건 제외):

```
전역  ◀──────────────────────────────────▶  레포
agent-conduct 21.8%      …      repo-orientation 1.7%
(에이전트를 설정)                 (코드베이스를 서술)
```

- 양극단만 단일 계층: `agent-conduct`·`human-authority`는 전역의 본거지, `repo-orientation`은 레포 독점(이전율 1.7% = 평균의 ¼).
- 중간 이전율 범주(`house-form` 13.4%, `pitfall-warnings` 9.7% 등)의 공유 블록을 열어보면 **생태계에 묶인 내용**이다: Laravel `route()` 규칙 40개 repo, `npm run build` 함정 38개, 도구 게이트 36개.
- **핵심 해석: 코퍼스의 대량 복붙은 "생태계 계층이 없어서 새는 현상"이다.** 40개 repo가 같은 Laravel 블록을 각자 들고 있는 건 그 내용을 놓을 중간 계층이 표준에 없기 때문. 3개 이상 무관 repo에 재등장하는 블록 1,021종이 그 수요의 크기다.

| 계층 | 담는 것 | 우리 자산 | 상태 |
|---|---|---|---|
| **전역** | 에이전트 자체의 운영·판단·검증 규율 | `claude/CLAUDE.md` + 가이드 14종 (12.8KB 고유) | 있음 — 보완 대상 |
| **생태계·도메인** | 언어·스택·인프라별 규칙, 함정, 형식 | 도메인 패키지 아키텍처 (설계 완료, 미구현) | **코퍼스가 수요 실증** |
| **레포** | 이 코드베이스의 지도·명령·불변식·절차 | 없음 | **원리적 공백** |

---

## 1. 전역 — 현 패키지 보완/보강 백로그

동일 codebook으로 자체 파일 라벨링(26단위) + 코퍼스 대조 결과. 강점은 유지가 결정이고, 아래는 변경 후보다.

### 유지 (코퍼스가 희소성을 증명한 강점)
- `human-authority` 계열(Decision Framing, 보안 완화 게이트): 코퍼스 채택률 **6.7%** — 업계 공백을 우리는 이미 두껍게 다룸.
- `Multi-Model Workflow` 위임 게이트: 코퍼스에 사실상 대응물 없음.
- `Tooling and Operational Safety`: 바이트당 페이로드 최고(증상 결합형 함정 — `input_tokens:0` 사전거절 증명, `origin/base..HEAD`, I/O대기 vs 행).

### 보완 백로그 (우선순위순)
| # | 항목 | 근거 | 방향 |
|---|---|---|---|
| G1 | **중복 지불 제거** | `LLM And Capability Boundary`·`Coding Guidelines`·`Verification Discipline`이 가이드로 라우팅하면서 압축본을 인라인 — 같은 교리에 컨텍스트 2회 지불. "green을 믿지 말라"는 한 섹션에서 3회 진술 | 라우팅+인라인 → 라우팅+**1줄 요지**로 통일. 최대 절감 구간 |
| G2 | **`hard-boundaries` 평문 금지 목록** | 무조건 금지가 조건절 안에만 존재. 판단 조건부 규칙은 컨텍스트 압력에서 열화, 평문 금지는 안 함 | capability surface가 못 막는 영역(원격 파괴, 이력 개변 등)만 5줄 내외. "금지는 표면으로 강제" 원칙과 양립 |
| G3 | **`Decision Framing` 통합 검토** | `Problem Solving`의 비교→기본값→막힐 때만 질문 루프를 다른 독자용으로 재진술 | 중복 절 제거, 고유 내용(결과 언어로 설명, 옵션 프레임)만 잔존 |
| G4 | **`engineering-values` 분리 정리** | `LLM And Capability Boundary`·`Concept Economy`는 에이전트 설정이 아니라 **산출물 설계 교리** (코드북 v2 분리 근거와 동일). 프론티어 모델은 상당 부분 지시 없이 수행 | 전역 본문 슬림화, 가이드 전담 + G1과 연동 |
| G5 | **커밋 스타일 명문화** | 평서문 제목 컨벤션이 일관 실행 중이나 불문율 (`contribution-protocol` 코퍼스 유일 완전 공백의 우리쪽 조각) | 3–4줄. 전역이 아니라 **레포 계층**(agent-bios AGENTS.md)에 두는 게 맞음 → R1로 이관 |

## 2. 생태계·도메인 — 패키지 후보 (코퍼스 실측 수요순)

3개 이상 무관 repo에 재등장하는 블록 1,021종을 공유 repo들의 지배 언어로 클러스터링:

| 수요 | 블록종 | 실측 내용 예시 | 패키지 후보 |
|---|---|---|---|
| TypeScript/JS | **230** | 트리아지 라벨, 프론트엔드 빌드 함정(38 repo), npm 스크립트 규약 | `@bios/typescript`, `@bios/frontend-web` |
| Rust | 139 | cargo 워크스페이스 게이트, beads_rust 계열 룰팩(38 repo) | `@bios/rust` |
| PHP/Laravel | 111 | `route()` 명명 라우트(40 repo), Livewire/Pest 규칙 — Laravel Boost 벤더팩이 원류 | `@bios/laravel` |
| Python | 49 | pip/의존성, pytest 경로 규약 | `@bios/python` |
| Go | 37 | cmd/ 레이아웃, 단일 그룹 규약 | `@bios/go` |
| Elixir | 32 | 리스트 인덱스 접근 불가 등 **언어 함정**(8 repo) | `@bios/elixir` |
| 범용(MIXED) | 247 | 대부분 보일러플레이트 서두·범용 룰팩 → 전역 계층 소관 또는 노이즈 | 패키지 아님 |

- **구조 검증**: 벤더 룰팩(Laravel Boost)이 이미 이 계층의 원시적 형태로 유통 중 — 우리 패키지 모델(`@scope/name`, prose-only, 단일/조직 저자)은 이것의 정제판. `ECOSYSTEM-ARCHITECTURE.md`의 결정(coarse-then-split-on-evidence)과 정합: 언어 단위로 시작, 블록종 수가 세분화(예: `@bios/frontend-web`를 React/Vue로)의 증거가 되면 분리.
- 패키지가 담아야 할 범주 프로파일(실측): `house-form`(언어 컨벤션) + `pitfall-warnings`(스택 함정) + `command-recipes`(도구체인 공통부) + `completion-gates`(생태계 게이트 도구).

## 3. 레포 — 목적 유형별 세분화

레포 계층은 "하나의 템플릿"이 아니다. 코퍼스에서 **레포의 목적이 범주 배합을 규정**하는 것이 관측됨 (개방코딩 A·B 독립 관찰 + star 구간 실측):

| 레포 목적 유형 | 코퍼스 관측 | 범주 배합 (두꺼워야 할 것) |
|---|---|---|
| **라이브러리/프레임워크** (외부 기여 수용) | 고star 인프라 repo에서 `contribution-protocol`·AI-PR 정책이 결정적으로 등장 (vllm, electron: 중복 PR 확인, "순수 코드에이전트 PR 불가", DCO) | `contribution-protocol` + `completion-gates` + `hard-boundaries` |
| **애플리케이션/제품** | 배포·환경·데이터 계약 중심, 불변식 밀도 높음 | `project-invariants` + `pitfall-warnings` + `cochange-duties` |
| **CLI/단독 도구** (단일 저자) | "공동 유지보수자 브리핑" 스타일 — 밀도 높은 불변식 + 설계 근거 | `repo-orientation` + `project-invariants` + `task-procedure` |
| **모노레포/플랫폼** | 중첩 AGENTS.md, 라우팅 중심 (50k+ 구간에서 `context-routing` 0.62, `task-procedure` 0.88) | `context-routing` + `task-procedure` |
| **콘텐츠/문서 repo** | 코퍼스 OTHER의 주요 원천 (블로그·커리큘럼 통붙임) — 지침 파일이 사실상 불필요하거나 최소 | `repo-orientation` 최소본만 |

- 레포 목적 → 필요한 섹션 집합을 내는 **목적별 템플릿**이 가능하다. agent-bios 관점에서는 `agent-bios onboard`가 레포 목적을 물어 해당 프로파일의 골격을 생성하는 형태.
- **R1 (즉시 실행 가능)**: agent-bios 저장소 자체의 repo-level `AGENTS.md`/`CLAUDE.md` 작성 — 유형은 "CLI/단독 도구". `repo-orientation`(gates/·compose/·launch/ 지도, 배포 이중 경로 함정), `command-recipes`(verify·parity·assemble), `project-invariants`(LEXICON 게이트, 5-lockstep parity), 커밋 스타일(G5 이관분).

## 4. 이 정리가 기존 결정과 만나는 지점

- **도메인 패키지 아키텍처**(`design/adapter-split/ECOSYSTEM-ARCHITECTURE.md`): 본 리서치가 생태계 계층의 수요(1,021 블록종)와 내용 프로파일을 실증 — 패키지 로드맵의 우선순위 데이터로 사용.
- **placement framework**(enforcement > gates > … > 전역): 계층 내 배치 원칙은 그대로 유효. 본 문서는 "어느 파일에"가 아니라 "어느 **범위**에"를 정하는 상위 축.
- **코드북 v2 예고 사항**: `agent-conduct`에서 `engineering-values` 분리(확정 결함), `house-form`/`project-invariants` 판별 기준 교체 — 이 분리는 G4·계층 프로파일 정밀화와 연동.
