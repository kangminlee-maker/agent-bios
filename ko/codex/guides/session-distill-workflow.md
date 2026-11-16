---
guide_id: session-distill-workflow
language: ko
status: active
audience: author
use_when:
  - Session distill preset(mission-injected)로 세션이 실행됐을 때
  - launcher nudge가 mining window에 충분한 세션이 쌓였다고 알릴 때
  - LLM 작업 세션의 경험으로 instructions와 그 적용을 개선할 때
  - session-distill ledger의 item을 promote·incubate·retire할 때
core_rules:
  - 상태 파일이나 pipeline 작업 전에 목표와 원하는 결과를 읽고 실행과 위임 작업의 판단 기준으로 삼는다
  - ledger가 상태의 SSOT다; pipeline을 건드리기 전에 먼저 읽는다
  - placement는 PLACEMENT-FRAMEWORK.md를 따른다, ad-hoc 판단은 쓰지 않는다
  - 모든 promotion은 명시적 사용자 승인 gate를 통과한다
  - canonical always surface는 20 KiB까지만 허용한다; distill은 여기서 삭제와 병합만 제안하며, 추가할 내용은 guide, skill 또는 세션 주입에 둔다
  - window를 닫을 때 mirror, parity, 배포, nudge baseline을 갱신한다
---

# Session-Distill Workflow

## 목표와 원하는 결과 — 가장 먼저 읽기

사용자가 직접 진행한 LLM 작업 세션의 경험에서 학습하여,
사용자와 이후의 에이전트가 배운 내용을 정확히 이해하고 설명하며,
관련 상황에 적절히 적용할 수 있게 한다. 이를 통해 사용자의 목표와
우선순위에 맞게 작업의 품질, 신뢰성, 시간과 비용을 개선한다.

이 목표는 LLM 제공자나 사용 도구에 관계없이 적용되며, 향후 추가되는
도구도 포함한다. 현재 지원하는 수집 출처는 Stage 1에 명시한다.

학습 대상에는 성공한 접근, 실수와 수정, 반복되는 어려움, 영향이 큰
예외, 선택의 이유가 포함된다. 기존 지식과 비교해 빠진 내용을 보완하고,
부정확한 내용을 명확히 하거나 수정하며, 적용되지 않는 지식의 활용을
개선하고, 잘 작동하는 내용은 유지한다. 신규 후보를 찾는 screener의
결과는 이 목표를 위한 입력이다. 후보 목록만으로 답할 수 없는 질문은
남아 있는 세션 근거로 확인한다.

한 번의 실행에서 원하는 결과는 다음과 같다.

1. **근거 있는 학습.** 무슨 일이 있었고, 무엇을 배웠으며, 어떤 근거가
   이를 뒷받침하고 어디까지 확실한지 설명한다. 관찰한 사실, 해석,
   미해결 불확실성을 구분하고 세션 근거를 추적할 수 있게 한다.
2. **이해하고 재사용할 수 있는 내용.** 학습 내용과 이유, 적용 조건과
   한계를 명시한다. 판단 원칙은 충돌하는 가치와 사용자의 우선순위를
   설명한다. 일반화하면 유용한 의미가 사라지는 구체적 사실이나 절차는
   그 내용을 보존한다.
3. **의미와 적용에 대한 검증.** 학습 내용이 정확하게 설명되고 근거로
   뒷받침되는지, 관련 판단과 행동에서 적절히 적용되는지를 모두 확인한다.
   기대 효익과 원치 않는 영향을 살피며, 이미 적절한 결정을 유지하는 것도
   좋은 결과일 수 있다. 근거와 영향에 비례해 검증하고, 관찰하거나
   시험한 효과와 아직 제안인 효과를 구분한다. 시험하지 않은 후보도
   검토 대상으로 남길 수 있다. 유창한 설명이나 한 번의 적절한 행동만으로
   두 가지가 모두 검증됐다고 판단하지 않는다.
4. **사용자가 검토할 수 있는 제안.** 기존 규칙과의 관계, 처리 방향과
   원본을 둘 위치, 실제 사용할 주체, 기대 효익과 비용, 남은 검증을
   제시한다. 사용자가 채택·수정·유지·보류·폐기를 결정할 맥락을 제공한다.
5. **승인된 변경의 지속 가능한 반영과 검증.** 승인된 학습을 placement
   framework에 따라 guide, principle, memory, 도구 수정, gate 등 실제
   사용 주체에게 도달하는 기존 수단에 반영한다. 근거와 결정은 ledger에
   보존하고, 반영·검증된 내용과 미해결 사항을 보고한다. 검토 가능한
   제안과 적용된 변경은 서로 다른 결과이며, promotion에는 계속해서
   명시적인 사용자 승인이 필요하다.

성공은 유용하고 타당한 학습과 적절한 적용으로 판단한다. 후보 수나
늘어난 문장의 양은 산출물의 분량을 나타낸다. 기존 내용을 유지한다는
근거 있는 결정이나 범위가 명확한 미해결 발견도 유용한 결과다.
위임 작업에도 이 목표와 해당 단계의 결과 기준을 전달하고, 실행 완료를
보고하기 전에 그 기준으로 결과를 검토한다.

**Requires an agent-bios checkout.** 이 runbook은 instructions 자체를 편집하므로 repo
경로를 지목하고 repo 스크립트를 실행한다. packaged install에는 그것들이 없으니,
실행할 수 없는 단계를 따르는 대신 그렇다고 말하고 멈춘다.

session-distill 실행을 위한 runbook: 최근 main-context 세션을 mining하고, candidate를 검증하고, framework를 통해 배치한 뒤 사용자와 함께 적용한다. 지속되는 모든 것은 agent-bios repo에 있다.

## 다음으로 읽기 (SSOT)

1. `design/session-distill/ledger.json` — initiative의 상태. WP-22 cutover 이후 schema 2다. entry의 `status`는 incubating / placed / adopted-no-text / absorbed / retired 중 하나이고, 이력은 `decisions[]`, 유형은 `classification.type`이다. 그래서 무엇이 열려 있고 무엇이 promote됐고 무엇이 아직 incubating인지는 전부 이 파일에 대한 query다. 상태는 여기서만 읽는다: 산문에 적힌 수치나 상태는 적은 날에만 맞고 그 뒤로는 조용히 틀린다. schema 1의 `verdict`, `strength`, `criteria`는 entry에서 사라졌다 — `criteria`는 `consequence.kinds`가 됐고, 떨어뜨린 값들은 날짜가 박힌 이행 기록에 적혀 있으며 파일에서는 되살릴 수 없다. ledger를 읽는 쪽은 `runlib/ledger.py`이고 스키마는 `session-distill/schemas/ledger.schema.json`이다.
2. `design/session-distill/versions.json` — 닫힌 mining window와 해당 commit을 연결하는 저작 provenance. Private rollback은 instructions plan에서 설치된 `baseline_ref`를 선택하며, 이 registry가 그 선택의 기준은 아니다.
3. `design/session-distill/PLACEMENT-FRAMEWORK.md` — placement framework(typology A–G, layer, admission bar, lifecycle). 위치를 고를 때는 현재 `AGENTS.md`의 canonical always surface 상한과 `SURFACES.md`의 전달 계약을 적용한다. 이 framework가 global 파일에 내용을 추가하도록 허용하지는 않는다.

## Stage 1 — 드라이버를 실행한다 (`session-distill/distill.py`)

한 run, 한 run 디렉터리, stage마다 subcommand 하나. 여기 있던 v1 pipeline — 세션별 digest,
batch, provider별 screener 둘, union, consolidation, bundle — 은 WP-22 cutover에서 삭제됐고
드라이버가 그 자리를 대신한다. 모든 stage는 `<run root>/<run-id>/` 아래에 쓴다. run root는
`--out`이고, 주지 않으면 드라이버가 XDG state 디렉터리로 해석한다. **이 checkout 안을 run
root로 주면 거부된다** — `inventory`는 checkout을 무조건 보호하고, 아무것도 쓰기 전에
`PROTECTED_OVERLAP`으로 끝낸다. 그것이 보호가 작동하는 모습이다: run은 소유자의 세션 기록
복사본을 쓰고, 저장소는 그것을 둘 자리가 아니다. 그래서 `--out`을 주지 않고 드라이버가 XDG
state 디렉터리를 해석하게 두거나, 보호된 어떤 root(checkout, 소유자 state root, `~/.claude`,
`~/.codex`)에도 들지 않는 디렉터리를 준다.

**S8을 뺀 모든 stage가 실행되며, 실행되지 않는 것은 대충 비슷한 일을 하는 대신 이름을 대고
거부한다.** stderr에 `STAGE_NOT_IMPLEMENTED <command> (<stage>)`, 종료 코드 2.
아래 표는 설계가 아니라 이 checkout이 오늘 하는 일이다:

| Stage | 명령 | 오늘 |
| --- | --- | --- |
| S0 | `distill.py declare --run-id ID --from DECLARATION.json` | 실행된다; stage가 읽기 전까지는 `--set PATH=VALUE`로 고치고, 그 뒤에는 `--amend --reason TEXT` |
| S1 | `distill.py census --run-id ID --coverage session-distill/local/coverage.json` | 실행된다; `--reconcile RESULTS.json`은 S3의 결과를 status와 coverage로 되돌려 접는다. `--coverage`는 마지막 periodic close가 올린 상태를 가리키고, declaration의 `starting_hashes.coverage`가 그 sha256을 고정한다(다르면 `COVERAGE_BASE_STALE`). 빼면 census는 추적되는 `session-distill/coverage.json`, 곧 periodic close가 한 번도 쓰지 않은 checkout의 빈 상태를 읽는다 |
| S2 | `distill.py views --run-id ID` | 실행된다: 불변 복사본, redaction projection, window, 검색 index, evidence store |
| S2 | `distill.py inventory --run-id ID --ledger design/session-distill/ledger.json` | 실행된다: reference point별 unit. ledger 경로는 부르는 쪽이 이름을 댄다 |
| S3 | `distill.py read --run-id ID --dry --checkout-ledger design/session-distill/ledger.json` | 실행된다: 모든 window packet을 재고, 호출은 하지 않으며, record는 partial로 남는다 |
| S3 | `distill.py read --run-id ID --cells DIR --checkout-ledger design/session-distill/ledger.json [--tranche calibration] [--jobs N] [--golden-plan PLAN.json]` | 실행된다: window 읽기와 stitch를 supervisor를 거쳐 수행한다. live(token은 `CLAUDE_RUN_TOKEN_FILE`로만) 또는 plan을 준 golden |
| S4 | `distill.py form --run-id ID --dry --checkout-ledger design/session-distill/ledger.json` | 실행된다: barrier, lifecycle intake, 한도에 맞춘 packet까지; record는 partial |
| S4 | `distill.py form --run-id ID --cells DIR --checkout-ledger design/session-distill/ledger.json [--golden-plan PLAN.json]` | 실행된다: formation 호출 한 번. live(token은 `CLAUDE_RUN_TOKEN_FILE`로만) 또는 plan을 준 golden |
| S5 | `distill.py retrieve --run-id ID --checkout-ledger design/session-distill/ledger.json` | 실행된다: 코드만으로 후보별 검색된 unit, lineage, check를 만들고 planted control을 함께 둔다 |
| S5b | `distill.py deliver --run-id ID` | 실행된다: 코드만으로 (session, unit, decision)마다 그 unit이 전달됐는지 답한다. session을 하나도 가리키지 않는 후보의 짝은 따로 센다(`not_session_derived`) |
| S6 | `distill.py judge --run-id ID --checkout-ledger design/session-distill/ledger.json --dry`, 그다음 `--dry` 대신 `--cells DIR [--golden-plan PLAN.json]`을 준 같은 명령 | 실행된다: 후보마다 judge 둘을 supervisor를 거쳐 부르고 derivation을 만든다 |
| S7, S7b | `distill.py propose --run-id ID --checkout-ledger design/session-distill/ledger.json`에 `--dry`, `--cells DIR [--golden-plan PLAN.json]`, 또는 손에 든 답(`--answers ANSWERS.json`); 그다음 `distill.py review-proposals --run-id ID`에 `--dry`, `--cells DIR [--golden-plan PLAN.json]`, 또는 `--reviews REVIEWS.json` | 실행된다: S6가 받아들인 후보마다 proposal 하나를 받아 contract와, S11이 그 operation에서 거부할 것에 비춰 확인한다. 두 번째 seat가 모델이 쓴 proposal을 각각 검토한다. release 1에서는 library 파일을 바꾸게 될 proposal이나 대안이 이름을 걸고 거부된다(`RELEASE_1_NO_LIBRARY_CHANGE`) |
| S8 | `distill.py test` | 거부되고, **release 1에서는 계속 거부된다: S8은 이름을 걸고 release 2로 미뤄졌다(D-20261111-818391).** 적용한 변경이 도움이 됐는지는 어떤 run도 시험하지 않는다. 시험 결과가 들어갈 row는 `untested: s8_deferred`라는 이름 붙은 상태를 가진다 |
| S9, S9b | `distill.py render --run-id ID --checkout-ledger design/session-distill/ledger.json`, 그다음 `distill.py review-korean --run-id ID --cells DIR` | 실행된다: run 디렉터리에 한국어 검토 파일 `decisions.ko.v<n>.md`를 만들고, 그 한국어가 proposal과 일치하는지 확인한다. S8이 없으므로 순서는 judge와 S7b로 물러나고 header가 그 사실을 적는다. header는 S6 뒤에 심어 둔 대조군 중 몇 개가 기대한 판정을 받았는지도 적고, 그 평가는 `review.v<n>.json`에 기록된다. 어긋난 대조군은 보여 줄 뿐 실행을 멈추지 않는다(D-20261115-18d56b) |
| S10, S10b | `distill.py parse-decisions --run-id ID`, `distill.py adjudicate --run-id ID --cells DIR`(소유자가 `판정`을 적었을 때), `distill.py confirm --run-id ID`, 그다음 `distill.py confirm --run-id ID --decide` | 실행된다: 소유자가 고친 사본에서 결정을 읽고, adjudication을 다시 계산하고, 최종 집합을 만들고, 소유자의 확인 줄을 읽는다. release 1에서는 library 파일을 바꾸는 항목이 든 최종 집합이 소유자가 확정하기 전에 이름을 걸고 거부된다 |
| S11 | `distill.py apply --run-id ID` | 실행된다: **release 1에서는 library 파일을 하나도 쓰지 않는다(D-20261116-7853bc).** 변경이 든 확정 집합은 계획이나 쓰기 전에 이름을 걸고 거부되고(`RELEASE_1_NO_LIBRARY_CHANGE`), 아무 파일도 바꾸지 않는 집합은 그렇게 기록되며 명령은 출력하지 않는다. git도, installer도, personal layer도 건드리지 않는다 |
| S12 | `distill.py close --run-id ID --checkout-ledger design/session-distill/ledger.json --checkout-coverage session-distill/local/coverage.json` | 실행된다: window와, 기존 ledger entry에 대한 결정을 checkout의 ledger에 기록하고(ledger entry가 없는 새 후보의 `none`은 ledger 줄을 만들지 않고 run의 `close.json`에만 남는다, F-40), periodic run이면 coverage 상태를 지정한 파일로 올린다. 명령에 적힌 대로, git이 무시하는 `session-distill/local/` 아래 파일을 지정한다: 이 상태는 session id로 키가 매겨지므로 git 밖에 둔다. periodic close에서 이 인자를 빼면 거부된다(`COVERAGE_UNNAMED`). 보고에는 S9가 기록한 대조군 평가가 그대로 실린다. process를 실행하지 않으며 소유자에게 남기는 일을 이름으로 적는다: commit, install, launcher 상태, version registry 줄. `--recovery`는 예약되어 있다 |

**release 1의 run이 내놓는 것.** window에 대한 증거, 그에 대한 소유자의 검토, 소유자가 결정한 것의
기록이다. **release 1은 library 파일을 바꾸지 않는다(D-20261116-7853bc).** 파일을 바꾸게 될 처리 -
`place`, `correct`, `re-deliver`, `reduce` - 와 모든 operation은 S7과 S7b가 답을 받는 곳, S10b가
최종 집합을 만드는 곳, S11이 항목을 가져가는 곳에서 이름을 걸고 거부된다(`RELEASE_1_NO_LIBRARY_CHANGE`).
어떤 종류의 후보든 `keep`, `incubate`, `drop`, `none` 가운데 답이 남는다. 증거가 library 파일의 변경을
뒷받침하면 proposal이 그 변경을 한국어 이유에 적어 소유자가 읽게 한다. 그 처리들을 다시 여는 일은
release 1을 발행한 뒤의 쓰기 경로 재설계를 기다린다. 변경이 도움이 될지는 아무것도 시험하지 않는다:
그것은 release 2의 S8이다. run은 선언된 checkout의 ledger(S12)와, periodic run이면 지정한 coverage
파일을 바꾸며, commit과 install과 publish는 소유자가 한다.

실행되는 stage가 실제로 실행된다는 증거는 드라이버 자신의 suite인
`python3 session-distill/distill.py --self-test`(실제 파일 위에서 declare → stage → amend →
stage)와 모듈 suite `python3 session-distill/runlib/<name>.py --self-test`다. 모듈 suite는
패키지 사용자의 것이 아니라 checkout의 도구다.

드라이버의 stage는 아니지만 여전히 실행되는 저자측 window 도구: `census.py`(v1 window
census), `plain-asks.py`, `update-state.py --window-end <date>`(launcher의 nudge baseline).
`migrate-ledger.py`는 ledger의 schema 1 → 2 이행이며, 한 번 수행하고 그 뒤로는 멱등이다.

`merge-ledger.py`는 v1 window 흐름에 속하고 **이 workflow의 일부가 아니다.** 그것은 schema 1의
필드 — 최상위 `window`, 항목별 `strength`와 `supporting_sessions` — 를 쓰는데 schema 2에는 그런
필드가 없다. 그래서 이행된 ledger에 돌리면 schema가 더는 설명하지 않는 문서를 남긴다. 지금은
schema 1이 아닌 ledger를 이름을 대고 거부한다(`LEDGER_SCHEMA_UNSUPPORTED`), 읽기도 쓰기도 전에.
이행 뒤의 window는 lifecycle intake가 접어 넣는다.

## Stage 2 — Review with the user

- 한국어 review edition을 로컬 repo 파일로 만든다(이 사용자는 web artifact render에 접근할 수 없다): item별로 principle, 선택된 이유, verdict, placement 추천을 안정적인 ID와 함께 담는다.
- 결정은 순서대로: ① promotion bar(recurrence ≥2 또는 단일 이벤트 high materiality — irreversible / verification-corrupting / security)에 대한 selection; ② PROPOSED resolution(절대 조용히 resolve하지 않는다); ③ G-candidate 채택. 모든 결정을 ledger에 기록한다.

## Stage 3 — Classify and apply (§P8)

- 승인된 각 item을 framework pipeline으로 진행시킨다: type(A–G) → leftward reformulation(fact→principle, knowledge→structure) → layer → consumer check(hermetic dispatch와 script는 prose를 읽지 않는다) → admission bar → token 추정. 모호함은 사용자를 위해 PROPOSED로 남긴다.
- canonical-first로, branch에서, 단계별 commit으로 적용한다: canonical guide text → canonical always surface 축소(규칙 삭제·병합·이동만 허용하며 추가 내용은 guide, skill 또는 세션 주입에 둔다) → 다른 guide → hook(주입된 text는 canonical guide에서 도출한다; read-only, 절대 blocking하지 않는다) → owned wrapper의 enforcement(loud failure; stdout/stderr channel contract를 유지한다) → codex/ + ko/ mirror.
- diff만이 아니라 layer별로 검증한다: enforcement/gate fixture test(non-vacuous — known-bad는 반드시 fire해야 한다), hook trigger positive/negative set, `gates/check-parity.sh` unpiped exit 0, prompting-target gate, 그다음 이 checkout에서 `bash install.sh install`로 변경된 private release를 저장하고 `bash install.sh verify`로 확인한다. `agent-launch`에서 새 configured session을 활성화하고 전달 근거를 따로 확인한다. 설치는 content를 활성화하거나 기존 세션의 pin을 바꾸지 않는다.

## Stage 4 — G-pass (principles, not directives)

- 사용자 correction turn(digest에 대한 deterministic marker extraction)과 initiative-arc retrospective를 mining한다; 새로 배치된 directive에 대한 upward distillation을 추가한다(≥3개가 하나의 value를 공유하면 parent-principle candidate).
- G의 evidence bar는 더 높다: ≥3개의 독립적이고 일관된 resolution, 또는 사용자가 확인한 arc retrospective 1개. principle은 tension, ordering, 금지하는 것을 명명해야 한다. under-applied gap(rule은 있지만 behavior가 따르지 않음)에는 prose 반복이 무효다 — behavior battery 목록에 올리고 surface를 대신 바꾼다.

## Stage 5 — Close the window

1. Ledger: 상태를 placed(구현 경로 포함) / incubating으로 바꾼다; 반박된 것에는 날짜를 붙인 정정을 남긴다.
2. `AGENTS.md` 형식에 따라 `design/session-distill/`에 timestamp가 있는 새 완료 기록을 쓴다. 우발적 발견은 next-window candidate로 남긴다.
3. instructions version을 등록한다: {version = window 종료일, commit = instructions 마감 commit}을 `design/session-distill/versions.json`에 append하여 저작 provenance를 남긴다. Private rollback은 `agent-bios instructions plan`에서 설치된 `baseline_ref`를 선택하며 이 window registry가 전역 파일 rollback을 허용하지는 않는다. 그 다음 `python3 session-distill/update-state.py --window-end <date>`(nudge baseline)와 `instructions-state.py project`(launcher 상태 패널)를 실행한다.
4. branch를 merge하고, push하고, 이 checkout의 private release를 확인한다(`bash install.sh verify`). 저장 상태와 세션 전달의 근거는 따로 보고한다.
