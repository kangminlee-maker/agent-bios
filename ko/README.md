# agent-bios

여러 LLM CLI 에이전트(Claude Code, Codex CLI)를 하나의 작업 규율로 움직이는 전역 지침·scoped guide의 단일 진실 원천(SSOT). 한 번 다듬으면 모든 에이전트, 모든 환경에 적용된다.

이 폴더 `ko/`는 아래 모든 문서의 한글 미러다 — **참고 전용이며 설치·로드되지 않는다.** 영어 정본은 상위 폴더에 있다.

## Model

### Corpus Studio의 가이드 참조 표시

규칙 본문에 `guides/*.md` 경로가 명시되어 있으면 목록 앞에 **→ GUIDE**와
가이드 이름을 표시한다. **Guide pointer** 영역에서 같은 패키지의 해당 가이드로
이동할 수 있으며, 대상의 현재 소비방식과 삭제·충돌 상태를 함께 보여준다.
연결 대상이 없거나 여러 개이면 추측하지 않고 그 상태를 표시한다.
표시만 바꾸므로 본문·ID·순서·선택·소비방식은 유지된다. 가이드의 로드나 실행을
증명하는 표시가 아니며, 일반 규칙을 의미에 따라 자동 분류하지 않는다.
개인 수정으로 참조 문구를 바꾸면 목록을 새로 읽을 때 표시도 갱신된다.

### Corpus 이해 세션

Private launcher의 **Understand!**에서 학습할 corpus 묶음을 선택한다.
`agent-bios understand list`로 목록을 보고,
`agent-launch --understand core-purpose claude` 또는 `codex`로 시작할 수도 있다.
단위는 개별 파일이 아니라 목표·범위, 의사결정, 피드백, 근거·안전, 학습 등
공통 목적을 가진 묶음이다. 개인 수정이 반영된 내용을 세션 시작 시 고정한다.
튜터는 규칙의 존재 이유와 배경, 작동원리, 한계를 설명하고 문서에 있는 근거와
추론을 구분한다. 매 학습 턴은 목적에 맞는 질문 하나로 끝나며 사용자 답변을
기다린다. 모든 모호함을 묻지는 않고, 중단·종료 요청에는 질문을 멈춘다.

사용자가 먼저 의미 있는 허점이나 대안을 발견하면 픽셀 트로피를 해금할 수 있다.
튜터가 먼저 제시한 아이디어·유도 질문의 반복은 대상이 아니다. 실제 호스트 세션의
사용자 발화와 순서를 확인하고, 이후 발화로 정확한 저장 문구를 확인받은 다음,
요청 시에만 소비되는 개인 corpus 항목 저장이 성공해야 트로피가 열린다.
발화 출처를 확인할 수 없으면 학습은 이어가되 수상은 보류한다. 의미적 독창성과
중요도는 튜터·사용자가 판단하며, 파일 검증으로 그것까지 증명했다고 주장하지 않는다.
트로피는 CLI와 공간이 충분한 TUI에 표시되고 업데이트·개인 항목 삭제 후에도 유지된다.
전체 초기화는 활성 해금 세대를 보관 후 제거하므로 과거 수상 기록이 표시를 되살리지 않는다.
학습 내용은 실행 지시가 아닌 자료이며 전역 `AGENTS.md`·`CLAUDE.md`는 수정하지 않는다.

두 계층:

- **전역 지침** — `claude/CLAUDE.md` ↔ `codex/AGENTS.md` (상호 미러). 매 세션 로드. 항상 켜져 있어야 하는 불변식, 결정 원리, 가이드 포인터만 담는다. 자격 기준: **에이전트가 상황을 인지하지 못했을 때도 작동해야 하는 규칙**만 전역에 둔다 — 인지 실패가 곧 사고 원인인 규칙은 포인터 뒤에 두면 죽는다.
- **Scoped guides** — `claude/guides/`, `codex/guides/`. 전역 포인터가 발동할 때 로드. 절차, 표, 수치, 환경 종속 내용은 전부 여기.

## Principles

`slide-writing` guide는 `office-work`와 `visualization-docs` 선택에 포함된다.
Primary guide는 모든 슬라이드와 프레젠테이션 작업의 semantic criteria를 제공한다.
Companion runbook과 scripts는 명시적으로 적용 가능한 정적 HTML/PDF job에만 쓴다.
준비 단계는 job-local criteria 사본과 `ORACLE.json`을 만들고 job input 및 runtime
version과 함께 고정한다. Job은 불변 corpus snapshot 밖에 둔다. 준비·접수에는 Python을,
렌더에는 `DEPENDENCIES.md`의 선택 의존성을 사용한다. 사용자가 요청한 프레젠테이션
형식은 유지하며, 제공된 renderer의 기계 검사는 정적 HTML/PDF 경로에 한정된다.

- **규칙 본문은 모델·도구 이름을 쓰지 않는다** — role slot과 tier로만. 바인딩은 각 가이드 `Environment Binding`에 있고 날짜·만료(~8주 또는 신규 모델 관측 시)를 가진다. 새 모델 → 그 행과 날짜만 갱신, 규칙은 손대지 않는다. 선언된 예외: 주제 자체가 구체 tool 표면인 섹션(cli 가이드의 Codex direct-drive 섹션)과 `DEPENDENCIES.md`에 등재된 선택적 capability 이름(예: `spreadsheet-processing` skill) — 둘의 교체는 아래 채택 체크리스트가 다룬다.
- **Codex 트리는 손으로 맞추는 미러가 아니라 생성물** — `gates/emit-mirrors.py`가 `claude/` → `codex/`, `ko/claude/` → `ko/codex/`를 투영한다. 차이는 제목과 config-home 변수(`$CLAUDE_CONFIG_DIR` ↔ `$CODEX_HOME`), 그리고 Codex trigger contract에 필요한 하나의 선언된 Codex-only standing-dispatch authorization을 고정 위치에 삽입하는 것뿐이다. 투영 규칙은 이 생성기가 단독 소유하며, `gates/check-parity.sh`가 그 `--check`를 실행하고 여기에 포인터 해석·frontmatter, 남겨둔 전역↔가이드 재진술 쌍의 공유 anchor 문구, Codex role-binding / wrapper-default projection을 더한다. 파리티가 강제하는 것은 내용 동기화뿐이다; 같은 문구에 두 하네스가 같은 강도로 반응한다는 보장은 아니다.
- **전역 파일은 세션당 토큰 예산이다** — 매 세션·모든 subagent에 재전송되고, 불릿 하나가 늘 때마다 다른 모든 규칙이 희석된다. 새 전역 불릿은 자기가 밀어내는 불릿(또는 없는 이유)을 명시해야 한다; 절차·표·수치·작업 예시는 가이드 소속이다.
- **배포는 로딩이 아니다** — 파일이 있다는 사실로는 거절된 import 승인이나 깨진 진입 import 줄을 알아낼 수 없다. 그래서 `onboard`는 activation canary로 끝나고 `verify`는 진입 import 줄을 확인한다. 안착했지만 읽히지 않는 코퍼스는 아무것도 바꾸지 않았다.
- **우리 것이 아닌 파일에 쓰는 모든 구간에는 지우는 짝이 있다** — Codex config 블록, settings 훅 등록, `AGENTS.md` central 구역, zsh 훅 줄은 각각 우리 것으로 식별 가능한 구간(마커 쌍·태그된 줄·manifest 이름)에 들어가고, `uninstall`은 정확히 그것만 지우고 주변은 건드리지 않는다. 진입 `CLAUDE.md`/`AGENTS.md`는 한 번 심긴 뒤 사용자 것이다: 코퍼스는 `central/` 아래에 조립되고 진입 파일은 그것을 import만 하므로, 사용자가 덧붙인 내용이 우리 것과 섞이지도, 함께 지워지지도 않는다. `uninstall`은 보안 조작이다 — 우리 것은 전부 사라지고, 가져간 것은 넘기거나 지울 수 있는 아카이브 하나로 나온다.
- **메타데이터는 고르고, 관측이 허가한다** — 무엇이 승격됐다는 기록은 되돌릴 수 없는 행위를 제안할 수는 있어도 허가할 수는 없다. 그 기록은 실행될 기계를 본 적이 없다. 승격된 learning의 개인 사본을 지울 때는 배포된 코퍼스에 대체물이 진짜 있는지 묻고, 지우려는 사본은 그 증거에서 제외하며, 조금이라도 애매하면 남긴다: 남은 중복은 잉여지만 잘못된 삭제는 데이터 손실이다.
- **배포물은 그것을 만든 행위보다 오래 산다** — 명령이 성공했다는 사실은 어느 버전이 안착했는지 말해주지 않는다. 캐시된 패키지는 exit 0으로 이전 버전을 내줄 수 있다. 그래서 배포된 상태가 자기 버전 마커를 품고, `status`는 실행된 소스가 아니라 그 마커를 읽는다. 마커가 없으면 답은 추측이 아니라 `unknown`이다.
- **`Evidence Base`(가이드별)가 숫자의 단일 소유자.** 실측은 `session-cost.py`로(설치된 패키지에서는 `agent-bios cost`).
- **영어가 정본이자 설치본, 한글(`ko/`)은 참고 전용.** 하네스는 파일명 고정 영어 파일만 로드하고, Restore는 영어만 설치한다.

## Layout

| 경로 | 역할 |
| --- | --- |
| `claude/CLAUDE.md`, `codex/AGENTS.md` | 전역 지침 (en) — 설치·로드 |
| `claude/guides/*.md`, `codex/guides/*.md` | scoped guides (en) — 설치 |
| `codex/agents/*.toml` | Codex custom subagent role 템플릿 — 설치 |
| `ko/**` | 위 모든 문서 + README·DEPENDENCIES의 한글 미러 (참고 전용) |
| `launch/` | launch profile, preflight TUI, 무인자 shell interception, managed Textual venv, 그리고 profile의 model binding을 지키는 prompting-target 검사 |
| `compose/` | corpus 분류와 선택별 조립 — domain manifest와 그 게이트, assembler, package identity, hook 등록, activation canary, 배포된 corpus 상태 |
| `learn/` | collection loop — capture, record schema와 validator, curation intake, promotion manifest, 재배포, secret-redaction floor |
| `session-distill/` | 여러 세션을 corpus 등급 항목으로 정제하는 heavy curator 파이프라인 |
| `wrappers/` | `$CODEX_HOME/bin/`에 배포하는 내부 Codex wrapper |
| `gates/` | author-side 검증 (미러 생성, parity, lexicon, payload, assembler 시나리오) — repo 체크아웃에서만 닿을 수 있고, npm payload에 들어가면 `check-package.sh`가 실패시킨다 |
| `ontology/` | 어떤 변경이 다른 무엇을 의무로 만드는지 — 엔티티, 의무 엣지, 서비스 라우트를 `check-ontology.py`가 실제 소스에 대조해 지킨다. `instances/graph.json`이 정본이고 `LEXICON.md`·RDF 뷰·HTML 맵·competency/extension 문서가 거기서 생성된다 |
| `install.sh`, `session-cost.py` | CLI와 비용 측정기 — 직접 실행하는 두 가지(설치 후에는 `agent-bios`와 `agent-bios cost`) |
| `decisions/` | 이 레포를 개발하며 내린 결정의 기록 — 무엇을 정했고 어떤 대안을 닫았는지. author-side라 배포되지 않는다 |
| `packages/` | 저작된 corpus 패키지. concept home이 아니라 패키지 정체성으로 조직된다 |
| `.githooks/` | 게이트를 인덱스에 대고 돌리는 pre-commit 훅. 클론마다 `core.hooksPath`로 한 번 켠다 |
| `design/`, `benchmarks/` | 설계 기록과 instruction-behavior 벤치마크 |
| `research/` | corpus 연구(12,749개 AGENTS.md/CLAUDE.md 분류): 보고서·스크립트·라벨링 기록; 벌크 데이터는 `.gitignore` 규칙으로 로컬에 남는다 |
| `DEPENDENCIES.md` | 외부 도구·host CLI·모델 provider + 검증 버전 |

`config.toml`, `settings.json`, `hooks.json`은 머신 종속(신뢰 목록, 훅 경로, 시크릿)이라 의도적으로 추적하지 않는다.

## Guides

| 가이드 | 내용 |
| --- | --- |
| `cli-multi-model-workflow` | 멀티모델 CLI 워크플로: Default Frame, role slot/tier, delegation mechanics, Codex CLI 직접 구동, 캐시 경제, 무인 배치 안전, halt/resume, handoff 계약, Environment Binding |
| `coding-staged-workflow` | 단계형 개발: 설계 → 프로세스 → 구현, review loop, severity 계약, verification menu, 정지 조건 |
| `llm-capability-boundary` (+ `-patterns`, `-examples`) | LLM/tool/code 권한 경계: field authority, accepted output channel, 구조적 강제, worked example |
| `mock-realization-boundary` | mock/fixture 실현과 제품 semantic path의 경계 |
| `svg-visualization-guide` | SVG 다이어그램·service blueprint 규격 |
| `implementation-map` | IMPLEMENTATION_MAP.html current-state dashboard |

## Edit workflow

1. 영어 정본(`claude/`)을 수정하고, 사용자에게 보이는 변경이면 한글 정본(`ko/claude/`)도 함께 수정한다.
2. `python3 gates/emit-mirrors.py` — 두 정본에서 `codex/`와 `ko/codex/`를 재생성한다. Codex 쪽은 절대 손으로 고치지 않는다: 생성된 투영이며, 생성기가 내놓는 것과 정확히 일치하지 않는 파일은 `--check`(파리티 게이트가 실행한다)가 실패시킨다.
3. `./gates/check-parity.sh` 통과 확인.
4. 커밋 후 Restore.

## Restore (배포)

### Private 설치와 셸 연결

일반 private 설치·업데이트는 전역 `AGENTS.md`·`CLAUDE.md`를 수정하지 않는다.
명시적인 `migrate`는 과거 agent-bios 관리 구간·import를 정리하며 사용자 작성
부분은 보존한다. 셸 연결의 복원·제거는 이 작업과 별개다.

```sh
agent-launch claude
agent-launch codex
agent-bios shell          # 연결 상태
agent-bios shell restore  # 인자 없는 claude/codex를 TUI에 연결
agent-bios shell remove   # 원본 CLI로 복귀
```

TUI 첫 화면의 **셸 연결**에서도 **연결 복원 / 연결 제거**를 선택하고 확인할 수
있다. 복원은 기존 파일을 백업하고 `${ZDOTDIR:-$HOME}/.zshrc`에 관리 구간을
추가한다. 새 터미널을 열거나 `.zshrc`를 source하면 적용된다. 인자가 있거나
비대화형인 호출에는 권한 옵션을 추가하지 않고 원본 CLI로 전달한다. 제거는
다른 셸 설정을 보존하며, 이미 열린 셸의 관리 래퍼도 다음 명령에서 해제된다.
관리 구간·스크립트를 사용자가 편집했다면 덮어쓰지 않고 확인을 요청한다.
업데이트는 연결을 유지하고, 초기화와 제거는 연결을 해제한다. 이 기능은 전역
지침 파일과 corpus 내용을 수정하지 않는다. 두 명령의 `--dry-run`과 런처의
`--dry-run`에서는 셸 변경을 미리보기만 한다.

### 호환 설치 참고

현재 기본 설치와 세션 활성화는 [영문 설치 안내](../README.md#install-and-activate)를
따른다. 아래 수동 전역 복사는 호환 방식의 참고용이며 private 설치가 아니다.
호환 설치기는 이전 manifest에만 있고 소유권이 확인되지 않는 guide 경로를 지우지
않고 수동 확인 대상으로 알린다. 새 소유 목록에서도 제외하므로 이후 uninstall이
그 파일을 삭제하지 않는다. 기본 private 설치는 자체 inventory를 사용한다.

**모든 활성 환경에서 한 자리에서** 배포한다 — 부분 배포는 공유 전역이 일부 환경에 없는 가이드를 가리키게 만든다. 글로벌은 영어만. Claude 환경들은 `CLAUDE.md`를 심링크로 공유할 수 있으나 `guides/`는 독립이다.

```bash
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
mkdir -p "$CLAUDE_DIR"
cp claude/CLAUDE.md "$CLAUDE_DIR/CLAUDE.md"
mkdir -p "$CLAUDE_DIR/guides"; cp -R claude/guides/. "$CLAUDE_DIR/guides/"

CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_DIR"
cp codex/AGENTS.md "$CODEX_DIR/AGENTS.md"
mkdir -p "$CODEX_DIR/guides"; cp -R codex/guides/. "$CODEX_DIR/guides/"
mkdir -p "$CODEX_DIR/agents"; cp codex/agents/*.toml "$CODEX_DIR/agents/"
mkdir -p "$CODEX_DIR/bin"
cp wrappers/codex-run.sh "$CODEX_DIR/bin/codex-run"
cp wrappers/codex-helm.sh "$CODEX_DIR/bin/codex-helm"
chmod +x "$CODEX_DIR/bin/codex-run" "$CODEX_DIR/bin/codex-helm"

LAUNCH_DIR="$HOME/.config/agent-launch"
mkdir -p "$LAUNCH_DIR" "$HOME/.local/bin"
cp launch/agent-launch.toml "$LAUNCH_DIR/profiles.toml"
cp launch/agent-launch.zsh "$LAUNCH_DIR/shell.zsh"
cp launch/agent-launch.py "$HOME/.local/bin/agent-launch"
chmod +x "$HOME/.local/bin/agent-launch"
bash launch/provision-venv.sh   # rich preflight용 managed Textual venv; 생략 시 numbered fallback
grep -qxF '[ -r "$HOME/.config/agent-launch/shell.zsh" ] && source "$HOME/.config/agent-launch/shell.zsh"' "$HOME/.zshrc" || \
  printf '%s\n' '[ -r "$HOME/.config/agent-launch/shell.zsh" ] && source "$HOME/.config/agent-launch/shell.zsh"' >> "$HOME/.zshrc"
```

TTY에서 인자 없는 `codex` 또는 `claude`는 launch preflight를 연다. 화살표 키 TUI의 모든 선택 화면은 상단 고정 영역에 현재 전체 설정을 계속 보여주고, 그 아래에 강조된 옵션의 설명과 선택지 목록을 순서대로 배치한다. 위/아래 화살표로 이동하고 Enter로 선택하며, Esc는 이전 메뉴로 돌아가고 `q`는 취소한다. Preset root의 Esc도 취소로 동작한다. 각 tier의 model은 host에 설정된 catalog에서 고르거나 **Other**로 backend가 받는 임의의 model id를 직접 입력한다. 그 text 입력은 `q`로 시작하는 값도 보존해야 하므로 여기서는 Esc 또는 Ctrl-C가 즉시 취소이고, `q`를 입력해 Enter로 제출해도 취소된다. Textual preflight는 terminal 크기에 맞춰 reflow하므로 고정 최소 geometry가 없다. 모드 아래 두 항목은 실행이 아니라 설치 자체를 다룬다. **코퍼스 패키지**는 선택 도메인 패키지 체크리스트를 열고(core + infra는 항상 설치), Apply하면 체크된 집합 그대로를 `agent-bios onboard --domains`에 넘긴다 — 배포·활성화 카나리·결과 기록은 설치기만 수행하며, 상태 패널이 그 결과를 보고하고 실패한 apply는 크게 표시한다. **언어**는 인터페이스 텍스트를 English·한국어·日本語 사이에서 바꾸고 사용자 소유 `launcher.local.toml`에 저장한다. 바뀌는 것은 런처 화면뿐이며, 모델이 소비하는 코퍼스는 영어로 통일되어 있다. Preset을 고르거나 **Custom**에서 main tier, review setup, host별 실행 정책, 각 tier binding을 편집하는 지속형 설정 허브를 연다. 모든 편집은 이 허브로 돌아오며, **Start with these settings**가 최종 실행 확인이고, **Save these settings globally and start**는 설정을 명명된 preset(host-scoped tier override 포함)으로 user config에 저장해 다른 곳에서도 재사용하게 한 뒤 실행하며, **Exit without launching**은 실행을 취소한다. rich preflight는 managed virtualenv(`launch/provision-venv.sh`, `~/.local/share/agent-launch/venv`)에서 실행되며 launcher가 인터랙티브 경로에서 이 venv로 re-exec한다. 이 venv가 없거나 비대화형 호출이거나 `TERM`이 `dumb`/미설정이면 numbered prompt로 fallback하며 이때 `b`가 뒤로가기 명령이다. Launcher는 호출 환경의 `PATH`에서 backend command를 해석하며 shell function으로 재진입하지 않는다. Codex child binding은 user cache의 session-selected agent config로 materialize하고, Claude에는 delegation이 켜졌을 때 model과 effort를 `--agents` JSON으로 전달한다. Review는 기본적으로 cross-family로 실행된다(`review_family`, 기본 `cross`; `same`은 기존 동일계열 projection 복원). main tier가 한 model family이므로 dispatch 가능한 native·deep 두 review route 모두 반대 계열에서 돈다. 예외는 host 자체의 내장 review 명령인 `slash-review`다(Claude는 `/code-review`, 깊은 multi-agent pass는 `ultra`; Codex는 `/review`). 의존성이 없어 항상 해석되지만 main 자신의 명령이라 cross-family로 dispatch할 수 없으므로 `cross`에서는 동일계열 floor로 돌고 그 verdict는 PROPOSED로 라벨한다. Claude main은 gpt/codex review를 dispatch하고(native는 `$CODEX_HOME/bin`에서 해석한 `codex-run` reviewer wrapper, deep은 plain `codex exec -m <frontier model> -c model_reasoning_effort="ultra"` — self-contained packet을 stdin으로 전달하며, `-c service_tier="fast"`는 더 빠르고 얕은 명시적 opt-in), Codex main은 Anthropic/Claude review를 dispatch한다(native는 `claude -p --permission-mode plan`, deep은 prompt에 keyword `ultracode`를 담은 헤드리스 `claude` CLI — 그 keyword가 해당 턴에 Claude Code의 dynamic workflow를 연다). 구체적인 reviewer 명령·해석된 절대경로·반대 계열 tier binding은 세션 시작 시 주입되는 contract에 명시된다. 어느 CLI도 상대 계열을 native subagent로 띄우지 못하므로 cross-family reviewer는 read-only subprocess로 dispatch되며 CLI-native subagent가 아니다. cross-family route가 launch 시점에 없거나 사용 시점에 미인증이면 launch를 막지 않고 동일계열 native subagent review로 degrade하며 그 verdict는 PROPOSED(family collapse)로 라벨한다. cross-family route도 없고 동일계열 fallback도 없는(delegation off) non-none review 요청만 fail-closed로 유지한다. 이 런처가 한 번도 본 적 없는 reviewer는 사용자가 직접 추가한다: review 편집기의 **Register another reviewer…**가 method descriptor에 필요한 것을 묻고, 한 바이트를 쓰기 전에 실제 config reader로 후보를 검증한 뒤 config 옆 `review-methods.local.toml`에 append한다. 이 파일은 설치기가 배포·검증·덮어쓰기를 하지 않으며, 그 항목은 shipped 항목과 정확히 같은 검증을 받고 shipped method 이름을 가릴 수 없다. 거부되면 reader의 메시지를 그대로 보여주고 파일은 바이트 하나 바뀌지 않는다. Review setup은 configured/requested 상태이며 launcher가 실제 review 완료까지 보장하지 않는다. Ultrawork처럼 통합되지 않은 runtime은 선택지에 내놓지 않는다.

Shell wrapper 경계에서는 인자가 있는 모든 명령(`codex exec ...`, `claude -p ...`)과 모든 non-TTY 호출이 launch-profile projection을 건너뛰고 caller argument를 보존한다. Claude 직접 경로는 wrapper 기본값인 `--dangerously-skip-permissions`를 의도적으로 유지한다. `codex --no-tui ...` / `claude --no-tui ...`는 이 직접 경로를 명시적으로 사용하고, `AGENT_LAUNCH_TUI=0`은 해당 process tree에서 무인자 TUI interception을 끈다.

`agent-launch` 직접 호출은 backend command와 기본 argument를 해석하기 위해 유효한 profile을 계속 요구한다. `--preset`, `--custom`, `--dry-run` 중 하나를 쓰면 non-TTY 또는 `--no-tui`와 함께 사용해도 configured-launch 경로를 사용한다. Non-TTY의 bare `--dry-run`은 Balanced를 결정적으로 선택하며, 해당 preset이 없는 custom profile은 `--preset NAME`을 명시해야 한다. 전달한 backend argument는 projected default 뒤에 그대로 붙지만, projected option(seat·contract·delegation·policy)을 덮어쓰는 것은 launch 시점에 거부되어 contract가 실제 실행을 계속 서술하며, argument가 있으면 summary가 이를 공개한다. 스크립트에서는 `$HOME/.local/bin/agent-launch --preset NAME --yes HOST -- ...`를 호출하거나 `$HOME/.local/bin`을 `PATH`에 추가한다. Summary는 stderr로 보내 backend stdout을 machine-consumable하게 보존한다.

`$CODEX_DIR/bin`을 `PATH`에 추가하거나 wrapper를 절대 경로로 호출한다. `codex-helm`은 local CLI 기본을 따라 HELM main을 `--dangerously-bypass-approvals-and-sandbox`로 시작하며, `--sandbox MODE`를 명시하면 flag 순서와 무관하게 그 run의 bypass를 끈다. `AGENTS.md`는 delegation gate가 발동할 때 root/main local Codex session에 상시 ordinary-subagent authorization을 준다. Non-Ultra HELM main은 native multi-agent를 기본 off로 설정하고 HELM에게 tier dispatch를 내부 `codex-run` adapter로 보내도록 지시하며, adapter를 사용한 실행에서는 선택한 model, effort, sandbox가 pin된다; native multi-agent 기본값은 HELM main 자체가 명시적 Ultra일 때만 on이다. FRONTIER는 항상 read-only인 별도 `gpt-5.6-sol` root로 실행하도록 지시하며 기본 max, 실제로 나눌 수 있는 복합 작업은 Ultra, 비용·latency가 우선이면 지원되는 더 낮은 effort다. HELM main에 bypass authority와 임의 expert `-c`를 의도적으로 허용하므로 이 dispatch route는 security boundary가 아니라 instruction-backed, live-E2E-verified default다. `codex-run`은 사용자에게 공개하는 policy boundary가 아니라 저수준 내부 adapter로 둔다. 두 wrapper 모두 `-c key=value`를 expert override로 받으며, 이 override는 단일 실행의 wrapper 기본값을 의도적으로 바꿀 수 있다.

배포 후 게이트: 배포된 전역이 참조하는 모든 `guides/*.md`가 그 환경 `guides/`에 존재하고, 필수 agent 파일 `frontier.toml`, `workhorse.toml`, `sweep.toml`, `reviewer.toml`이 `$CODEX_DIR/agents/` 아래에 있으며 TOML로 parse되고, `frontier.toml`은 per-spawn effort를 받는 native surface를 위해 의도적으로 `model_reasoning_effort`를 생략하며, `DEPENDENCIES.md`의 각 필수 `codex exec --help` flag가 존재하며, `$CODEX_DIR/bin/codex-helm --dry-run --mode review "probe"`가 credential-free assembly check로 성공해야 한다(실제 Codex 호출 아님). Restore는 각 가이드 `Environment Binding`을 덮어쓴다 — 환경별 바인딩 수정은 레포 사본이나 untracked 파일에 둔다.

## 다른 환경이 가져갈 때

규칙 계층은 그대로 둔다. 교체 체크리스트: 각 가이드 `Environment Binding`(`(private)`은 원작성자 예시); 전역 파일의 응답 언어 선호와 "설계" design-trigger 단어; `DEPENDENCIES.md`에 등재된 skill/MCP 이름(`spreadsheet-processing` skill, review MCP). 그런 뒤 `Evidence Base` 수치를 자기 환경에서 재측정 후 조정한다.

## Scope

안정된 설정, 설정으로 관리하는 자격증명, 전역 에이전트 지침만. 런타임 상태·로그·세션·캐시·생성 아티팩트·임시 경로는 넣지 않는다.

## 세션별 공통 hook

`agent-launch --corpus-native`는 선택한 corpus hook을 해당 Claude 또는 Codex
세션에만 전달한다. 기본값은 꺼짐이다. 두 호스트가 같은 Python 본문과
`event`/`matcher`를 사용하며, 대상 호스트가 지원하지 않는 이벤트는 실행 불가로
표시한다. Claude는 항목별 plugin, Codex는 세션별 `-c hooks.<Event>=...` 설정을
사용한다. 기존 사용자·프로젝트 hook은 유지하고 전역 hook 설정은 추가하지 않는다.
Codex의 활성화 설정과 신뢰 검토는 그대로 적용된다. 새 정의나 바뀐 정의는 해당
세션의 `/hooks`에서 검토해야 한다. 설정 발견과 실제 실행은 별도로 검증한다.

`agent-bios corpus snapshot --host codex --native --json` 또는 `--host claude`로
미리 볼 수 있다. 기존 세션 재개는 그 세션에 고정된 hook을 유지한다. Corpus agent의
Claude frontmatter를 Codex agent 설정으로 옮기는 작업은 별도이며, 이 차이가 공통
hook 실행을 막지는 않는다.
