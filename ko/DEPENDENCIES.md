# Dependencies

의존성 종류, 필요한 기능, 검증된 실행 환경의 정본은
[영문 DEPENDENCIES.md](../DEPENDENCIES.md)다. 이 문서는 요구사항과 사용 범위를
번역하며, 설치된 버전과 검증 날짜는 영문 정본을 참조한다. `--version` 확인,
패키지 설치, native 프로토콜 검사, 실제 모델 실행은 서로 다른 검증이다.

Textual root pin과 선택적 학습 validator pin은 `launch/provision-venv.sh`가
소유한다. `gates/build-ui-runtime.py`는 `TEXTUAL_PIN`에서 정확한 wheel 묶음을
만들어 `compose/ui_runtime/manifest.json`에 기록한다. Setup은 이 inventory와
선택적 validator pin을 읽는다.
최소 요구 버전은 `package.json`과 runtime 검사 코드가 정하며,
모델·역할 바인딩은 가이드의 `Environment Binding`과 launch profile,
실측값은 `Evidence Base`가 소유한다.

## Runtime tools

지원 운영체제는 `package.json`에 선언된 macOS와 Linux다. Private transaction,
지침 capture와 앱 등록은 POSIX file lock·descriptor·symlink를 사용한다.
JSON setup 프로토콜, 비대화형 지침 작업, import, 앱 context는 Python 표준
라이브러리로 동작한다.
대화형 설치 UI, 패키지·현재 checkout의 Instructions Studio, private·현재 checkout
런처의 rich CLI는 함께 배포하는 오프라인 의존성을 사용한다. 선택적 학습 검증과
남아 있는 호환 client의 managed 환경 요구사항은 별도로 구분한다.

| 도구 | 사용 경로 | 필요한 기능 | 검증 버전 |
| --- | --- | --- | --- |
| `python3` | `compose/instructions*.py`, 앱 helper, 비용 측정, launcher | Python 3.11+의 `tomllib`과 표준 라이브러리. `jsonschema`·Textual은 각각의 선택 경로에서 요구한다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `bash` | `install.sh`, shell adapter, provisioner, 앱 helper | 배열과 인자 보존 실행; macOS system Bash 지원 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `git` | 대화 설치의 소스 확보, clone 업데이트와 버전 관리 | 커밋을 고정하는 clone과 detached checkout; 개발에는 worktree와 revision 연산. 설치된 npm 패키지 사용에는 checkout이 필요 없다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `zsh` | `launch/agent-launch.zsh`, 선택적 shell connection | private 환경에서 명시적으로 연결한 셸과 호환 설치에 사용한다. 일반 private 저장·앱 context 사용에는 필요 없다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `mktemp`, `cp` | wrapper의 임시 환경과 shell 도구 | BSD 또는 GNU 명령 인터페이스 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `ioreg`, `ps` | macOS 대화형 setup의 머신·프로세스 식별 | 로컬 OS 정보를 확인한다. Linux는 machine-id와 `/proc`를 쓴다. 머신 식별에는 host/filesystem 대체 경로가 있으며 프로세스 근거가 없으면 실행 중인 시도를 확정하지 않는다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| Node.js | npm 배포, 선택한 npm 호스트 설치, 정적 slide job | 패키지 배포의 engine은 Node >=18, Claude npm 설치 경로는 Node >=22를 요구한다. Python 지침 runtime에는 필요 없다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `npm` | 패키지·선택 호스트 설치 | 사용자 prefix·registry 설정을 따르는 설치 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| Homebrew | setup의 선택 설치 명령 | 로컬 버전 검사가 성공한 manager의 formula/cask 설치; Homebrew 자체는 자동 설치하지 않는다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| Python `venv`, `ensurepip`, pip | 명시적으로 선택한 managed 환경 설치 | `AGENT_LAUNCH_PYTHON`으로 환경 생성. 설치 UI 번들을 여는 데는 필요 없다. 일부 Linux 배포판은 별도 구성요소 설치가 필요하다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| 번들 Textual UI | 대화형 설치, 패키지·현재 checkout의 Instructions Studio TTY, private·현재 checkout의 rich 런처 | `compose/ui_runtime/`의 pure-Python wheel을 검증하고 임시로 사용한다. system·managed Textual, pip 설치, 실행 중 네트워크 접근은 필요 없다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| Managed Textual | 단독 호환 런처, 프로세스 내부 API, 저작 테스트 | 선택적인 `AGENT_LAUNCH_VENV` 환경. Pin은 `TEXTUAL_PIN`이며 현재 패키지 CLI UI는 번들을 사용한다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| Rich | Textual 클라이언트 | 설치 UI 번들에 포함되며 다른 경로에서는 Textual이 가져오는 의존성이다. 별도 setup 선택이나 선택적 구문 강조 패키지가 필요하지 않다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |
| `jsonschema` | 사용자 `learn` 수집과 저작 검증 | Draft 2020-12 validator. 사용 가능한 system validator가 없으면 configured managed Python으로 실행한다. `JSONSCHEMA_PIN`과 `--learning-only` 경로가 설치를 소유한다 | [영문 runtime 정본](../DEPENDENCIES.md#runtime-tools) |

`install`과 `onboard`는 `--non-interactive`를 명시하지 않으면 대화형이다.
선택 옵션은 UI 초기값이며, non-TTY 기본 호출은 쓰기 전에 실패한다. Python 3.11+는
필요하다. `compose/instructions_ui_runtime.py`는 번들을 검증해 프로세스 전용 임시
디렉터리에 풀고 정상 종료 시 정리한다. 런처는 backend `execve` 직전에도 정리한다.
영구적인 UI 패키지 설치는 만들지 않는다. 패키지 UI의 번들이 없거나 손상되면
복구·재설치를 안내하며, 설치는 번호형 화면으로 전환하지 않는다. 단독 호환 런처는
managed·번호형 경로를 유지한다. 프로세스 내부 API의 의존성 계약도 유지하며,
번들 활성화는 실제 CLI 진입점에서 명시적으로 수행한다.

터미널 설치의 언어 선택과 영어·한국어·일본어 메시지는
`compose/instructions_setup_i18n.py`가 소유한다. 의존성 검사 전에 고르는 이번 실행의
UI 언어이며 지침 언어나 저장되는 호스트 설정을 바꾸지 않는다. Locale은 초기
제안만 정하고 실제 선택 화면은 항상 표시한다. JSON setup 프로토콜은 검토 언어를
명시적으로 받으며, 정해진 필드 이름과 정확한 값은 유지한다.

`agent-bios setup`은 Python 3.11+와 Bash가 필요하며 TTY, Textual, 모델 SDK나
새 서버를 요구하지 않는다. 검사·검토 계획·고정된 의존성 설치 명령에는 같은
`SetupController`를 사용한다. 명시적인 Apply만 선택한 작업을 실행하고 private
상태에 영구 receipt를 남긴다. `status`와 `resume`은 설치 작업을 실행하지 않고
상태를 확인하거나 추가 검토를 준비한다. 대화 client에는 호스트의 일반 파일·
명령 도구가 필요하다. `INSTALL.md`는 저장소 링크 요청에서 사용자가 지정한 로컬
소스나 내려받을 커밋 하나를 확정하고 `compose/setup/START.md`로 연결한다.
호스트의 다운로드 또는 Git 도구로 소스를 확보하며 설치 계획을 만들기 전에
호출자가 관리하는 파일을 생성한다. 이 작업은 setup Apply와 별개다. 소스를 사용하는
대화 설치에는 사전 bridge, Codex CLI, Node.js나 npm이 필요 없다.

Setup의 로컬 검사는 패키지를 설치하거나 로그인하지 않는다. 실제 설치 명령은
고정된 argv로 미리 보여주며 선택과 Apply 이후 실행한다. 앱 bridge는 나중의
학습 호출을 위해 설정된 managed 환경 경로를 보존한다. 로그인, MCP 인증,
브라우저·job 환경, 개인 skill은 별도다. 선택 기능이 없어도 로컬 지침 저장소는
사용할 수 있다. Manager 버전 검사가 성공해야 설치 recipe를 제안한다. 새 managed
환경을 만들 때는 선택한 Python의 venv/ensurepip가 필요하며, 이미 있는 managed
interpreter는 다시 bootstrap할 필요가 없다. Provisioner는 환경을 바꾸기 전에
Python 3.11+를 확인한다.

## Host agent CLIs

| CLI | 역할과 요구 기능 | 검증 버전·범위 |
| --- | --- | --- |
| Claude Code | native 세션·worker·review. 모델·effort·agent 설정, 세션별 prompt 추가, session id·resume, MCP 설정, plugin과 선택 권한 모드를 사용한다. 전역·프로젝트 지침은 native 규칙으로 읽는다 | [영문 호스트 정본](../DEPENDENCIES.md#host-agent-clis) |
| Codex CLI | native adapter와 Codex worker/review. cwd를 반영한 `config/read`, `thread/start`·`thread/inject_items`·`thread/read`, resume·exec·세션 config를 사용한다 | [영문 호스트 정본](../DEPENDENCIES.md#host-agent-clis) |

Claude의 선택적 전역 지침 제외는 `compose/instructions_session.py`가 검사하는
지원 최소 버전을 요구한다. `claudeMdExcludes`를 하나의 `--settings` 인자로
전달하며 기존 인자와 충돌하면 거부한다. Codex의 현재 adapter에는 지원되는
전역 지침만 제외하는 기능이 없으며, 대신 sandbox나 config home을 바꾸지 않는다.

설치된 CLI 버전, 분리된 최신 호환성 검사, 과거 기능별 실행 관측은
[영문 검증 범위](../DEPENDENCIES.md#host-agent-clis)에서 구분한다.
버전·parser·discovery 확인만으로 hook 실행, instructions-agent 실행, 모델 응답이나
인증된 resume까지 검증되었다고 보지 않는다. SWEEP의 도구·effort 선택은
현재 launch binding을 따른다.

## Codex 앱과 지침 import

Codex 데스크톱 앱은 CLI와 별도 호스트다. 선택 bridge에는
`~/.agents/skills/agent-bios` 검색, `compose/app_bridge/agents/openai.yaml`의 명시적
호출 정책, Python과 `/bin/bash`가 필요하다. 현재 작업은 `CODEX_THREAD_ID`로
식별하며 없으면 실제 `--session` id를 명시한다. Helper는 매 호출마다 확인된
private 설치와 저장된 root를 사용한다. 로컬 등록·receipt 테스트만으로 최소
앱 버전이나 실제 앱 검색·모델 읽기를 입증하지는 않는다.

명시적인 설치 요청에는 bridge의 `setup` 전달 경로를 사용할 수 있다.
`setup start`가 설치 안내의 위치를 반환한다. 이 경로는 작업 ID를 요구하거나
`session use`를 실행하지 않는다. Native 작업 ID는 작업 context receipt에만
필요하며, 설치 검토·Apply는 머신·사용자·경로·패키지·작업 디렉터리와 실행에
영향을 주는 환경을 연결한다. Status receipt는 시도의 기록이며 `handoff`는
패키지·runtime 검증과 helper 등록·무결성·사용 가능 여부를 따로 보고한다.
`compose/instructions_transaction.py`의 읽기 전용 `try_transaction_lock`은 다른 쓰기
작업을 기다리거나 잠금 상태를 새로 만들지 않는다. 안전하게 잠금을 얻을 수 없으면
handoff는 `verification: "deferred"`, 관측하지 못한 필드는 `null`로 반환한다.
Status는 이때도 기록된 진행 상황을 반환한다. `verification: "checked"`는 검사를
실행했다는 뜻이며 각각의 결과는 별도로 확인한다.
`helper_usable`이 참이면 `helper_argv`, `package_verified`가 참이면 `setup_argv`를
반환된 environment와 함께 사용할 수 있다. Native skill 검색을 입증하는 값은
아니다. 엔진은 호스트의 파일·명령 도구를 설치하거나 설정하지 않는다.

`app session preview/use/off/status`는 새 CLI 세션 대신 현재 작업에 반환하는
context를 관리한다. 별도의 Codex CLI subprocess, Textual, model SDK가 필요하지
않다. Instructions Studio는 터미널에서 열며 rich UI는 선택 사항이다. 각 작업에서
명시적으로 사용해야 하며 hook·agent를 자동 활성화하지 않는다. Off는 이미 반환한
본문을 회수하지 못한다. 앱 등록은 기본으로 꺼져 있고 자기 discovery link만
소유하며 전역 지침과 다른 도구의 항목을 보존한다.

로컬 지침 import에는 model SDK나 별도 parser framework가 필요 없다.
알려진 전역 경로와 명시한 프로젝트 root의 정해진 파일명을 확인하고,
`learn/redact.py`로 마스킹한 증거를 저장한다. 코드는 source digest, 줄 단위 근거,
프로젝트·호스트 범위와 transaction을 검사한다. 본문·소비방식·trigger 설명은
호스트 에이전트가 작성하며, 의미를 자동 분류하는 코드가 아니다. Plan/apply에는
설치된 baseline이 필요하다. 원본 파일은 보존되며 native 호스트가 별도로 계속
읽을 수 있다.

## Private 지침 assets

- **Native 지침 hook·agent**는 명시적 `--instructions-native`와 지원되는 설치 carrier를
  요구한다. Claude agent는 항목별 plugin에서 원본 frontmatter와 제한을 유지하며
  plugin으로 한정된 이름을 쓴다. Codex agent 의미 변환은 별도 작업이다.
- **Codex 역할 템플릿**은 `codex/agents/*.toml`에서 private release로 전달한다.
  기본 설치가 사용자 native home에 같은 파일을 복사할 필요는 없다.
- **관리 bootstrap**과 선택된 requested 절차는 private snapshot 자원이다.
  **No-instructions 모드는 bootstrap과 지침 지침 본문을 제외한다.** 앱 discovery
  bridge는 별도이며 등록만으로 작업 context를 선택하지 않는다.

## 모델과 선택적 연동

구체 role/model 바인딩은 가이드 `Environment Binding`과 launch profile을 따른다.
공급자는 Anthropic·OpenAI이며 인증은 host login이 제공한다. 의존성 검사로
사용자 계정을 추측하거나 인증정보를 설치하지 않는다.

- **정적 HTML/PDF slide companion** — Python은 준비와 접수, Node·Playwright·
  `pdf-lib`·Chromium 계열 browser는 명시한 렌더 job에 사용한다. Instructions 배포가
  설치하지 않는다. Job 검증 버전은 [영문 정본](../DEPENDENCIES.md#models-and-optional-integrations)을 따른다.
- **Deep review** — 추가 core 도구 대신 선택된 host CLI를 사용한다. Codex는
  read-only exec와 독립적인 packet을 사용한다. Claude는 헤드리스로 실행하며
  프롬프트에 `ultracode` 키워드를 넣어 workflow를 활성화한다.
  모델과 effort는 launch binding을 따른다. Hermetic adapter를 선택하지 않았다면
  native 설정을 상속한다. 개인 reviewer는 `review-methods.local.toml`에 등록한다.
- **Cross-family adapter** — private 패키지의 `wrappers/codex-run.sh`,
  `codex-helm.sh`, `claude-run.sh`에서 찾는다. 실제 경로·binding·도달 범위·fallback은
  launch contract를 따른다. 사용 불가나 미인증을 완료된 review로 계산하지 않는다.
- **MCP 서버** — 사용자가 선택한 `mcp-stdio-v1` capability에 한해 launcher가
  등록한다. Shipped review method와 앱 context 전달은 MCP 서버를 추가로 요구하지 않는다.
- **spreadsheet-processing** — 선택된 spreadsheet 규칙이 참조하는 선택 skill이다.
  없으면 일반 도구·코드와 실제 spreadsheet engine 검증이라는 inline fallback을 따른다.

Host 설정과 인증정보는 추적하지 않는 사용자 상태다. `launch/agent-launch.toml`은
secret 없이 launch binding을 담는다.

## Re-verify

아래 로컬 inventory는 패키지 설치나 모델 실행 없이 현재 상태를 읽는다.

```bash
python3 -B - <<'PY'
import json, os, pathlib, sys
repo = pathlib.Path.cwd()
sys.path.insert(0, str(repo / 'compose'))
from instructions_setup import dependency_inventory
for row in dependency_inventory(repo, {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}):
    print(json.dumps({key: row[key] for key in ('id', 'status', 'version', 'path', 'manual_reason')}, ensure_ascii=False))
PY
bash install.sh verify
bash install.sh instructions status --json
bash install.sh app status --json
```

패키지 설치와 저작 gate는 위 검사와 분리한다. 패키지 CLI UI를 여는 데 아래
provisioner는 필요하지 않다. 학습 검증, 호환 client, 저작 환경에 명시적으로 설치할 때
`bash launch/provision-venv.sh` 또는 `--learning-only`를 사용한다. 이 명령은
설정된 package index에 접근하고 managed 환경을 바꿀 수 있다. 저작 gate도
테스트 환경을 준비할 수 있으므로 읽기 전용 inventory가 아니다.
검사 명령은 [영문 Re-verify](../DEPENDENCIES.md#re-verify)를 따른다.

`python3 gates/build-ui-runtime.py --check`와 `--self-test`는 오프라인에서 번들과
격리된 import·화면·정리를 검증한다. 명시적인 `--build`만 패키지를 가져온다.
Wheel과 manifest는 직접 편집하지 않고 builder로 생성한다.

## Ownership

| 소유처 | 소유 대상 |
| --- | --- |
| 영문 `DEPENDENCIES.md` | 요구 기능과 범위가 명시된 버전 관측의 정본 |
| `launch/provision-venv.sh` | Textual root pin, validator pin, 명시적 managed 설치 |
| `gates/build-ui-runtime.py` | 저작용 번들 생성과 오프라인 검사·대조군 |
| `gates/workenv/check-workenv.py` | `RUFF_PIN`(저작용 정적 분석 도구의 정확한 버전과 규칙 집합), 단위 테스트 leg가 요구하는 Python 최소 버전. `ruff`가 없거나 버전이 다르면 umbrella가 이름을 밝혀 실패하며, 아무것도 설치하지 않는다 |
| `compose/ui_runtime/manifest.json` | 생성된 wheel 목록, 버전, hash와 license |
| `compose/instructions_ui_runtime.py` | 오프라인 검증, 임시 추출, 프로세스 종료·인계 전 정리 |
| `compose/instructions_setup.py` | 공통 SetupController, 로컬 inventory, 검토한 설치 recipe |
| `package.json`과 runtime validator | 지원 플랫폼과 최소 요구 버전 |
| 가이드 `Environment Binding`·launch profile | 역할·모델 바인딩과 기능별 host 근거 |
| 가이드 `Evidence Base` | 행동 실측과 숫자 기본값 |
