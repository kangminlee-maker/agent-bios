# agent-bios 개발 참여

[← 소개](README.md) · [English](../CONTRIBUTING.md)

agent-bios checkout이 필요하다. 작업 규칙의 기준은 [AGENTS.md](../AGENTS.md)이며, 지침 파일은 개발 지시가 아니라 배포할 제품 내용이다.

## 수정 절차

1. `claude/`의 영어 정본과 필요한 `ko/claude/` 한글 정본을 수정한다.
2. `python3 gates/emit-mirrors.py`로 Codex 투영을 생성한다. 생성된 트리는 손으로 수정하지 않는다.
3. 클론마다 `git config core.hooksPath .githooks`를 설정한다. 패키지·파리티 게이트를 통과시킨 뒤 커밋한다.
4. 작업 중인 checkout을 로컬에 배포하려면 루트에서 `bash install.sh install --non-interactive`를 사용한다. 전역 CLI는 설치된 npm 패키지를 배포한다.

게이트는 인덱스 스냅샷을 검사하며 검증 중 인덱스가 바뀌면 커밋을 거부한다. CI는 없으므로 실제 검사 결과를 확인한다. 게시에는 별도의 출처·깨끗한 커밋·원격 도달성 검사가 적용된다.

## Layout

| 경로 | 역할 |
| --- | --- |
| `claude/CLAUDE.md`, `codex/AGENTS.md` | 선택된 활성 세션에 전달하는 영어 정본·생성 투영. 사용자 전역 파일에 설치하지 않음 |
| `claude/guides/*.md`, `codex/guides/*.md` | 선택된 불변 고정본에 복사하는 영어 가이드 |
| `codex/agents/*.toml` | private 릴리즈에 보관하는 Codex 역할 템플릿. native 활성화는 별도 |
| `ko/**` | 한글 지침 투영과 사용자·개발자 참고 문서. 설치·모델 로드 대상이 아님 |
| `launch/` | launch profile, preflight TUI, 선택적 private 셸 연결과 legacy 호환 경로, 내장 UI 런타임, prompting-target 검사 |
| `compose/` | private 지침·고정본·관리 UI, 터미널/대화 공통 설치 엔진, 원본 보존 가져오기, 명시적 앱 연결, 호스트 전달과 세션 고정 |
| `learn/` | collection loop — capture, record schema와 validator, curation intake, promotion manifest, 재배포, secret-redaction floor |
| `session-distill/` | 여러 세션을 지침 등급 항목으로 정제하는 heavy curator 파이프라인 |
| `wrappers/` | private 릴리즈의 내부 실행·리뷰 어댑터. 기본 설치는 호스트 bin에 배치하지 않음 |
| `gates/` | author-side 검증 (미러 생성, parity, lexicon, payload, assembler 시나리오) — repo 체크아웃에서만 닿을 수 있고, npm payload에 들어가면 `check-package.sh`가 실패시킨다 |
| `ontology/` | 어떤 변경이 다른 무엇을 의무로 만드는지 — 엔티티, 의무 엣지, 서비스 라우트를 `check-ontology.py`가 실제 소스에 대조해 지킨다. `instances/graph.json`이 정본이고 `LEXICON.md`·RDF 뷰·HTML 맵·competency/extension 문서가 거기서 생성된다 |
| `install.sh`, `session-cost.py` | CLI와 비용 측정기 — 직접 실행하는 두 가지(설치 후에는 `agent-bios`와 `agent-bios cost`) |
| `decisions/` | 이 레포를 개발하며 내린 결정의 기록 — 무엇을 정했고 어떤 대안을 닫았는지. author-side라 배포되지 않는다 |
| `packages/` | 저작된 지침 패키지. concept home이 아니라 패키지 정체성으로 조직된다 |
| `.githooks/` | 게이트를 인덱스에 대고 돌리는 pre-commit 훅. 클론마다 `core.hooksPath`로 한 번 켠다 |
| `design/`, `benchmarks/` | 설계 기록과 instruction-behavior 벤치마크 |
| `research/` | corpus 연구(12,749개 AGENTS.md/CLAUDE.md 분류): 보고서·스크립트·라벨링 기록; 벌크 데이터는 `.gitignore` 규칙으로 로컬에 남는다 |
| `docs/` | 사용자 운영·세션·복구·실행·학습 문서와 UI 이미지 |
| `DEPENDENCIES.md` | 외부 도구·host CLI·모델 provider + 검증 버전 |

`config.toml`, `settings.json`, `hooks.json`은 머신 종속(신뢰 목록, 훅 경로, 시크릿)이라 의도적으로 추적하지 않는다.

## 지침과 문서 변경

지침의 배치·용어·모델 바인딩·검증 정책은 [개발 규칙](../AGENTS.md)과 [영문 개발 안내](../CONTRIBUTING.md)를 따른다. 새 환경에서는 `(private)` 표시와 가이드의 Environment Binding, 환경별 도구를 검토하고 수치는 재측정한다.

README는 사용자의 시작 경로를 설명하고, 상세 운영은 `docs/`에 둔다. 실제 UI를 격리된 기본 지침으로 캡처하고 버전·Textual 조건을 표시한다. 개인 경로·계정·내용은 캡처에 포함하지 않는다.
