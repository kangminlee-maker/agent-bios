# 실행 설정

[← 소개](../README.md) · [영문 상세 기준](../../docs/advanced-launch.md)

이 문서는 한글 참고용이다. 정확한 어댑터·복구·검증 한계는 영문 상세 문서와
[의존성 문서](../../DEPENDENCIES.md)를 함께 확인한다.

## Preflight와 Custom

명시적인 `agent-launch claude` 또는 `agent-launch codex`가 런처를 연다.
전역 PATH에 없다면 `"$HOME/.local/bin/agent-launch"`를 사용한다.
일반 `claude`·`codex`가 런처를 열려면 별도의 셸 연결을 먼저 선택해야 한다.

화살표 키 TUI의 모든 선택 화면은 현재 설정을 상단에 보여준다.
**Custom**은 모델·리뷰·권한·전역 지침·티어를 수정하는 지속형 설정 허브다.
**Start with these settings**로 최종 설정을 확인하고 시작하며,
**Exit without launching**은 실행 없이 취소한다.
Textual이 없는 번호 입력 메뉴에서는 `b`가 뒤로가기 명령이다.

일부 Builder 프리셋과 내부 wrapper는 권한 우회를 기본으로 요청한다.
실행 전에 설정을 확인한다. Software Engineer / Vanilla는 agent-bios 고정본,
실행 계약, 티어 바인딩, 권한 플래그를 추가하지 않는다.
호스트 자체의 전역·프로젝트 지침과 설정은 그대로 적용된다.

## 전역 지침

활성 세션도 사용자 전역 지침을 기본적으로 포함한다.
**Custom → My global instruction files**에서 지원되는 호스트의 제외 여부를 선택한다.
이 선택은 파일 삭제나 접근 금지가 아니다. 프로젝트 메모리·이전 대화에도 내용이 남을 수 있다.

Claude는 지원 버전에서 `claudeMdExcludes`를 사용한다. 현재 Codex 어댑터는 선택적인
전역 문서 제외를 지원하지 않는다. 설정 충돌·심볼릭 링크 등 경계와 버전 조건은
[영문 전역 지침 안내](../../docs/advanced-launch.md#global-instruction-files)에 있다.

## Native 훅과 에이전트

`agent-launch --corpus-native`는 선택한 corpus 훅을 해당 Claude 또는 Codex
세션에만 전달한다. 기본값은 꺼짐이다. 두 호스트가 같은 Python 본문과
`event`/`matcher`를 사용하며, 지원하지 않는 이벤트는 실행 불가로 표시한다.
Claude는 항목별 플러그인, Codex는 세션별 `-c hooks.<Event>=...` 설정을 사용한다.
기존 사용자·프로젝트 훅을 유지하며 전역 훅 설정을 추가하지 않는다.

Codex의 활성화·신뢰 검토는 별도로 적용된다. 새 정의나 바뀐 정의는 해당 세션의
`/hooks`에서 검토해야 한다. 설정 발견과 실제 실행은 다르다.
체크박스의 켜짐도 native 동의를 대신하지 않는다.
현재 corpus agent의 native 전달은 Claude 플러그인 경로를 사용한다.

## 셸 연결

루트 메뉴의 **Shell connection**에서 **Restore connection** 또는 **Remove connection**을
선택한다. CLI는 `agent-bios shell restore`와 `agent-bios shell remove`이고,
`--dry-run`으로 미리 볼 수 있다. 기존 zsh 파일을 백업하고 관리 블록만 다룬다.

연결 후 새 터미널을 열거나 설정을 다시 읽으면 인자 없는 대화형 `claude`·`codex`가
런처를 연다. 인자가 있거나 비대화형인 호출은 원래 CLI로 전달하며 이 경로에 권한
플래그를 추가하지 않는다. 업데이트는 선택한 연결을 유지하고, reset·uninstall은 제거한다.
사용자가 수정한 관리 파일은 임의로 덮어쓰지 않고 충돌을 알린다.

## 리뷰와 스크립트 실행

리뷰는 기본적으로 반대 모델 계열을 요청한다. 이용할 수 없는 경로의 fallback과
PROPOSED 판정은 독립 리뷰가 완료됐다는 뜻이 아니다. 내장 slash-review는 호스트
자신의 명령이며, 다른 계열의 native subagent로 바뀌는 것이 아니다.

Claude workflow reviewer는 prompt의 `ultracode` keyword로 활성화를 요청한다.
실제 활성화 전제와 가용성·receipt·내부 wrapper 권한은
[영문 리뷰 안내](../../docs/advanced-launch.md#review-routing)에 있다.

스크립트의 configured launch는 검토한 프리셋을 명시한다. 전달 인자가 선택된 모델·계약·
권한을 덮어쓰면 거부될 수 있다. Summary는 stderr, backend 출력은 stdout을 사용한다.
런처 프리셋과 Codex 자체의 named profile은 서로 다르며, 현재 private activation
어댑터의 named profile 제약은 [세션 검증 범위](../../docs/session-model.md#verification-and-limits)를 확인한다.
