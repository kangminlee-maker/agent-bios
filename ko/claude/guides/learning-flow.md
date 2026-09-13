---
guide_id: learning-flow
language: ko
status: active
use_when:
  - 사용자가 어떤 세션에서든 `learn!`을 입력했을 때 (이것이 light 포착 흐름)
  - 현재 세션에서 얻은 지속적 교훈을 재사용 + 조직 curation을 위해 포착할 때
  - 후보 교훈을 기록할 가치가 있는지, 그리고 어떻게 적용할지 결정할 때
core_rules:
  - 사용자에게 묻기 전 세 개의 gate — admission bar, type, consumption layer
  - 모든 기록된 learning은 사용자가 승인한다; 승인 없이는 아무것도 쓰지 않는다
  - 제출은 아래의 패키지 경로에 연결된 learn 명령으로만; record를 직접 손으로 쓰지 않는다
---

# Session learning 흐름 (`learn!`)

**Light**, per-user, single-session 포착 흐름: 현재 세션의 교훈을 **learning**
(prose + JSON record)으로 바꿔 (a) 이후 agent-bios를 활성화한 세션에서 선택에 따라
적용하고 (b) 전송이 설정되어 있으면 조직의 curation에 전달한다. 이는 여러 세션을 mining하는 **heavy** session-distill
pipeline(`distill!`, curator/power-user 전용)의 대응물이다. 용어와 전체 routing
framework는 agent-bios repo에서 관리하며, 이 flow가 적용하는 기준은 아래에 적는다.

Preset mission에 양보: 이 세션이 **Session distill** preset(trigger `distill!`)
으로 실행 중이면 그 mission이 포착을 담당하므로 이 흐름을 실행하지 않는다.

## 언제 발동하는가

오직 사용자의 `learn!`에서만. 현재 세션 위 in-conversation으로 실행한다(Workflow
fleet 없음, subagent mining 없음). **한 번의 호출에서 여러 learning 허용** —
각 후보를 gate에 독립적으로 통과시킨다.

## Rigor: 무엇이든 surfacing하기 전 세 개의 gate

각 후보에 대해 셋 다 확립하고, 실패하는 후보는 버린다. 여전히 유효한 후보만
사용자 승인을 위해 surfacing한다.

1. **Admission bar** (promotion criteria — PLACEMENT-FRAMEWORK): 교훈이
   **독립된 세션 ≥2회** 재발했거나, **단일 사건이지만 high materiality**
   (irreversible / verification-corrupting / security)여야 한다. 일회성
   저위험 관찰은 bar를 넘지 못한다 — 그렇게 말하고 건너뛴다.

2. **Type** (typology A–G; root cause로 분류, first match wins):
   - **A. Own-tooling defect** — 우리가 소유한 script/tool의 결함(repair).
   - **B. Tool gotcha** — machine-detectable trigger(command pattern)를 가진
     반직관적 외부 도구 동작.
   - **C. Recognition principle** — cross-domain semantic signal → 의심/행동.
   - **D. Domain procedure** — 이미 routing된 종류의 작업 안의 multi-step 방법.
   - **E. Environment fact** — 일반화 불가·감쇠하는 특정 사실.
   - **F. Unproven** — 아직 bar 아래의 증거(보통 gate 1에서 이미 버려짐).
   - **G. Principle/direction** — 많은 결정을 형성하는 value ordering.
     **v1에서 user-side 제조 안 함**(curator 전용); principle성 관찰은 보통
     learning으로 기록하고 curation이 promote하게 둔다.
   가능하면 *leftward reformulation*을 선호한다(E→C 사실을 principle로 일반화;
   B/C/D→A 지식을 구조로 mechanize) — 더 싸고 신뢰도 높다.

3. **Intended consumption layer** (제때 발화하는 가장 싼 것이 이긴다):
   **enforcement > gate > hook > guide > global > memory** (`incubator` = 나중
   triage용 보관). 이는 **metadata로만** 기록한다 — hook/gate/enforcement를 여기서
   만들지 않는다; mechanization은 curation으로 미룬다.

## Domain 태깅 (curation join key)

`compose/domains.json`의 등록된 어휘에서 `domain`을 제안한다(domain-specific
교훈에는 domain key, 진짜 cross-cutting 교훈에는 `core`/`infra` 같은 tier name);
사용자가 **확인**한다. 불확실하면 `unclassified`를 쓴다(포착을 막지 않는다 —
curator가 나중에 배정). 맞는 등록 domain이 없으면 `domain: "unclassified"`를
유지하고 모델이 제안한 새 이름을 `proposed_domain`에 넣는다(domain 생성은 curator
권한).

## 사용자 승인, 그다음 제출

살아남은 각 후보를 간결하게 surfacing한다 — 교훈, type, intended layer,
admission-bar 판정, domain(+ proposed_domain) — 그리고 사용자가 명시적으로
승인한 것만 기록한다.

명시적 corpus bridge를 사용하는 Codex 앱 작업에서는 응답의 `runtime`에 있는
`learn` 명령·환경 또는 등록된 helper를 사용한다. 이전 앱 도구 호출의 shell export는
다음 호출에 유지되지 않는다.

런처에서 활성화한 세션에서는 아래처럼 전달받은 `AGENT_BIOS_PACKAGE_ROOT`의 `learn`을
실행한다. 활성화된 세션 밖에서는 설치된 `agent-bios` 실행 파일의 경로를 확인하고
그 실행 파일의 `learn` 하위 명령을 사용한다.

승인된 각 learning을 deterministic submit tool로 제출한다. 세션의 `--host`를
넘기고 **semantic payload만** 하나의 JSON 객체로 stdin에 넘긴다
(`supporting_sessions`의 tool prefix — `claude:` 또는 `codex:` — 를 host에 맞춘다):

    echo '{"lesson":"…","domain":"builder-base","supporting_sessions":["<tool>:<session-short-id>"],
           "criteria":["recurrent_error"],
           "classification":{"type":"B","layer":"hook","meets_bar":true}}' \
      | bash "$AGENT_BIOS_PACKAGE_ROOT/install.sh" learn --host <claude|codex>

스크립트(capability boundary)가 `learning_id` / `created` / `schema_version`를
생성하고 `learn/learning.schema.json`에 따라 검증한다. 기록은 개인 corpus의
`learnings/<host>/events.jsonl`에 추가하며 Claude와 Codex의 기록을 구분한다.
선택한 교훈은 개인 corpus를 통해 이후 활성화되는 세션의 스냅샷에 포함된다.
기록 시 사용자의 전역 지침 파일과 실행 중인 세션의 스냅샷은 보존한다.
전송이 설정되어 있으면 로컬 저장을 마친 뒤 업로드한다.
개인 저장 루트는 `$AGENT_BIOS_CORPUS_DIR`이며 기본값은
`~/.config/agent-bios/corpus`이다. 호스트의 설정 홈을 바꿔도 이 위치는 바뀌지 않는다.
`--config-dir`는 명시적인 레거시 모드에서만 허용된다. 로컬에만 기록하려면
`--no-upload`를, 쓰기와 업로드 없이 검증하려면 `--dry-run`을 사용한다.

`learning_id` / `created` / `schema_version`를 **절대** 손으로 쓰지 말고, 그
파일들을 직접 쓰지 말라. 스크립트가 record를 REJECT하면 semantic payload를 고쳐라
— validation을 우회하지 말라.

## Scope (v1)

- Single-session 포착만; cross-session mining은 `distill!`(curator).
- Mechanization(hook/gate/enforcement)은 curation으로 미룸 — 의도만 기록, 만들지 않음.
- Type-G principle 제조는 curator 전용.
- Transport(조직 업로드)는 로컬 기록 후 best-effort로만 실행된다:
  `~/.config/agent-bios/{ingest-url,token}` 슬롯이 설정된 경우에만 동작하며, 그
  슬롯이 유일한 소스다. 기본 설치는 아무것도 설정하지 않으므로 어떤 것도 머신을
  떠나지 않는다; 조직은 자기 wrapper를 통해 슬롯을 채운다.
