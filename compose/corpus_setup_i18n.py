"""Shared installation text; locale selection never changes setup data or identifiers."""
from __future__ import annotations

import copy
import os
import re
from string import Formatter
from typing import Any, Mapping


LANGUAGES = (("English", "en"), ("한국어", "ko"), ("日本語", "ja"))

# English source templates map to Korean and Japanese in that order.
MESSAGES: dict[str, tuple[str, str]] = {
    "unknown setup presentation": ("알 수 없는 설치 화면 형식", "不明なセットアップ表示形式"),
    "Use the returned review_id with agent-bios setup status or agent-bios setup resume before continuing.": (
        "계속하기 전에 반환된 review_id를 agent-bios setup status 또는 agent-bios setup resume에 전달해 상태를 확인하세요.",
        "続行する前に、返された review_id を agent-bios setup status または agent-bios setup resume に渡して状態を確認してください。"),
    "Continue in the conversation using the returned verified entrypoint.": (
        "반환된 검증된 실행 경로를 사용해 대화에서 계속 진행하세요.",
        "返された検証済みの実行経路を使い、会話で続けてください。"),
    "Setup could not finish. Details: {detail}": (
        "설정을 완료하지 못했습니다. 상세 내용: {detail}",
        "セットアップを完了できませんでした。詳細: {detail}"),
    "agent-bios setup": ("agent-bios 설치", "agent-bios セットアップ"),
    "Continue": ("계속", "続ける"),
    "Back": ("이전", "戻る"),
    "Cancel": ("취소", "キャンセル"),
    "Next": ("다음", "次へ"),
    "Apply setup": ("설정 적용", "設定を適用"),
    "Close": ("닫기", "閉じる"),
    "Choose corpus": ("코퍼스 선택", "コーパスを選択"),
    "Prepare personal instructions": ("개인 지침 준비", "個人の指示を準備"),
    "Choose dependencies": ("의존성 선택", "依存関係を選択"),
    "Review setup": ("설정 확인", "設定を確認"),
    "Checking available setup options…": ("사용 가능한 설정을 확인하고 있습니다…", "利用可能な設定を確認しています…"),
    "No active corpus": ("코퍼스 사용 안 함", "コーパスを使用しない"),
    "All available corpus": ("사용 가능한 모든 코퍼스", "利用可能なすべてのコーパス"),
    "all available corpus": ("사용 가능한 모든 코퍼스", "利用可能なすべてのコーパス"),
    "Choose supplied packages or domains": ("제공된 패키지 또는 분야 선택", "提供パッケージまたは分野を選択"),
    "Keep saved/default selection": ("저장된 선택 또는 기본값 유지", "保存済みの選択または既定値を維持"),
    "Keep the saved corpus policy and item choices": ("저장된 코퍼스 정책과 항목 선택 유지", "保存済みのコーパスポリシーと項目の選択を維持"),
    "No selected items": ("선택한 항목 없음", "選択した項目はありません"),
    "No specific corpus entries selected": ("개별 코퍼스 항목을 선택하지 않았습니다", "個別のコーパス項目は選択されていません"),
    "Add folder": ("폴더 추가", "フォルダーを追加"),
    "Clear folders": ("폴더 비우기", "フォルダー一覧をクリア"),
    "Project folder path (optional)": ("프로젝트 폴더 경로 (선택 사항)", "プロジェクトフォルダーのパス（任意）"),
    "Global instruction files only": ("전역 지침 파일만 확인", "グローバル指示ファイルのみ"),
    "No sources selected": ("선택한 원본 없음", "選択したソースはありません"),
    "No dependency installation selected": ("설치할 의존성을 선택하지 않았습니다", "インストールする依存関係は選択されていません"),
    "Every dependency: purpose and location": ("전체 의존성: 용도와 위치", "すべての依存関係：用途と場所"),
    "Exact commands, paths and plan": ("실행 명령·경로·계획 원문", "実行コマンド・パス・計画の原文"),
    "Operation output": ("실행 출력", "実行出力"),
    "Read-only checks; no installation changes yet.": ("읽기만 하며 확인 중입니다. 아직 변경 사항을 적용하지 않았습니다.", "読み取りのみで確認しています。まだインストールによる変更はありません。"),
    "No installation changes yet. Choose only what you want to use.": ("아직 변경 사항을 적용하지 않았습니다. 사용할 항목만 선택하세요.", "まだインストールによる変更はありません。使用する項目だけを選んでください。"),
    "Choose what future activated launches may use. App tasks require their own explicit use.": (
        "앞으로 활성화하는 세션에서 사용할 코퍼스를 선택하세요. 앱의 각 작업에서는 별도로 사용을 요청해야 합니다.",
        "今後有効にするセッションで使用するコーパスを選んでください。アプリ内の各タスクでは別途、使用を明示する必要があります。"),
    "Optional: capture existing instructions for later model review. Space toggles a source; originals stay unchanged.": (
        "선택 사항: 기존 지침을 복사해 나중에 모델이 검토하도록 준비합니다. Space로 원본을 선택하며 원본 파일은 바꾸지 않습니다.",
        "任意：既存の指示をコピーし、後でモデルが確認できるように準備します。Spaceでソースを選択します。元のファイルは変更しません。"),
    "Available dependencies are checked and locked. Choose only additional installations; missing items without an installer stay unchecked.": (
        "이미 사용 가능한 항목은 체크된 고정 상태입니다. 추가로 설치할 항목만 선택하세요. 설치 방법이 없는 미충족 항목은 체크하지 않습니다.",
        "利用可能な項目はチェック済みで固定されています。追加でインストールする項目だけ選んでください。インストール手順がない未充足の項目は未選択です。"),
    "Already on this device — kept unchanged. This does not turn on corpus use.": (
        "이 기기에 보관 중인 개인 자료 — 그대로 보존합니다. 보관된 자료가 자동으로 사용되지는 않습니다.",
        "この端末に保存済みの個人データ — そのまま保持します。この表示でコーパスの使用が有効になることはありません。"),
    "{name} — {count} items retained": ("{name} — {count}개 항목 보관 중", "{name} — {count}件を保存済み"),
    "Connect to the Codex app": ("Codex 앱 연결", "Codexアプリと連携"),
    "Adds the $agent-bios command to Codex app conversations for setup and personal instruction management. Choose separately which tasks use the instructions.": (
        "$agent-bios는 Codex 앱 대화에서 설정과 개인 지침을 관리하는 명령입니다. 지침을 사용할 작업은 따로 선택합니다.",
        "$agent-biosはCodexアプリの会話で設定や個人の指示を管理するコマンドです。指示を使用するタスクは別途選びます。"),
    "All content in {package}": ("{package}의 모든 내용", "{package} のすべての内容"),
    "{description} ({target})": ("{description} ({target})", "{description} ({target})"),
    "{package} (included)": ("{package} (포함됨)", "{package}（同梱）"),
    "Selected item: {item}": ("선택한 항목: {item}", "選択した項目：{item}"),
    "Location: {location}": ("위치: {location}", "場所：{location}"),
    "available": ("사용 가능", "利用可能"),
    "missing": ("요건 미충족", "要件未充足"),
    "not assessed": ("확인하지 않음", "未確認"),
    "global": ("전역", "グローバル"),
    "project": ("프로젝트", "プロジェクト"),
    "runtime": ("실행에 필요", "実行に必要"),
    "optional package manager": ("선택적 패키지 관리자", "任意のパッケージマネージャー"),
    "delivery / optional host install": ("배포 / 선택적 호스트 설치", "配布／任意のホスト導入"),
    "selected host": ("선택한 실행 도구", "選択した実行ツール"),
    "workflow": ("작업 흐름", "ワークフロー"),
    "optional shell connection": ("선택적 셸 연결", "任意のシェル連携"),
    "shell adapters": ("셸 어댑터", "シェルアダプター"),
    "managed dependency prerequisite": ("관리형 의존성 설치에 필요", "管理環境の依存関係導入に必要"),
    "bundled UI runtime": ("내장 UI 실행 환경", "同梱UI実行環境"),
    "bundled UI dependency": ("내장 UI 의존성", "同梱UIの依存関係"),
    "learning capture": ("학습 기록 수집", "学習記録の収集"),
    "optional job / personal integration": ("선택적 작업 / 개인 연동", "任意の処理／個人向け連携"),
    "Homebrew": ("Homebrew", "Homebrew"),
    "Bash": ("Bash", "Bash"),
    "Python 3.11+": ("Python 3.11+", "Python 3.11+"),
    "Node.js 22+": ("Node.js 22+", "Node.js 22+"),
    "npm": ("npm", "npm"),
    "Codex CLI": ("Codex CLI", "Codex CLI"),
    "Claude Code": ("Claude Code", "Claude Code"),
    "Git": ("Git", "Git"),
    "zsh": ("zsh", "zsh"),
    "cp": ("cp", "cp"),
    "mktemp": ("mktemp", "mktemp"),
    "Python venv / pip bootstrap": ("Python venv / pip 초기 준비", "Python venv／pip の初期準備"),
    "Textual (included)": ("Textual (포함됨)", "Textual（同梱）"),
    "jsonschema": ("jsonschema", "jsonschema"),
    "Playwright module": ("Playwright 모듈", "Playwright モジュール"),
    "pdf-lib": ("pdf-lib", "pdf-lib"),
    "Chromium-family browser": ("Chromium 계열 브라우저", "Chromium 系ブラウザー"),
    "Spreadsheet-processing skill": ("스프레드시트 처리 skill", "スプレッドシート処理スキル"),
    "User-specific MCP servers": ("사용자별 MCP 서버", "ユーザー固有のMCPサーバー"),
    "Homebrew prefix": ("Homebrew 설치 경로", "Homebrew のインストール先"),
    "Homebrew prefix and required dependencies": ("Homebrew 설치 경로와 필요한 의존성", "Homebrew のインストール先と必要な依存関係"),
    "npm global prefix": ("npm 전역 설치 경로", "npm のグローバルインストール先"),
    "process-owned temporary directory": ("이 프로세스의 임시 디렉터리", "このプロセス専用の一時ディレクトリ"),
    "Offers local package installation recipes when available.": ("사용 가능하면 로컬 패키지 설치 방법을 제공합니다.", "利用可能な場合、ローカルパッケージのインストール手順を提供します。"),
    "Optional: use an existing operating-system package manager or the official host installer.": ("선택 사항입니다. 기존 운영체제 패키지 관리자나 해당 도구의 공식 설치기를 사용하세요.", "任意です。既存のOSパッケージマネージャーか、対象ツールの公式インストーラーを使用してください。"),
    "This installer supports macOS and Linux.": ("이 설치기는 macOS와 Linux를 지원합니다.", "このインストーラーはmacOSとLinuxに対応しています。"),
    "Runs the package entry point and bundled shell tools.": ("패키지 실행 명령과 포함된 셸 도구를 실행합니다.", "パッケージの起動コマンドと同梱シェルツールを実行します。"),
    "Install Bash using your operating system package manager.": ("운영체제의 패키지 관리자로 Bash를 설치하세요.", "OSのパッケージマネージャーでBashをインストールしてください。"),
    "Runs installation, corpus storage, and terminal interfaces.": ("설치, 코퍼스 저장, 터미널 화면을 실행합니다.", "インストール、コーパスの保存、ターミナル画面を実行します。"),
    "Install Python 3.11+ and ensure python3 resolves to it.": ("Python 3.11 이상을 설치하고 python3 명령이 해당 버전을 실행하는지 확인하세요.", "Python 3.11以降をインストールし、python3コマンドでそのバージョンが起動することを確認してください。"),
    "Supports npm host installation and optional slide rendering.": ("npm을 통한 호스트 설치와 선택적 슬라이드 렌더링에 사용합니다.", "npmによるホストの導入と任意のスライド描画に使用します。"),
    "Install a current Node.js distribution with npm; the corpus runtime itself does not need Node.": ("npm이 포함된 최신 Node.js를 설치하세요. 코퍼스 실행 자체에는 Node가 필요하지 않습니다.", "npmを含む現行のNode.jsをインストールしてください。コーパスの実行自体にはNodeは不要です。"),
    "Node.js 22+ is required by the Claude npm installer.": ("Claude의 npm 설치에는 Node.js 22 이상이 필요합니다.", "ClaudeのnpmインストーラーにはNode.js 22以降が必要です。"),
    "Installs the package and selected host CLIs.": ("패키지와 선택한 호스트 CLI를 설치합니다.", "パッケージと選択したホストCLIをインストールします。"),
    "npm comes with Node.js; install Node.js first and rerun setup.": ("npm은 Node.js에 포함되어 있습니다. 먼저 Node.js를 설치한 뒤 설정을 다시 실행하세요.", "npmはNode.jsに含まれます。先にNode.jsをインストールしてからセットアップを再実行してください。"),
    "Required to launch this host; sign-in is a separate step.": ("이 호스트를 실행하는 데 필요합니다. 로그인은 별도 단계입니다.", "このホストの起動に必要です。ログインは別の手順です。"),
    "Use the official installer, or install npm with Node.js {minimum}+ and rerun setup.": ("공식 설치기를 사용하거나 Node.js {minimum} 이상과 npm을 설치한 뒤 설정을 다시 실행하세요.", "公式インストーラーを使うか、Node.js {minimum}以降とnpmをインストールしてからセットアップを再実行してください。"),
    "Clone updates, worktrees, and version-control workflows.": ("복제한 저장소 업데이트, worktree, 버전 관리에 사용합니다.", "クローンしたリポジトリの更新、worktree、バージョン管理に使用します。"),
    "Optional interception of bare host commands.": ("호스트 명령만 입력했을 때 런처를 여는 선택적 기능입니다.", "ホスト名だけのコマンド入力でランチャーを開く任意の機能です。"),
    "Install with your operating system package manager.": ("운영체제의 패키지 관리자로 설치하세요.", "OSのパッケージマネージャーでインストールしてください。"),
    "Required by optional shell worker adapters.": ("선택적 셸 작업 어댑터에서 사용합니다.", "任意のシェルワーカーアダプターで使用します。"),
    "Install the standard BSD or GNU command-line utilities for your system.": ("운영체제에 맞는 표준 BSD 또는 GNU 명령줄 도구를 설치하세요.", "お使いのシステムに合った標準のBSDまたはGNUコマンドラインツールをインストールしてください。"),
    "Creates the managed environment using AGENT_LAUNCH_PYTHON when set, otherwise python3.": ("AGENT_LAUNCH_PYTHON이 지정되어 있으면 해당 Python으로, 아니면 python3로 관리 환경을 만듭니다.", "AGENT_LAUNCH_PYTHONが設定されていればそのPythonを、未設定ならpython3を使って管理環境を作成します。"),
    "Install venv/ensurepip for Python 3.11+; check AGENT_LAUNCH_PYTHON if configured. An existing managed environment does not need this bootstrap.": ("Python 3.11 이상의 venv/ensurepip를 설치하세요. AGENT_LAUNCH_PYTHON을 지정했다면 값도 확인하세요. 관리 환경이 이미 있으면 이 초기 준비는 필요하지 않습니다.", "Python 3.11以降のvenv/ensurepipをインストールしてください。AGENT_LAUNCH_PYTHONを設定している場合はその値も確認してください。既存の管理環境にはこの初期準備は不要です。"),
    "The terminal UI uses verified bundled packages without a system or managed Textual installation.": ("터미널 화면은 검증된 내장 패키지를 사용하므로 시스템이나 관리 환경에 Textual을 따로 설치할 필요가 없습니다.", "ターミナル画面は検証済みの同梱パッケージを使うため、システムや管理環境にTextualを別途インストールする必要はありません。"),
    "The shipped UI bundle is unavailable; verify or reinstall this agent-bios package.": ("내장 UI 패키지를 사용할 수 없습니다. agent-bios 패키지를 검증하거나 다시 설치하세요.", "同梱UIパッケージを利用できません。agent-biosパッケージを検証するか、再インストールしてください。"),
    "Included in the Textual runtime; no separate installation is needed.": ("Textual 실행 환경에 포함되어 있어 별도 설치가 필요하지 않습니다.", "Textual実行環境に含まれているため、別途インストールする必要はありません。"),
    "Validates end-user learn submissions against JSON Schema Draft 2020-12, and also serves the author gate.": ("사용자가 제출한 학습 기록을 JSON Schema Draft 2020-12로 검증합니다. 개발용 검사에서도 사용합니다.", "ユーザーが送信する学習記録をJSON Schema Draft 2020-12で検証します。開発用の検査でも使用します。"),
    "Select the managed learning validator installation; learn uses it when system Python lacks jsonschema.": ("관리 환경의 학습 검증기 설치를 선택하세요. 시스템 Python에 jsonschema가 없으면 learn이 이 검증기를 사용합니다.", "管理環境への学習記録検証ツールのインストールを選択してください。システムPythonにjsonschemaがない場合、learnがこの環境を使用します。"),
    "Static slide jobs bind an explicit Playwright module file.": ("정적 슬라이드 작업에서는 사용할 Playwright 모듈 파일을 명시합니다.", "静的スライドの処理では、使用するPlaywrightモジュールファイルを明示します。"),
    "Static slide jobs resolve pdf-lib beside the selected Playwright module.": ("정적 슬라이드 작업은 선택한 Playwright 모듈 옆에서 pdf-lib를 찾습니다.", "静的スライドの処理では、選択したPlaywrightモジュールの隣からpdf-libを読み込みます。"),
    "Static slide jobs bind an explicit browser executable.": ("정적 슬라이드 작업에서는 사용할 브라우저 실행 파일을 명시합니다.", "静的スライドの処理では、使用するブラウザー実行ファイルを明示します。"),
    "Selected spreadsheet guidance can use this optional personal skill.": ("선택한 스프레드시트 지침에서 이 개인용 skill을 사용할 수 있습니다.", "選択したスプレッドシートの指針で、この任意の個人スキルを利用できます。"),
    "Only user-selected workflows require their configured external services.": ("사용자가 선택한 작업 흐름에서만 해당 외부 서비스 설정이 필요합니다.", "ユーザーが選択したワークフローでのみ、対応する外部サービスの設定が必要です。"),
    "Configure this only for a workflow that requires it; setup cannot choose your job environment or account.": ("필요한 작업 흐름에서만 설정하세요. 설치기가 작업 환경이나 계정을 대신 선택하지는 않습니다.", "必要とするワークフローでのみ設定してください。セットアップが処理環境やアカウントを代わりに選ぶことはありません。"),
    "Technical-common: coding, verification menus, documentation hygiene, tooling safety, concept economy": ("개발 공통: 코딩, 검증 방법, 문서 관리, 도구 안전, 개념 정리", "開発共通：コーディング、検証方法、文書管理、ツールの安全性、概念の整理"),
    "LLM pipeline development: capability boundary, structured output, runtime authority": ("LLM 파이프라인 개발: 기능 경계, 구조화된 출력, 실행 권한", "LLMパイプライン開発：機能の境界、構造化出力、実行時の権限"),
    "Multi-model/CLI orchestration: spawn policy, prompting guides, cross-family review": ("여러 모델·CLI 협업: 에이전트 생성 정책, 프롬프트 가이드, 다른 계열 모델의 검토", "複数モデル・CLIの連携：エージェント起動方針、プロンプトガイド、異なる系列のモデルによるレビュー"),
    "Visual explanations: HTML/SVG diagrams, implementation map": ("시각적 설명: HTML/SVG 다이어그램, 구현 현황도", "視覚的な説明：HTML/SVG図、実装状況図"),
    "Office artifacts: spreadsheet processing": ("오피스 문서: 스프레드시트 처리", "オフィス文書：スプレッドシート処理"),
    "Personal corpus": ("개인 코퍼스", "個人コーパス"),
    "Claude learning records": ("Claude 학습 기록", "Claudeの学習記録"),
    "Codex learning records": ("Codex 학습 기록", "Codexの学習記録"),
    "Setup stopped after the current operation finished.": ("진행 중이던 작업을 마친 뒤 설정을 중단했습니다.", "実行中の処理が完了した時点でセットアップを停止しました。"),
    "Dependencies retained: {dependencies}.": ("설치된 의존성은 유지됩니다: {dependencies}.", "インストール済みの依存関係は保持されます：{dependencies}。"),
    "The private runtime installation is retained; remaining setup was not applied.": ("개인 실행 환경은 설치된 상태로 유지됩니다. 나머지 설정은 적용하지 않았습니다.", "専用の実行環境はインストール済みの状態で保持されます。残りの設定は適用していません。"),
    "The private runtime installation was not applied.": ("개인 실행 환경 설치는 적용하지 않았습니다.", "専用の実行環境のインストールは適用していません。"),
    "Setup cancelled. No installation changes were applied.": ("설치를 취소했습니다. 설치와 관련한 변경은 적용하지 않았습니다.", "セットアップをキャンセルしました。インストールによる変更は適用していません。"),
    "Setup preview complete. No installation changes were applied.": ("설치 미리보기를 마쳤습니다. 설치와 관련한 변경은 적용하지 않았습니다.", "セットアップのプレビューが完了しました。インストールによる変更は適用していません。"),
    "Private runtime installation needs attention: {error}": ("개인 실행 환경 설치를 확인해야 합니다: {error}", "専用の実行環境のインストールを確認する必要があります：{error}"),
    "Inspect the reported state and rerun agent-bios install.": ("표시된 상태를 확인한 뒤 agent-bios install을 다시 실행하세요.", "表示された状態を確認し、agent-bios installを再実行してください。"),
    "Dependency installation failed: {dependency}. The private runtime was not installed by this setup.": ("의존성 설치에 실패했습니다: {dependency}. 이번 설정에서는 개인 실행 환경을 설치하지 않았습니다.", "依存関係のインストールに失敗しました：{dependency}。今回のセットアップでは専用の実行環境をインストールしていません。"),
    "Dependencies already installed: {dependencies}.": ("이미 설치된 의존성: {dependencies}.", "インストール済みの依存関係：{dependencies}。"),
    "Resolve the dependency error and run agent-bios install --interactive again.": ("의존성 오류를 해결한 뒤 agent-bios install --interactive를 다시 실행하세요.", "依存関係のエラーを解決し、agent-bios install --interactiveを再実行してください。"),
    "Private runtime installed; app registration or instruction capture needs attention.": ("개인 실행 환경은 설치했습니다. 앱 등록 또는 지침 캡처를 확인해야 합니다.", "専用の実行環境をインストールしました。アプリへの登録または指示のキャプチャを確認する必要があります。"),
    "The app command registration is retained; instruction capture did not complete.": ("앱 명령 등록은 유지됩니다. 지침 캡처는 완료하지 못했습니다.", "アプリへのコマンド登録は保持されます。指示のキャプチャは完了していません。"),
    "Dependencies installed: {dependencies}.": ("설치한 의존성: {dependencies}.", "インストールした依存関係：{dependencies}。"),
    "Open Corpus Studio: agent-bios corpus (terminal or Codex app terminal panel).": ("Corpus Studio 열기: 터미널 또는 Codex 앱 터미널 패널에서 agent-bios corpus를 실행하세요.", "Corpus Studioを開くには、ターミナルまたはCodexアプリのターミナルパネルでagent-bios corpusを実行してください。"),
    "Setup did not complete.": ("설정을 완료하지 못했습니다.", "セットアップを完了できませんでした。"),
    "Setup complete. Private runtime installed.": ("설정을 완료하고 개인 실행 환경을 설치했습니다.", "セットアップが完了し、専用の実行環境をインストールしました。"),
    "Corpus for future activated sessions: none.": ("앞으로 활성화하는 세션에서는 코퍼스를 사용하지 않습니다.", "今後有効にするセッションではコーパスを使用しません。"),
    "Corpus for future activated sessions: {corpus}.": ("앞으로 활성화하는 세션에서 사용할 코퍼스: {corpus}.", "今後有効にするセッションで使用するコーパス：{corpus}。"),
    "Corpus policy: core, infrastructure and personal corpus.": ("코퍼스 정책: 핵심·기반·개인 코퍼스를 사용합니다.", "コーパスポリシー：コア・基盤・個人コーパスを使用します。"),
    "Corpus policy: core, infrastructure and personal corpus; selected domains: {domains}.": ("코퍼스 정책: 핵심·기반·개인 코퍼스를 사용합니다. 선택한 분야: {domains}.", "コーパスポリシー：コア・基盤・個人コーパスを使用します。選択した分野：{domains}。"),
    "Saved corpus policy and item choices preserved.": ("저장된 코퍼스 정책과 항목 선택을 유지했습니다.", "保存済みのコーパスポリシーと項目の選択を保持しました。"),
    "Codex app bridge needs attention; existing files were preserved:": ("Codex 앱 연결을 확인해야 합니다. 기존 파일은 보존했습니다:", "Codexアプリとの連携を確認する必要があります。既存のファイルは保持しました："),
    "Codex app bridge registered: use $agent-bios for per-task preview/use/off and corpus management.": ("Codex 앱 연결을 등록했습니다. $agent-bios로 작업별 코퍼스를 미리 보고 사용하거나 끄고, 코퍼스를 관리할 수 있습니다.", "Codexアプリとの連携を登録しました。$agent-biosでタスクごとにコーパスをプレビュー・使用・無効化し、管理できます。"),
    "Instruction capture: {capture_id}. Model review is required before activation.": ("지침 캡처: {capture_id}. 활성화하기 전에 모델 검토가 필요합니다.", "指示のキャプチャ：{capture_id}。有効化する前にモデルによる確認が必要です。"),
    "Instruction capture: {capture_id} ({count} source files). Model review is required before activation.": ("지침 캡처: {capture_id} (원본 파일 {count}개). 활성화하기 전에 모델 검토가 필요합니다.", "指示のキャプチャ：{capture_id}（原本ファイル{count}件）。有効化する前にモデルによる確認が必要です。"),
    "Next: {command}": ("다음 명령: {command}", "次のコマンド：{command}"),
    "In Codex: {request}": ("Codex에서: {request}", "Codexで：{request}"),
    "Use $agent-bios to import capture {capture_id}": ("캡처 {capture_id} 가져오기를 $agent-bios에 요청해 주세요", "$agent-biosでキャプチャ{capture_id}を取り込んでください"),
    "Language / 언어 / 言語": ("Language / 언어 / 言語", "Language / 언어 / 言語"),
    "Continue / 계속 / 続ける": ("Continue / 계속 / 続ける", "Continue / 계속 / 続ける"),
    "Cancel / 취소 / 中止": ("Cancel / 취소 / 中止", "Cancel / 취소 / 中止"),
    "Choose your language to continue.": ("계속하려면 언어를 선택하세요.", "言語を選択して続けてください。"),
    "Close preview": ("미리보기 닫기", "プレビューを閉じる"),
    "Stop request": ("중단 요청", "停止をリクエスト"),
    "Esc / Ctrl+C: Cancel   Tab: Move   Space: Toggle": ("Esc / Ctrl+C: 취소   Tab: 이동   Space: 선택 전환", "Esc / Ctrl+C：キャンセル   Tab：移動   Space：選択切り替え"),
    "Ready to apply": ("적용 준비 완료", "適用の準備ができました"),
    "Corpus: {selection}": ("코퍼스: {selection}", "コーパス：{selection}"),
    "App connection: {connection}": ("앱 연결: {connection}", "アプリとの連携：{connection}"),
    "Register $agent-bios for explicit task use": ("작업에서 명시적으로 사용할 수 있도록 $agent-bios 등록", "タスク内で明示的に使用できるよう$agent-biosを登録"),
    "No new app registration": ("새 앱 등록 없음", "新たなアプリ登録は行いません"),
    "Install:": ("설치 항목:", "インストールする項目："),
    "Install dependencies: none": ("설치할 의존성 없음", "インストールする依存関係はありません"),
    "Prepare for model review: {count} instruction file(s)": ("모델 검토를 위해 준비할 지침 파일: {count}개", "モデルによる確認に向けて準備する指示ファイル：{count}件"),
    "Native global and project instruction files are preserved.": ("기존 전역·프로젝트 지침 파일은 보존합니다.", "既存のグローバル指示ファイルとプロジェクト指示ファイルは保持します。"),
    "This setup does not add corpus to the current app task.": ("이 설정은 현재 앱 작업에 코퍼스를 추가하지 않습니다.", "このセットアップでは、現在のアプリタスクにコーパスを追加しません。"),
    "Library files remain stored privately when active corpus is off.": ("코퍼스를 사용하지 않아도 라이브러리 파일은 개인 저장소에 남아 있습니다.", "コーパスを使用しない場合も、ライブラリファイルは専用の保存場所に保持されます。"),
    "Captured instructions need a separate semantic review before import.": ("캡처한 지침은 가져오기 전에 내용을 별도로 검토해야 합니다.", "キャプチャした指示は、取り込む前に内容を別途確認する必要があります。"),
    "Setup could not be prepared.\n\n{error}": ("설정을 준비하지 못했습니다.\n\n{error}", "セットアップを準備できませんでした。\n\n{error}"),
    "No setup plan was applied. Close to see the diagnostic.": ("설치 계획은 적용하지 않았습니다. 닫으면 진단 결과를 확인할 수 있습니다.", "セットアップ計画は適用していません。閉じると診断情報を確認できます。"),
    "{step} of 4 — {stage}": ("4단계 중 {step} — {stage}", "4段階中 {step} — {stage}"),
    "Enter a project folder path, or continue without adding one.": ("프로젝트 폴더 경로를 입력하거나 추가하지 않고 계속하세요.", "プロジェクトフォルダーのパスを入力するか、追加せずに続けてください。"),
    "Choose an existing absolute project folder path.": ("실제로 존재하는 프로젝트 폴더의 절대 경로를 지정하세요.", "実在するプロジェクトフォルダーの絶対パスを指定してください。"),
    "Project folders:\n{paths}": ("프로젝트 폴더:\n{paths}", "プロジェクトフォルダー：\n{paths}"),
    "Finding instruction files in the selected locations…": ("선택한 위치에서 지침 파일을 찾고 있습니다…", "選択した場所で指示ファイルを探しています…"),
    "Could not inspect those locations: {error}": ("해당 위치를 확인하지 못했습니다: {error}", "指定された場所を確認できませんでした：{error}"),
    "{count} eligible file(s); selecting none is valid.": ("선택 가능한 파일 {count}개. 아무것도 선택하지 않아도 됩니다.", "選択可能なファイルは{count}件です。何も選択しなくてもかまいません。"),
    "Skipped {path}: {reason}": ("건너뛴 경로 {path}: {reason}", "スキップしたパス {path}：{reason}"),
    "Capture is independent of corpus selection and needs later model review.": ("지침 캡처는 코퍼스 선택과 별개이며, 나중에 모델의 검토가 필요합니다.", "指示のキャプチャはコーパスの選択とは独立しており、後でモデルによる確認が必要です。"),
    "Selected corpus: {selection}": ("선택한 코퍼스: {selection}", "選択したコーパス：{selection}"),
    "Selected files:\n{paths}": ("선택한 파일:\n{paths}", "選択したファイル：\n{paths}"),
    "Global instruction files only; add a project folder to include its files.": ("현재는 전역 지침 파일만 확인합니다. 프로젝트 파일도 보려면 폴더를 추가하세요.", "現在はグローバル指示ファイルのみを確認しています。プロジェクトのファイルも含めるにはフォルダーを追加してください。"),
    "Install: {dependencies}": ("설치할 의존성: {dependencies}", "インストールする依存関係：{dependencies}"),
    "Detected: {version}": ("확인한 버전: {version}", "検出したバージョン：{version}"),
    "Installation location: {path}": ("설치 위치: {path}", "インストール先：{path}"),
    "Location: {path}": ("위치: {path}", "場所：{path}"),
    "Select missing capabilities to install. Next shows the exact effects before Apply.": ("설치할 미충족 항목을 선택하세요. 다음 화면에서 적용 전에 실제 변경 내용을 확인합니다.", "インストールする未充足の項目を選んでください。次の画面で、適用前に実際の変更内容を確認します。"),
    "Your choices are preserved. Edit this section or continue.": ("선택한 내용은 유지됩니다. 이 단계를 수정하거나 계속하세요.", "選択内容は保持されています。この段階を修正するか、そのまま続けてください。"),
    "Choose at least one corpus, or select No active corpus.": ("코퍼스를 하나 이상 선택하거나 ‘코퍼스 사용 안 함’을 선택하세요.", "コーパスを1つ以上選ぶか、「コーパスを使用しない」を選択してください。"),
    "Validating the exact setup plan…": ("실제로 적용할 설치 계획을 검증하고 있습니다…", "実際に適用するセットアップ計画を検証しています…"),
    "Preview refused: {error}": ("미리보기를 진행할 수 없습니다: {error}", "プレビューを実行できません：{error}"),
    "Read-only preview. No Apply is available in dry-run mode.": ("읽기 전용 미리보기입니다. dry-run 모드에서는 적용할 수 없습니다.", "読み取り専用のプレビューです。dry-runモードでは適用できません。"),
    "Review the effects, then choose Apply setup.": ("변경 내용을 확인한 뒤 ‘설정 적용’을 선택하세요.", "変更内容を確認してから「設定を適用」を選択してください。"),
    "Apply refused before changes: {error} Choose Next to review a fresh plan.": ("변경하기 전에 적용을 중단했습니다: {error} ‘다음’을 선택해 새 계획을 확인하세요.", "変更前に適用を中止しました：{error}。「次へ」を選択し、新しい計画を確認してください。"),
    "Applying the accepted setup. Completed changes will be reported.": ("확인한 설정을 적용하고 있습니다. 완료한 변경 사항을 알려드리겠습니다.", "確認済みの設定を適用しています。完了した変更内容を表示します。"),
    "Installing {dependency}…": ("{dependency} 설치 중…", "{dependency}をインストールしています…"),
    "Installing the private runtime": ("개인 실행 환경 설치 중", "専用の実行環境をインストールしています"),
    "Preparing app registration and selected instruction capture": ("앱 등록과 선택한 지침의 캡처를 준비하고 있습니다", "アプリへの登録と、選択した指示のキャプチャを準備しています"),
    "Could not start {dependency}": ("{dependency} 실행을 시작하지 못했습니다", "{dependency}の実行を開始できませんでした"),
    "Finished {dependency}": ("{dependency} 실행 종료", "{dependency}の処理が終了しました"),
    "The accepted operation finished. Its completed effects remain.": ("확인한 작업이 끝났습니다. 완료된 변경 사항은 유지됩니다.", "確認済みの処理が終了しました。完了した変更内容は保持されます。"),
    "Stopped at a safe boundary; the outcome lists any retained changes.": ("현재 단계를 마친 뒤 중단했습니다. 유지된 변경 사항은 결과에 표시됩니다.", "現在の段階を終えてから停止しました。保持された変更内容は結果に表示されます。"),
    "Setup complete": ("설정 완료", "セットアップ完了"),
    "Setup result": ("설정 결과", "セットアップ結果"),
    "Review the outcome before closing.": ("닫기 전에 결과를 확인하세요.", "閉じる前に結果を確認してください。"),
    "Setup stopped with an error.\n\n{error}\n\nEarlier completed effects may remain. Inspect status before retrying.": (
        "오류로 설정을 중단했습니다.\n\n{error}\n\n앞서 완료된 변경 사항은 남아 있을 수 있습니다. 다시 시도하기 전에 상태를 확인하세요.",
        "エラーによりセットアップを停止しました。\n\n{error}\n\n先に完了した変更内容は残っている可能性があります。再試行する前に状態を確認してください。"),
    "No rollback is claimed. Close to return the diagnostic.": ("변경이 되돌아갔다고 보장하지 않습니다. 닫아서 진단 결과를 확인하세요.", "変更のロールバックは保証されません。閉じて診断情報を確認してください。"),
    "Stop requested. Waiting for the current step to finish safely; completed changes are retained.": ("중단을 요청했습니다. 현재 단계를 안전하게 마칠 때까지 기다립니다. 완료된 변경 사항은 유지됩니다.", "停止をリクエストしました。現在の段階が安全に終了するまで待っています。完了した変更内容は保持されます。"),
    "source": ("원본", "ソース"),
    "unavailable": ("확인 불가", "確認できません"),
}


def detect_language(environ: Mapping[str, str] | None = None) -> str:
    """Honor the first effective locale variable, including unsupported locales."""
    source = os.environ if environ is None else environ
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = source.get(name, "").strip()
        if value:
            language = value.lower().replace("-", "_").split("_", 1)[0].split(".", 1)[0].split("@", 1)[0]
            return language if language in {"en", "ko", "ja"} else "en"
    return "en"


def translate(language: str, message: str, **values: Any) -> str:
    """Translate owned templates; unknown prose and interpolation values stay intact."""
    translations = MESSAGES.get(message)
    template = translations[{"ko": 0, "ja": 1}[language]] if translations and language in {"ko", "ja"} else message
    return template.format(**values) if values or (translations is not None and template_fields(message)) else template


def template_fields(message: str) -> set[str]:
    fields = set()
    for _literal, field, format_spec, _conversion in Formatter().parse(message):
        if field is not None:
            fields.add(field)
            fields.update(template_fields(format_spec))
    return fields


def validate_catalogs() -> list[str]:
    issues = []
    for message, translations in MESSAGES.items():
        if len(translations) != 2:
            issues.append(f"incomplete language coverage: {message}")
            continue
        expected = template_fields(message)
        for language, text in zip(("ko", "ja"), translations):
            if not text or template_fields(text) != expected:
                issues.append(f"placeholder mismatch ({language}): {message}")
    return issues


def dependency_display(language: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Return translated display fields while leaving the controller's row untouched."""
    result = copy.deepcopy(dict(row))
    for field in ("title", "role", "status", "purpose", "install_scope", "manual_reason"):
        value = row.get(field)
        if isinstance(value, str):
            result[field] = translate(language, value)
    title = row.get("title", "")
    if str(row.get("id", "")).startswith("ui-") and isinstance(title, str) and title.endswith(" (included)"):
        result["title"] = translate(language, "{package} (included)", package=title[:-len(" (included)")])
    reason = row.get("manual_reason", "")
    if isinstance(reason, str):
        match = re.fullmatch(r"Use the official installer, or install npm with Node\.js ([0-9]+)\+ and rerun setup\.", reason)
        if match:
            result["manual_reason"] = translate(language, "Use the official installer, or install npm with Node.js {minimum}+ and rerun setup.", minimum=match[1])
        prefix = "The shipped UI bundle is unavailable; verify or reinstall this agent-bios package."
        if reason.startswith(prefix):
            result["manual_reason"] = translate(language, prefix) + reason[len(prefix):]
    return result


def choice_label(language: str, row: Mapping[str, Any]) -> str:
    """Translate supplied description templates without changing a corpus target."""
    label = str(row.get("label", row.get("target", "")))
    target = str(row.get("target", ""))
    if target and label == "All content in " + target:
        return translate(language, "All content in {package}", package=target)
    suffix = " (" + target + ")"
    if target and label.endswith(suffix):
        description = label[:-len(suffix)]
        return translate(language, "{description} ({target})", description=translate(language, description), target=target)
    return label
