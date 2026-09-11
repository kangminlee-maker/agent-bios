# Dependencies

agent-bios의 스크립트·규칙이 의존하는 것을 요구 capability와 검증 버전으로 정리한다. role-slot→model 바인딩은 각 가이드 `Environment Binding`이, 숫자 기본값은 각 가이드 `Evidence Base`가 소유한다. 이 문서는 그것들을 재기술하지 않고 의존성 *종류*를 인벤토리화하며 소유 위치를 가리킨다 — 버전이 한 곳에만 있게.

영문 정본: [`../DEPENDENCIES.md`](../DEPENDENCIES.md). 날짜 = 검증 시점; 버전 재확인 시 날짜를 갱신한다.

## Runtime tools (scripts) — 이 문서가 소유

| Tool | Required by | Required capability | Verified |
| --- | --- | --- | --- |
| `codex` (codex-cli) | `wrappers/codex-run.sh`, `wrappers/codex-helm.sh`, `launch/agent-launch.py`; guide "Codex direct-drive"·"Session relocation" 바인딩 | 기존 `codex exec` 계약과 `agents.<name>.description/config_file` config projection; final output은 stdout, progress는 stderr; `CODEX_HOME` 존중; `codex resume` cwd-filtered | 0.144.1 · 2026-07-13 |
| `bash` | `install.sh`, `*/*.sh` | POSIX + 배열; macOS 시스템 bash에서 동작 | 3.2.57 · 2026-07 |
| `python3` | `session-cost.py`, `launch/agent-launch.py` | 모든 direct / 비-TTY / numbered 경로는 표준 라이브러리만; Python 3.11+ (`tomllib`). 인터랙티브 preflight는 추가로 `textual`(아래 행) 필요 | 3.14.5 · 2026-07-13 |
| `textual` (managed venv) | `launch/agent-launch.py` 인터랙티브 preflight; `launch/provision-venv.sh`가 프로비저닝 | `~/.local/share/agent-launch/venv`(재정의: `AGENT_LAUNCH_VENV`)의 Textual TUI framework. launcher가 인터랙티브 TTY 경로에서만 이 venv로 re-exec한다. venv 부재/손상, 비-TTY, `TERM` `dumb`/미설정이면 numbered prompt로 fallback하며 절대 막지 않는다 | 8.2.8 · py 3.14.5 · 2026-07-13 |
| `jsonschema` (system python) | `learn/check-learning.py` (learning record 게이트; `gates/check-parity.sh`에서 체인 실행) | `learn/learning.schema.json`을 SSOT 그대로 실행하는 JSON Schema Draft 2020-12 validator | 4.26.0 · 2026-07-20 |
| `zsh` | `launch/agent-launch.zsh`, `launch/shell_integration.py` | 선택적 private 셸 연결과 legacy 호환 경로: function, TTY 검사, 인자 보존 dispatch. 기본 private 설치는 셸 연결을 켜지 않는다 | 5.9 · 2026-07-13 |
| `git` | scripts·workflow (`origin/<base>..HEAD`, worktree) | 최근 git; worktree 지원 | 2.50.1 · 2026-07 |
| coreutils (`mktemp`, `cp`) | `codex-run.sh` hermetic home; `codex-helm.sh` managed home | BSD 또는 GNU | 2026-07 |

## Host agent CLIs

| CLI | Role | Required capability | Version 소유 |
| --- | --- | --- | --- |
| Claude Code | primary host; `CLAUDE.md` + `guides/` 로드; `agent-launch` backend | `--model`; effort `low/medium/high/xhigh/max`; per-agent `model`/`effort`를 담는 `--agents` JSON; `--append-system-prompt`; `--mcp-config`; permission mode `acceptEdits/auto/bypassPermissions/manual/dontAsk/plan` | Environment Binding (v2.1.207) |
| Codex CLI | mirror host; `AGENTS.md` + `guides/` 로드; worker/reviewer 런타임 | 위 codex 행 참조 | Environment Binding + 이 문서 |

## LLM models & providers — `Environment Binding`이 소유

구체 role-slot→model 바인딩은 각 가이드 `Environment Binding`에만 있고 날짜·만료(~8주 또는 신규 모델 관측 시)를 가진다. 여기서 재기술하지 않는다.

- Providers: **Anthropic** (Claude — Fable/Opus/Sonnet/Haiku), **OpenAI** (GPT / Codex).
- Auth: Anthropic는 Claude Code 로그인; OpenAI는 ChatGPT 구독 또는 API key (`$CODEX_HOME/auth.json`).

## Deployed Codex assets

- **Codex custom agents** (`codex/agents/*.toml`) — `frontier`, `workhorse`, `sweep`, `reviewer` 역할 템플릿; 런타임에는 optional이지만 Restore 계약의 일부이며, `wrappers/codex-helm.sh`가 Codex subagent fan-out을 명시적으로 허용할 때 활성화한다.

## Referenced / optional — 코어 레포가 요구하지 않음

- **slide-writing 정적 HTML/PDF companion** — Primary slide-writing guide에는 renderer가 필요 없다. 명시적인 정적 HTML/PDF job 경로는 준비·binding check·결과 접수에 Python 3.11+ 표준 라이브러리를 사용한다. 렌더에는 명시한 Node 실행 파일·Playwright 모듈·그 모듈에서 찾을 수 있는 `pdf-lib`·Chromium 계열 browser executable이 추가로 필요하다. 이것들은 corpus 배포가 설치하지 않는 job-side dependency다. 검증 버전은 영문 `DEPENDENCIES.md`가 소유하며, 호출 방식과 지원 형식은 companion runbook이 소유한다.

- **Deep review** — 어느 쪽도 별도 도구가 아니다. Codex-seat deep reviewer(`codex-exec`)는 `codex` CLI 자체의 non-interactive exec 모드다: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort="ultra"`, self-contained packet은 stdin으로(`-s read-only`·`-c model_reasoning_effort`·`-c service_tier`는 설치된 codex-cli 0.146.0에서 검증; `-c service_tier="fast"`는 더 빠르고 얕은 명시적 opt-in; `-s read-only`가 약속된 sandbox를 강제한다 — ambient `~/.codex` 설정은 상속되므로 read-only이되 hermetic은 아니다). Claude-seat deep reviewer(**ultracode**)는 prompt에 keyword `ultracode`를 담아 헤드리스로 실행되는 `claude` backend 자체다. 개인·서드파티 reviewer는 shipped config가 아니라 user-owned `review-methods.local.toml`에 등록한다.
- **codex-plugin-cc** (1.0.6; 2026-07-16 재평가) — `codex app-server`를 상속된 env로 spawn하며 `--ignore-user-config`/`--profile`이 없어 매 실행이 실제 `~/.codex`(config.toml, auth, 해당 MCP 서버)를 그대로 읽는다. 호출 단위 hermetic reach가 없다는 점이 **review** route로 부적합한 이유다. reviewer가 main과 같은 config·AGENTS.md를 상속하면 `review_family=cross`가 제공하려는 독립적 관점이 무너진다. model은 선택 가능하지만(`--model`/`--effort`), 낡은 것은 번들된 `gpt-5-4-prompting` 스킬이므로 최신 model을 넘겨도 해소되지 않는다. **미채택**; 제어 가능한 reach를 위해 `wrappers/codex-run.sh` 선호. Claude Code의 `/code-review`는 건드리지 않으며(`code-review.md` 없음; 네임스페이스 `/codex:*`를 추가), 따라서 그 route를 cross-family로 만든 적이 없다. 우리에게 없고 별도로 탐낼 만한 기능: opt-in `Stop` hook review gate.
- **MCP servers** (clickhouse, node_repl 등) — 환경 종속; Environment Binding이 참조하나 코어 의존성 아님. launcher는 offer가 `mcp-stdio-v1` adapter를 선언한 user-registered capability에 대해서만 stdio MCP 서버를 등록하며, shipped review method 중 MCP-backed는 없다.
- **spreadsheet-processing** (skill) — 전역 spreadsheet 규칙이 참조; 원작성자의 Claude Code·Codex 환경에 존재. 없으면 규칙의 인라인 폴백(일반 tool/code + real Excel-engine 검증)이 적용된다.

## Untracked — 의존성이지만 설계상 제외

Host `config.toml`, `settings.json`, `hooks.json` — 머신 종속 신뢰 목록, 훅 경로, MCP 시크릿. 추적되는 `launch/agent-launch.toml`에는 launch binding만 두고 secret은 두지 않는다. README Scope 참조.

## Re-verify

```bash
codex --version
codex_help="$(codex exec --help)"
for flag in --output-schema --ignore-user-config --ephemeral --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --cd --sandbox --model --profile; do
  printf '%s\n' "$codex_help" | grep -q -- "$flag" || { echo "missing codex flag: $flag"; exit 1; }
done
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-c([,[:space:]]|$)' || { echo "missing codex flag: -c"; exit 1; }
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-C([,[:space:]]|$)' || { echo "missing codex flag: -C"; exit 1; }
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-p([,[:space:]]|$)' || { echo "missing codex flag: -p"; exit 1; }
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-s([,[:space:]]|$)' || { echo "missing codex flag: -s"; exit 1; }
claude --version; claude --help | grep -E -- '--model|--effort|--agents|--append-system-prompt|--mcp-config'
bash --version | head -1; zsh --version; python3 --version; git --version
bash -n wrappers/codex-run.sh wrappers/codex-helm.sh gates/check-parity.sh launch/check-prompting-targets.sh
zsh -n launch/agent-launch.zsh
python3 -c 'compile(open("launch/agent-launch.py").read(), "launch/agent-launch.py", "exec")'
./gates/check-parity.sh
./launch/check-prompting-targets.sh
python3 - <<'PY'
import os, pathlib, tomllib
roots = [pathlib.Path("codex/agents"), pathlib.Path(os.environ.get("CODEX_HOME", pathlib.Path.home() / ".codex")) / "agents"]
required = {"frontier.toml", "workhorse.toml", "sweep.toml", "reviewer.toml"}
for root in roots:
    missing = required - {path.name for path in root.glob("*.toml")}
    assert not missing, f"missing required agent TOML files in {root}: {sorted(missing)}"
    for path in sorted(root.glob("*.toml")):
        tomllib.loads(path.read_text())
    print(f"agent TOML ok: {root}")
PY
wrappers/codex-helm.sh --dry-run --mode review "probe"
```

## Ownership

| 소유처 | 소유 대상 |
| --- | --- |
| 이 문서 (`DEPENDENCIES.md`) | 스크립트 런타임 도구 + 요구 capability; 의존성 인벤토리 |
| 각 가이드 `Environment Binding` | role-slot→model 바인딩, host-CLI 검증 버전 |
| 각 가이드 `Evidence Base` | 숫자 기본값·실측 |

## 세션별 corpus hook

`--corpus-native`는 두 호스트에서 같은 Python hook과 이벤트 바인딩을 사용한다.
확인한 실행 환경은 Claude Code 2.1.268과 Codex CLI 0.153.4다. Claude는 항목별
plugin과 `--plugin-dir`, Codex는 세션별 inline hook 설정과 `hooks/list`를 사용한다.
Codex의 신뢰·활성화 상태를 임의로 바꾸지 않는다. 실제 Codex runtime과 로컬 테스트
서버로 신뢰 전후의 hook 실행과 컨텍스트 주입을 검증한다. Corpus agent의 모델·도구
제약 변환은 hook 지원과 별개의 adapter 작업이다.
