---
guide_id: session-distill-workflow
language: ko
status: active
audience: author
use_when:
  - Session distill preset(mission-injected)로 세션이 실행됐을 때
  - launcher nudge가 mining window에 충분한 세션이 쌓였다고 알릴 때
  - LLM 작업 세션의 경험으로 corpus와 그 적용을 개선할 때
  - session-distill ledger의 item을 promote·incubate·retire할 때
core_rules:
  - 상태 파일이나 pipeline 작업 전에 목표와 원하는 결과를 읽고 실행과 위임 작업의 판단 기준으로 삼는다
  - ledger가 상태의 SSOT다; pipeline을 건드리기 전에 먼저 읽는다
  - placement는 PLACEMENT-FRAMEWORK.md를 따른다, ad-hoc 판단은 쓰지 않는다
  - 모든 promotion은 명시적 사용자 승인 gate를 통과한다
  - round당 global growth는 측정된 gate로 hard-cap된다(~500 token)
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

**Requires an agent-bios checkout.** 이 runbook은 corpus 자체를 편집하므로 repo
경로를 지목하고 repo 스크립트를 실행한다. packaged install에는 그것들이 없으니,
실행할 수 없는 단계를 따르는 대신 그렇다고 말하고 멈춘다.

session-distill 실행을 위한 runbook: 최근 main-context 세션을 mining하고, candidate를 검증하고, framework를 통해 배치한 뒤 사용자와 함께 적용한다. 지속되는 모든 것은 agent-bios repo에 있다.

## 다음으로 읽기 (SSOT)

1. `design/session-distill/ledger.json` — initiative의 상태. 모든 item이 status(placed / incubating / incubating-G / absorbed / adopted-no-text)와 strength, provenance를 들고 있으므로 무엇이 열려 있고 무엇이 promote됐고 무엇이 아직 incubating인지는 전부 이 파일에 대한 query다. 상태는 여기서만 읽는다: 산문에 적힌 수치나 상태는 적은 날에만 맞고 그 뒤로는 조용히 틀린다.
2. `design/session-distill/versions.json` — 닫힌 mining window가 어느 commit에 대응하는지, 따라서 rollback이 무엇을 되돌리는지.
3. `design/session-distill/PLACEMENT-FRAMEWORK.md` — placement authority(typology A–G, layer, admission bar, lifecycle).

## Stage 1 — Mine (pipeline in `session-distill/`)

현재 수집기는 Claude Code와 Codex의 세션 기록을 읽는다.
순서대로 실행한다; 각 단계는 이전 단계의 `out/`을 읽는다:

1. `census.py --end YYYY-MM-DD` — 두 provider의 history.jsonl에서 열거한다; transcript-side provenance(dispatched = Codex source=exec / Claude sidechain/sdk-cli/agentId)로 직접 처리된 main-context 세션만 남긴다.
2. `digest.py` — 세션당 secret-redacted digest 하나에 deterministic 6-criteria signal을 담는다. 모든 digest를 screen한다; triage는 order를 매기되 버리지 않는다.
3. `batch.py` — baseline blob(`claude/CLAUDE.md` + 모든 guide, 레포의 canonical corpus)과 provider별 batch를 만든다; screener가 `args`로 받는 `out/batch_index.json`을 쓴다.
4. 그 baseline에 대한 provider-affine screening: `screen-claude.js`(Claude 세션; Workflow script — index를 `args`로 넘기고 batch당 WORKHORSE screener 하나)와 `screen-codex.py`(Codex 세션; batch당 hermetic read-only `codex exec` 하나, packet은 stdin). novelty는 memory가 아니라 real baseline text에 대해 판단한다. 이어서 `collect.py`가 두 출력을 `out/candidates-all.json`으로 합치고, provider의 screened set이 batch보다 작으면 실패한다.
5. `consolidate.js`(Workflow; `args` = baseline, candidates 경로, 개수, ledger의 `{id, lesson}` 목록) — dedup과 독립적인 novelty 검증, 이어서 어떤 survivor가 기존 ledger entry의 재발인지 이름 붙이는 match pass. strength(recurrence × materiality)로 순위를 매기고, 자기 보고된 confidence로는 매기지 않는다. 반환값을 `out/consolidated.json`으로 저장한다.
6. `bundle_final.py` — tiered bundle. `merge-ledger.py --window-end <date>`(dry-run; `--apply`가 쓴다)가 survivor를 `ledger.json`에 merge한다: 재발은 그 window의 세션을 `recurrence` 아래에 얻고, 새 lesson은 `candidate` entry가 된다 — 그래서 recurrence가 window를 가로질러 누적되고 incubated item은 재발생하면 promote된다.

## Stage 2 — Review with the user

- 한국어 review edition을 로컬 repo 파일로 만든다(이 사용자는 web artifact render에 접근할 수 없다): item별로 principle, 선택된 이유, verdict, placement 추천을 안정적인 ID와 함께 담는다.
- 결정은 순서대로: ① promotion bar(recurrence ≥2 또는 단일 이벤트 high materiality — irreversible / verification-corrupting / security)에 대한 selection; ② PROPOSED resolution(절대 조용히 resolve하지 않는다); ③ G-candidate 채택. 모든 결정을 ledger에 기록한다.

## Stage 3 — Classify and apply (§P8)

- 승인된 각 item을 framework pipeline으로 진행시킨다: type(A–G) → leftward reformulation(fact→principle, knowledge→structure) → layer → consumer check(hermetic dispatch와 script는 prose를 읽지 않는다) → admission bar → token 추정. 모호함은 사용자를 위해 PROPOSED로 남긴다.
- canonical-first로, branch에서, 단계별 commit으로 적용한다: canonical guide text → 측정된 budget gate 아래의 global 편집(net growth ≤ round당 ~500 token; overflow는 조용히 미루지 않고 guide로 재라우팅한다) → 다른 guide → hook(주입된 text는 canonical guide에서 도출한다; read-only, 절대 blocking하지 않는다) → owned wrapper의 enforcement(loud failure; stdout/stderr channel contract를 유지한다) → codex/ + ko/ mirror.
- diff만이 아니라 layer별로 검증한다: enforcement/gate fixture test(non-vacuous — known-bad는 반드시 fire해야 한다), hook trigger positive/negative set, `gates/check-parity.sh` unpiped exit 0, prompting-target gate, 그다음 `agent-bios install`로 활성화하고 재검증한다.

## Stage 4 — G-pass (principles, not directives)

- 사용자 correction turn(digest에 대한 deterministic marker extraction)과 initiative-arc retrospective를 mining한다; 새로 배치된 directive에 대한 upward distillation을 추가한다(≥3개가 하나의 value를 공유하면 parent-principle candidate).
- G의 evidence bar는 더 높다: ≥3개의 독립적이고 일관된 resolution, 또는 사용자가 확인한 arc retrospective 1개. principle은 tension, ordering, 금지하는 것을 명명해야 한다. under-applied gap(rule은 있지만 behavior가 따르지 않음)에는 prose 반복이 무효다 — behavior battery 목록에 올리고 surface를 대신 바꾼다.

## Stage 5 — Close the window

1. Ledger: 상태를 placed(구현 경로 포함) / incubating으로 바꾼다; 반박된 것에는 날짜를 붙인 정정을 남긴다.
2. HANDOFF: 완료 기록, 우발적 발견은 next-window candidate로 남긴다.
3. corpus version을 등록한다: {version = window 종료일, commit = corpus 마감 commit}을 `design/session-distill/versions.json`에 append한다 — launcher의 Versions & rollback 화면이 제공하는 목록이 바로 이것이다 — 그 다음 `python3 session-distill/update-state.py --window-end <date>`(nudge baseline)와 `corpus-state.py project`(launcher 상태 패널)를 실행한다.
4. branch를 merge하고, push하고, 배포된 상태를 확인한다(`agent-bios verify`).
