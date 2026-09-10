<!-- Archived 2026-09-03 from branch `corpus-global-slimming` (7a392a0), which was never
merged. Numbers below describe the corpus as of 2026-08-05; the global has since gone from
119 bullets to 77. The live item is FINDINGS.md F-17, which carries figures re-derived
against current main. This file is kept for the change list and its reasoning only. -->

# 코퍼스 개정 — 목표 · 근거 · 진행 · 계획

2026-08-05 · 브랜치 `corpus-global-slimming` · 측정의 소유자는 `research/agents-md/`

이 문서는 **결정 고도로 압축한 사본**이다. 수치의 소유자는 `research/agents-md/REPORT.md`
(코퍼스·분류·검증)와 `LAYERS.md`(계층 축·백로그)이며, 여기서 다시 적는 이유는 하나다 —
무엇을 바꿀지 판단할 때 필요한 것은 172,279단위의 분포가 아니라 **그 분포가 licensed하는
변경 목록**이다. 두 수치가 어긋나면 원본이 맞다.

---

## 1. 목표

**우리 지침 코퍼스의 모든 변경이 측정된 근거 위에서 이뤄지게 한다.** 지침 파일은 "좋아 보이는
규칙"이 무한히 누적되는 방향으로 썩는데, 무엇이 실제로 페이로드를 내는지에 대한 외부 기준이
없기 때문이다. 12,749개 권위 파일이 그 기준을 제공한다.

파생 목표 — 각각이 별개의 결정을 바꾼다:

- **범위 축을 명시한다.** 어떤 규칙이 전역·생태계·레포 중 어디 소속인지가 지금까지 암묵이었다.
- **컨텍스트 예산을 회수한다.** 전역은 모든 세션이 무조건 지불한다. 중복 지불은 순손실이다.
- **결정적으로 강제할 수 없는 영역만 문장으로 남긴다.** 나머지는 capability surface의 일이다.

---

## 2. 근거

### 2.1 이 근거를 믿어도 되는 이유

| 축 | 값 | 의미 |
|---|---|---|
| 모집단 열거 | user 8,364 / repo 38,851 | 둘 다 API 총계와 정확히 일치 — 표본이 아니라 전수 |
| 파일 판정 | 123,428 repo, 실패 배치 **0 / 6,172** | 유실 없음 |
| 최종 코퍼스 | **12,749 파일 / 11,374 repo** | |
| 분류 일치도 | **κ = 0.786** (관측 82.6%) | substantial |
| 표본 밖 일반화 | OTHER 5.0% → **6.2%** | 45파일에서 도출한 체계가 12,749파일에 성립 |
| 독립 재현 | 상위 800헤딩 → 코퍼스 40.4% 전수 매핑 | 표본과 **순위 동일** |

웹 `path:` 검색은 API로 재현되지 않는다(구 인덱스 의미 + 쿼리당 1,000건 상한). 그래서 방향을
뒤집어 **자격 조건을 먼저 전수 열거하고 파일 존재를 확인**했다. 이것이 "권위 있는 파일"을
정의상 100% 덮는 유일한 경로였다.

### 2.2 과잉 해석하면 안 되는 것

- **`agent-conduct`는 두 목적의 합이다(확정 결함).** 산출물 설계 교리(`KISS`, `SOLID`)와 에이전트
  운영 설정(`Agent roles`, `Thread management`)이 한 범주에 섞였다. 아래 §2.4의 "우리 파일
  54%"는 절반이 이 결함이며, 분리 시 실제 비중은 약 30%다. **G4의 근거는 이 분리 자체이지
  54%라는 숫자가 아니다.**
- `house-form` / `project-invariants` 판별 기준이 약하다(런타임 반사실을 요구).
- star 상위 구간 표본이 작다(10k–50k 14파일, 50k+ 8파일) — 구간별 수치는 경향으로만.
- 채택률은 층화 표본 180파일 기준. 순위는 헤딩 전수 매핑으로 교차 확인됐다.

### 2.3 계층 축 — 측정으로 갈린다

계층을 가르는 실측 축은 **교차-repo 이전율**(무관한 repo에 글자 그대로 재등장, 전체 파일 복제
884건 제외)이다.

```
전역 ◀───────────────────────────────────────▶ 레포
agent-conduct 21.8%        …        repo-orientation 1.7%
```

핵심 해석: 중간 이전율 범주의 공유 블록을 열면 **생태계에 묶인 내용**이다(Laravel `route()`
40 repo, `npm run build` 함정 38 repo). 즉 **코퍼스의 대량 복붙은 관행이 아니라 "생태계 계층이
없어서 새는 현상"**이고, 3개 이상 무관 repo에 재등장하는 블록 **1,021종**이 그 수요의 크기다.
이것이 도메인 패키지 아키텍처(`design/adapter-split/ECOSYSTEM-ARCHITECTURE.md`)의 실증이다.

### 2.4 우리 파일 진단

같은 codebook으로 `claude/CLAUDE.md`를 라벨링(26단위). **비교 전제 교정**: 코퍼스는 repo별
지침이고 우리 것은 글로벌이므로 `repo-orientation`·`command-recipes` 부재는 누락이 아니라
구조적 해당 없음이다.

| 판정 | 내용 |
|---|---|
| **강점 — 유지가 결정** | `human-authority`(코퍼스 채택률 **6.7%**, 업계 최대 공백)를 두껍게 다룸. `Multi-Model Workflow` 위임 게이트는 코퍼스에 대응물 없음. `Tooling and Operational Safety`는 바이트당 페이로드 최고 |
| **갭 1건** | `hard-boundaries` **0** (코퍼스 18.3%) — 무조건 금지가 조건절 안에만 존재 |
| **저페이로드 구간** | `LLM And Capability Boundary`·`Concept Economy`가 각각 한 규칙을 15–16불릿으로 선회. 세 섹션이 가이드 라우팅과 인라인 압축본을 **동시에** 실어 같은 교리에 컨텍스트를 두 번 지불 |

### 2.5 현 기준선 (측정값, `claude/CLAUDE.md` @ `b995613`)

총 **119불릿 / 26,495 B**. 개정 대상 구간:

| 섹션 | 불릿 | 바이트 | 최장 불릿 | 해당 항목 |
|---|---|---|---|---|
| Multi-Model Workflow | 9 | 4,565 | 149 단어 | — (강점, 유지) |
| Verification Discipline | 14 | 4,053 | 134 단어 | G1 |
| Coding Guidelines | 15 | 3,373 | 136 단어 | G1 |
| LLM And Capability Boundary | 15 | 2,831 | 59 단어 | **G1 + G4** |
| Concept Economy | 16 | 2,565 | 61 단어 | **G4** |
| Decision Framing | 10 | 1,535 | 52 단어 | G3 |

---

## 3. 범위

**포함** — 전역 개정(G1–G4), 레포 계층(R1, 완료), 생태계 파일럿 1개 패키지.

**비포함** — codebook v2(연구 후속, 의도적 분리: 개정을 연구 개정에 묶으면 둘 다 멈춘다),
composer §3(패키지 조립 경로, 기존 결정대로 유예), 제3자 패키지 배포·신뢰 모델.

---

## 4. 결정 기록

| # | 결정 | 대안 | 근거 | 일자 |
|---|---|---|---|---|
| D1 | 계층은 이전율로 가른다 | 직관적 분류 | 양극단이 21.8% vs 1.7%로 실측 분리됨 | 07-26 |
| D2 | 순서 = R1 → G2 → G1+G4 → G3 → 파일럿 | 큰 절감(G1)부터 | 추가·저위험을 먼저 두어 되돌리기 쉬운 것부터 확정 | 07-26 |
| D3 | G5(커밋 스타일)는 레포 계층으로 이관 | 전역에 유지 | 전역 파일이 특정 repo 관례를 담을 수 없음 → R1에 흡수 | 07-26 |
| D4 | `Hard Boundaries`는 capability surface가 못 막는 것만 | 금지 전반 열거 | "금지는 표면으로 강제" 원칙과의 양립 조건 | 08-05 |
| D5 | 코퍼스 섹션은 **불릿만** | 머리말 산문 허용 | 조립기가 앵커로 `- ` 불릿만 선택 → 산문은 배포본에 미도달 | 08-05 |
| D6 | 베이스는 main | ontology-seed 위 | `claude/CLAUDE.md` 겹침이 1줄뿐 | 08-05 |

---

## 5. 진행

| 항목 | 커밋 | 상태 |
|---|---|---|
| **R1** 레포 계층 `AGENTS.md` (유형: CLI/단독 도구) | `4ef3d57` (ontology-seed) | 완료 — G5 흡수 |
| 리서치 산출물 트래킹 (46파일) | `99bcbd0` | 완료 |
| **G2** `Hard Boundaries` 평문 금지 5줄 | `b995613` | 완료 |

**G2에서 확인된 사실 2건** (이후 모든 코퍼스 변경에 적용):

1. **미등록 불릿은 배포되지 않는다.** `compose/domains.json`이 불릿과 전단사를 요구하며,
   등록 없이는 도메인 게이트가 막는다(114 vs 119). 게이트가 없었다면 변경이 정본에만 남고
   런타임에 도달하지 않은 채 통과했을 것이다.
2. **섹션 산문은 조립에서 탈락한다**(D5). 실제 번들을 확인해 발견했고, 정본에만 남는 inert
   텍스트가 되므로 제거했다.

---

## 6. 계획

### G1 + G4 — 중복 지불 제거 + 설계 교리 이관 (한 패스)

두 항목이 **같은 섹션을 건드리므로** 분리하면 같은 텍스트를 두 번 재작성하게 된다.

- **목표** — 라우팅 + 인라인 압축본 → 라우팅 + **1줄 요지**. `LLM And Capability Boundary`와
  `Concept Economy`는 에이전트 설정이 아니라 산출물 설계 교리이므로 가이드가 전담한다.
- **근거** — §2.4 저페이로드 구간, §2.2의 codebook 결함(분리 근거는 결함 자체).
- **done-when** (falsifiable)
  - 두 섹션 합계 5,396 B → **≤ 2,700 B** (절반 이하), 전체 119불릿 대비 순감소가 diff로 증명됨.
  - **이관은 삭제가 아니다**: 제거한 각 불릿의 요지가 대상 가이드에 실재함을 앵커 문구 grep으로
    확인하고, 그 목록을 커밋 본문에 남긴다. 이 검사가 이 항목의 유일한 실질 판정이다.
  - 조립 후 번들에서 해당 교리로 가는 **라우팅 불릿이 살아 있다**(도달 가능성 유지).
- **위험** — 삭감은 추가보다 되돌리기 어렵다. 프론티어 모델이 지시 없이 수행한다는 §2.4의
  판단은 분석가 관측이지 대조 실험이 아니다. ⇒ **삭감 목록을 먼저 제시하고 승인 후 실행.**

### G3 — `Decision Framing` 통합

- **목표** — `Problem Solving`과 중복인 절(선택지 비교 → 기본값 선정 → 막힐 때만 질문) 제거,
  고유 내용(결과 언어로 설명, 옵션 프레이밍)만 잔존.
- **done-when** — 10불릿 / 1,535 B에서 중복 절이 사라지고, 남은 불릿이 `Problem Solving`의
  어느 불릿과도 같은 지시를 하지 않음을 쌍대 대조표로 제시.
- **주의** — `human-authority`는 §2.4의 **강점**이다. `Decision Framing`은 그 범주의 담지체이므로
  통합이 human-authority 밀도를 낮추면 목표에 역행한다. 축소가 아니라 중복 제거로 한정한다.

### 생태계 파일럿 — 패키지 1개

- **목표** — 도메인 패키지가 실제로 조립·배포되는지 증명. 대상은 사용자의 실 스택(TypeScript
  230 블록종 또는 Python 49 중 택1).
- **큐레이션 기준** — "프론티어 모델 기본값을 넘어서는 것만". 모델이 이미 하는 일을 적으면
  §2.4의 저페이로드 문제를 생태계 계층에 복제하는 것이다.
- **done-when** — 패키지가 선택됐을 때만 해당 불릿이 번들에 실리고, **미선택 시 실리지 않음을
  네거티브 컨트롤로 증명**. 도메인 게이트 통과.

---

## 7. 검증 프로토콜

코퍼스 변경 1건당 아래 전부를 돌린다.

| 검사 | 무엇을 증명하나 |
|---|---|
| `gates/emit-mirrors.py --write` → `--check` | `codex/`·`ko/codex/`가 정본의 투영과 일치 |
| `gates/emit-mirrors.py --self-test` | 네거티브 컨트롤 9종 — 한쪽만 고친 편집이 실제로 잡히는지 |
| `gates/check-lexicon.py` | 용어 게이트 |
| `gates/check-package.sh` | 런타임 경로가 npm `files[]`에 포함 |
| `compose/check-domains.py` | 불릿 전단사 — **미등록 불릿 차단** |
| `gates/test-assemble.sh` | 조립기 시나리오 S1–S6 |
| `gates/check_parity.py --only ...` (코퍼스 8종) | 프로필 투영·바이패스·역할 슬롯·래퍼 |

**실행 경로로 확인한다.** 게이트 통과는 조립 산출물 확인을 대체하지 않는다 — 실제로 조립해
섹션과 불릿이 번들에 있는지 본다(G2에서 D5를 발견한 방식).

**리터럴 드리프트**: `gates/test-assemble.sh`의 기대 개수는 core 티어 변경 시 함께 움직인다.
조립기 출력에서 **재측정해** 갱신하고, 숫자를 맞추려 고치지 않는다. 선택 도메인이 달라도
증가폭이 동일하면 core 티어에 들어갔다는 증거다(G2에서 일률 +5).

**미검증으로 남는 것**: parity의 런처 TUI 픽스처 24종은 대화형 터미널을 요구해 이 환경에서
실행 불가다. 게이트가 공허하게 통과하지 않고 중단하는 것은 올바른 설계다. 코퍼스 표면 8종만
판정에 쓰며, 부분 실행은 전체 게이트를 대신하지 않는다.

---

## 8. 열린 항목

| # | 항목 | 성격 |
|---|---|---|
| O1 | 조립기가 섹션 산문을 **조용히** 버린다 — 경고도 게이트도 없다 | 결함 후보. D5는 회피책이지 수정이 아님 |
| O2 | G1+G4 삭감 목록 승인 대기 | 사용자 결정 |
| O3 | codebook v2(`engineering-values` 분리, `house-form` 판별 기준 교체) | 연구 후속, 본 개정의 선행조건 아님 |
| O4 | 런처 픽스처를 비대화형에서 돌릴 경로 | 검증 공백 |

## 9. 관련 문서

- `research/agents-md/REPORT.md` — 코퍼스 구성·분류·검증·우리 파일 진단 (수치의 소유자)
- `research/agents-md/LAYERS.md` — 3계층 모델·백로그·패키지 후보 (계층 축의 소유자)
- `design/adapter-split/ECOSYSTEM-ARCHITECTURE.md` — 도메인 패키지 아키텍처
- `design/session-distill/PLACEMENT-FRAMEWORK.md` — 계층 **내부** 배치 원칙 (본 문서는 범위 축)

---

## The five bullets as written on the branch (b995613)

Kept here so the branch is disposable.

- Never rewrite or erase history others already have: no force-push, amend, rebase, or reset on a shared branch, and no deleting a remote branch, tag, or release.
- Never destroy data, infrastructure, or accounts you were not asked to destroy.
- Never disable, weaken, or route around a check, gate, test, or negative control so that work passes; a failing check is reported, never silenced.
- Never emit a secret, credential, or private artifact anywhere it outlives the moment — a commit, a remote, a log, an issue, or a third-party service.
- Never take an irreversible outward action — publishing, sending, deploying, granting, revoking — that the user did not ask for.
