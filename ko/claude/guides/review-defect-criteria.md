---
guide_id: review-defect-criteria
language: ko
status: active
use_when:
  - review를 dispatch하기 전에 무엇이 결함인지 선언할 때
  - 시스템 유형 × 작업 목표에 맞는 defect criterion을 고르거나 새로 쓸 때
  - review loop이 고원에 걸리거나 발산하거나 "material 0" 종료가 오지 않을 때
  - finding의 class가 경계에서 다투어지거나 두 lens가 다르게 분류할 때
core_rules:
  - review 시작 전에 criterion을 고르고 선언한다 — 선언하지 않으면 reviewer마다 자기 기준을 쓴다
  - severity ladder는 얼마나 나쁜지를, criterion은 결함인지·어느 class인지·"0"을 무엇 위에서 세는지를 답한다
  - 빈 칸이 있는 criterion은 기준이 아니라 감이다 — review를 시작하지 않는다
  - golden을 packet에 그대로 붙인다; 정의만으로는 경계에서 일관되게 분류되지 않는다
  - class enum은 수용 채널에 둔다 — schema가 있으면 schema에, prose route면 fold 절차를 돌린다
  - 혼합 packet은 쪼갠다 — 한 궤적에 두 관찰자를 돌리지 않는다
verification_focus:
  - dispatch되는 모든 packet이 criterion을 이름으로 선언하고 golden을 싣는다
  - 라운드마다 보고된 class를 실측 후 확정 class와 대조한다; 반복되는 불일치가 다음 golden이다
  - 종료 조건은 전체 finding 수가 아니라 stop-relevant class 위에서만 평가한다
---

# Review Defect Criteria

defect criterion은 가정하는 것이 아니라 고르는 것이다. 이 guide는
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/review-request.md`의 범위 확장이다: 그
guide의 요청 작성이 시작되기 전에, 이 guide가 review가 무엇을 사냥하는지를 정한다.
근거: 같은 codebase, 두 종료 기준, 정반대 궤적.

| 구간 | 기준 | 궤적 |
|---|---|---|
| 초반 | material = 계약 위반 **또는** 보호되지 않는 계약 문장, 작고 동결된 표면 | 10 → 4 → 1 → 0 |
| 후반 | 같은 기준, 클라이언트 관찰 가능 범위로 축소 | 17 → 19 → 21 → 23 → 19 — **고원** |
| 최종 | class 분리: behavioral_defect / coverage_gap / doc_gap; 종료 = behavioral 0 | behavioral 10 → 5 — 다시 감소 |

고원의 원인은 코드가 아니라 기준이었다: "테스트가 보호하지 않는 계약 문장"을 결함으로
세면 매 수정이 계약에 행을 추가하고, 그 행 하나하나가 다음 라운드의 잠재 결함이다 —
자기보충 기준은 표면이 성장하는 한 0에 도달할 수 없다. 그런데 그 기준은 라이브러리에는
정확히 맞다. 거기서는 보호되지 않는 약속이 1급 결함이다. 어느 쪽도 틀리지 않았다;
고르지 않고 시작한 것이 틀렸다.

**severity ladder**(`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/coding-staged-workflow.md`)는
finding이 *얼마나 나쁜지*를 답한다. **criterion**은 그것이 애초에 결함*인지*, 어느
class인지, "0"을 무엇 위에서 세는지를 답한다. 위의 고원은 전부 "material" 안에서
일어났다 — severity를 조정해서는 끝낼 수 없었다. 순서: 시스템 유형 + 목표 → defect
criterion → 분류 → 결함? → severity → materiality → 종료 판정.

## Criterion 스키마

항목 하나는 아래 전부를 갖는다. 빈 칸이 있으면 기준이 아니라 감이다 — 그 위에서
review를 시작하지 않는다.

| 필드 | 뜻 |
|---|---|
| 관찰자 | 누구의 눈으로 판정하나 — 클라이언트, 호출자, 운영자, 출력을 읽는 모델 |
| 결함 | 관찰자가 무엇을 겪어야 하나 |
| class | 분류 enum, 정확히 하나만 stop-relevant; 나머지는 stop class를 정직하게 유지하는 배출구다 |
| 증거 | finding 하나가 무엇을 제시해야 하나 |
| 비결함 | 결함처럼 보이지만 이 기준에서 제외되는 것 — 명시적으로 |
| 종료 조건 | "0"이 무엇을 뜻하나 — stop class 위에서 세고, 왜 도달 가능한지(성장하는 표면을 어떻게 고정했는지) |
| 오분류 비용 | 어느 오류가 비싼가 — reviewer에게 어느 쪽으로 기울라고 말할 근거 |
| golden | 양성 2+ · 음성 2+ · 경계 1+; 각각 왜 + 날짜 + 출처 라벨: `measured`(날짜 있는 실사례) 또는 `constructed`(경계를 고정하려고 작성) |

## 카탈로그

시스템 유형 네 가지. 시작점이지 전부가 아니다.

### 웹서비스 / API 표면 (계약 준수형)

- **관찰자**: HTTP 클라이언트.
- **결함**: 오늘 클라이언트가 계약과 다른 응답을 받는다 — 상태코드, 봉투, 스트림 터미널 프레임, 실제 실행되는 모델, 격리, 자원 상한.
- **Class**: `behavioral_defect`(stop-relevant) · `coverage_gap` · `doc_gap`.
- **증거**: 구체적 요청과 관측된 응답 vs 약속된 응답.
- **비결함**: 내부 수명주기(요청 시퀀스로 두 다른 응답을 보이지 못하는 한), 테스트 부재 자체, 문서 문구.
- **종료**: behavioral 0 — 도달 가능: 코드 표면은 유한하고, 수정이 새 행동 결함을 만들지 않는 한 단조 감소한다.
- **오분류 비용**: false negative가 비싸다(클라이언트가 실제로 깨진다); 단 커버리지 공백을 결함으로 부풀리면 종료 조건이 무너진다 — 카테고리 팽창은 별도로 감사한다.
- **Golden** (전부 `measured`, 2026-08-13–15):
  - **+** 존재하지 않는 경로에 `GET`이 404가 아니라 405 — 있는 메서드에 대한 불평이 없는 경로에 붙었다.
  - **+** 스트리밍 endpoint의 터미널 delta가 `output_tokens`만 실어 캐시·입력 토큰 수가 스트리밍 클라이언트에 영영 도달하지 않음 — 비스트리밍은 정상이라 아무도 못 봤다.
  - **−** "이 기본값의 한 줄 뒤집기를 아무 테스트가 안 잡는다": 오늘 동작은 맞다 — 여기서는 `coverage_gap`, 라이브러리 기준에서만 결함이다.
  - **−** 자식 프로세스 종료 유예 시간 — 요청 시퀀스로 클라이언트 가시 차이를 보이기 전까지 스코프 밖; 관찰자를 클라이언트에 고정한다.
  - **±** 문서상 유효한 경계값 거부(compression 100, 문서는 "100 미만은 jpeg/webp 필요") — 문서가 있어야 결함이 된다; 그 문장이 없으면 취향이다.

### 라이브러리 / SDK / 계약-우선 시스템

- **관찰자**: 호출자 **와** 미래의 유지보수자.
- **결함**: 오늘 위반된 약속, 또는 보호되지 않는 약속 — 한 줄 수정이 깨뜨리는데 아무것도 안 잡는다. API 기준의 `coverage_gap`이 여기서는 1급이다.
- **Class**: `contract_defect`(stop-relevant) · `style_note` · `internal_change`.
- **증거**: 위반이면 위와 같음; 미보호면 약속 문장 + 깨뜨리는 한 줄 수정 + 잡는 테스트의 부재.
- **비결함**: 문체, 내부 구조.
- **종료**: 주의 — 이 기준은 계약이 성장하는 동안 자기보충된다. "0"은 성장이 멈춘 표면에만 선언한다; 성장 중이면 "이번 변경이 추가한 약속은 전부 보호됨"으로 좁힌다.
- **오분류 비용**: 균형 — 미보호를 놓치면 다음 리팩터에서 조용히 깨지고, 과잉 보고하면 루프가 안 끝난다.
- **Golden**:
  - **+** 스트리밍 이미지 이벤트 테스트가 `.completed`만 매칭 → edit 스트림이 `image_generation.completed`로 잘못 명명돼도 통과 — 뮤테이션 생존이 약속의 미보호를 보였다. (`measured`, 2026-08-13–15)
  - **+** 계약은 "저장소는 큰 이미지를 최소 1회 서빙"인데 코드는 다음 요청에 축출 — **계약을 고쳐** 해소했다: 불일치 자체가 결함이고, 어느 쪽을 움직여도 수정이다. (`measured`, 2026-08-13–15)
  - **−** 문서가 약속하지 않는 내부 헬퍼의 리네임 — 관찰자는 계약을 든다; 문서 밖 내부에는 약속이 없다. (`measured`, 2026-08-13–15)
  - **−** 문서화되지 않은 순회 순서에 기댄 호출자가 깨짐 — 약속이 없었다; 리네임 경계를 호출자 쪽에서 고정한 것. (`constructed`, 2026-08-19)
  - **±** 인벤토리에 있는 테스트가 실은 vacuous — 약속에 대해 아무것도 단언하지 않는다. "테스트가 있다"는 단언을 읽기 전까지는 이름에 대한 주장이다; reviewer에게 "이름이 아니라 단언을 확인하라"를 준다. (`measured`, 2026-08-13–15)

### AI 워크벤치 / 하네스 (에이전트 오케스트레이션, review loop, 검증 파이프라인)

- **관찰자**: 운영자, 그리고 하네스의 출력을 입력으로 받는 모델.
- **결함**: **참처럼 보이는 거짓 신호** — 잘못된 PASS, vacuous 테스트, 조용한 fallback, 호출부가 빠진 packet, 잘못된 분모. 틀린 것이 결함이 아니라 틀렸는데 *옳아 보이는 것*이 결함이다. 두 번째 형태: dispatch를 증명 못 하는 "돌았다" 주장 — 영수증 부재.
- **Class**: `false_signal`(stop-relevant) · `detected_miss`. dispatch가 증명되지 않은 실행 — 영수증 없는 실행·PASS 주장 — 은 별도 배출구를 주지 않고 `false_signal`로 분류한다: 참임을 보일 수 없는 신호는 거짓으로 센다. 아니면 모든 dispatch가 미증명인 채로 라운드가 완료를 선언할 수 있다.
- **증거**: 계기가 거짓 판정을 낸 입력과 그 입력의 알려진 정답. 표준 절차: 반대 답이 알려진 입력에 계기를 돌려 반응을 확인한다.
- **비결함**: 개별 출력의 스타일; 하네스가 스스로 **감지한** 오탐 — 잡힌 오류는 하네스가 일한 것이다.
- **종료**: 이번 실행이 낸 모든 PASS가 반대-입력 검사를 통과하고 자신의 dispatch를 증거함. 단위는 상시 0이 아니라 "이번 실행의 신호가 신뢰 가능함"이다.
- **오분류 비용**: false pass가 압도적이다. 실패를 알리는 계기 버그는 사람이 들여다보니 몇 분 안에 죽고, 통과를 알리는 계기 버그는 살아남는다 — 선택 효과다.
- **Golden**:
  - **+** 셸 테스트 러너에 존재하지 않는 경로 하나가 전달(zsh는 따옴표 없는 변수를 단어 분리하지 않는다) → 항상 exit 1 → 모든 뮤테이션이 KILLED로 보고 — 피검체를 한 번도 안 돌린 초록 계기. (`measured`, 2026-08-13–15)
  - **+** 테스트 인벤토리 grep이 `^test('...'`만 매칭해 파라미터화된 이름을 전부 누락 → reviewer 3명이 차 있는 파일을 비었다고 판단 — 인벤토리 분모를 소스 자체의 개수와 묶는 단언이 없었다. (`measured`, 2026-08-13–15)
  - **+** negative control이 자기가 겨눈 수정의 충실한 revert 후에도 계속 통과 — 부재로 충족되는 가드, gate 자체에 대한 false PASS; revert 재실행으로만 발견됐다. (`measured`, 2026-08)
  - **+** review 라운드가 "clean"을 반환했는데 선언된 packet이 정확히 그 seat에 dispatch됐다는 영수증이 없음 — 관측된 잘못이 없어도 `false_signal`이다: 종료가 거부하는 것은 거짓의 증명이 아니라 dispatch 증명의 부재다. (`constructed`, 2026-08-19, 정확히 이 경계에서의 분류 이견 뒤에 고정)
  - **−** reviewer 하나가 항목을 material로 과대 분류 → 다른 lens와 실측이 걸러냄 — 하네스가 잡았으니 하네스는 일했다: `detected_miss`, 결함 아님. (`measured`, 2026-08-13–15)
  - **−** 다섯 라운드가 8 → 9 → 10 → 5 → 12 finding을 내며 수렴을 거부 — 그리고 모든 수가 참이었다. 참인 불쾌한 신호는 거짓 신호가 아니다; 결함은 선언되지 않은 criterion에 있었다. (`measured`, 2026-08-16–17)
  - **±** 생존한 뮤테이션이 조사 결과 등가 — 플랫폼이 이미 정규화해 그 가드는 죽은 코드였다. 하네스 결함도 테스트 공백도 아니다; 단 "생존 = 공백"으로 자동 해석하는 하네스라면 그 규칙이 결함이다. (`measured`, 2026-08-13–15)

### 의사결정 ontology (모델이 그것만 보고 결정하는 ontology)

- **관찰자**: ontology만 보고 결정하는 모델/에이전트.
- **결함**: 잘못된 결정을 낳거나 옳은 결정을 막는 표현: 겹치는 개념 경계, 결정에 필요한 구분의 부재, 실제와 모순되는 인스턴스, 틀린 관계 방향·기수, 정의와 다른 것을 암시하는 이름.
- **Class**: `decision_defect`(stop-relevant) · `representation_note` · `out_of_scope_gap`.
- **증거**: **결정 시나리오** — "ontology만으로 답하면 X, 실제는 Y" — 질문·경로·실제 근거와 함께.
- **비결함**: 표현 형식, 완전성 그 자체, 모델이 ontology 없이도 틀렸을 질문.
- **종료**: 합의된 시나리오 집합에서 잘못된 결정 0. 집합이 곧 스코프다 — 먼저 고정하지 않으면 라이브러리 기준처럼 자기보충된다.
- **오분류 비용**: 상황 의존 — 하드 게이트를 먹이면 false negative가, 탐색 보조면 false positive가 비싸다. 선언 시 이 칸을 반드시 채운다.
- **Golden** (전부 `constructed`, 2026-08-19, 원 루프의 결정-시나리오 틀이 열어 둔 경계를 고정하려고 작성):
  - **+** `Customer`와 `Account`가 둘 다 "결제 주체"를 정의 → 환불 라우팅 질문이 두 경로로 풀린다 — 각 정의가 홀로 옳아도 겹침은 결정 결함이다.
  - **+** 분할 결제가 존재하는데 `Order —hasOne→ Payment` — 기수는 주장이고, 거짓 주장은 결정하는 모델을 오도한다.
  - **−** 개념 설명이 장황함 — 바뀌는 결정이 없다; 형식은 이 관찰자의 시야 밖이다.
  - **−** 합의된 시나리오가 요구하지 않는 도메인의 부재 — 완전성은 세계가 아니라 집합으로 스코프된다.
  - **±** 구분은 존재하는데 모델이 찾지 못하는 위치에 있음(이름·연결 부재) — 관찰자를 "ontology만 보는 모델"로 고정했다면 도달 불가는 표현 결함이지 검색 결함이 아니다. 관찰자 조항이 class를 정한다.

## Review 시작 전에

1. 한 문장을 쓴다: 시스템 유형과 이번 작업의 목표. ("API 표면 — 오늘 클라이언트가 받는 응답을 계약에 맞춘다." / "하네스 — 이번 실행의 PASS 신호를 신뢰 가능하게 한다.")
2. 카탈로그에서 criterion을 고르거나 스키마를 새로 채운다. 못 채우는 칸이 있으면 review를 시작하지 않는다.
3. golden을 packet에 그대로 붙인다. 정의만 넣지 않는다.
4. 종료 조건과 그것이 도달 가능한 이유 — 또는 스코프를 어떻게 고정해 도달 가능하게 만들었는지 — 를 선언한다.
5. 분류를 수용 채널에 둔다(다음 절).
6. 라운드마다 감사한다: 보고된 class vs 실측 후 확정 class. 반복되는 불일치가 다음 golden이다.

## Enum 강제 — 채널별

채널이 얼마나 대신 거부해 주는지 순으로:

1. **submit schema가 있는 route**: 분류는 필수 enum 필드다. 실측 선례는 anchor다 —
   2,466건 중 2,466건이 실었는데, schema가 없는 출력을 거부하기 때문이다. 이 채널이
   있으면 쓴다.
2. **prose-packet route** (배포되는 deep-review 방법들): packet 헤더가
   `Criterion: <이름>`을 선언하고 golden을 그대로 싣는다. 그리고 dispatch하는
   에이전트가 돌아온 결과에 이 fold 절차를 돌린다:
   1. 돌아온 각 finding 행의 class를 선언된 enum에 대조한다.
   2. enum의 class를 단 행은 그 class로 findings ledger에 들어간다.
   3. class가 없거나 enum 밖인 행은 **받지 않는다**: 분류를 위해 한 번 돌려보내거나,
      사유와 함께 거부로 기록한다. 무분류로 받지 않고, 대신 class를 추측해 주지 않는다.
   4. 종료 조건은 stop-relevant class 위에서만 센다.
   5. 감사 쌍(보고된 class, 확정 class)을 위 절차 6번을 위해 기록한다.

   정직하게 말하면: prose route에서 이것은 control이 아니라 steering이다 — fold는 이
   guide를 따르는 에이전트가 수행하고, class 없는 행을 구조적으로 거부해 주는 것은
   없다. 요청-전용 규칙이 주는 알려진 더 약한 결과다.
3. **launcher의 criterion discipline** (agent-launch): preset이 `criterion = true`를
   선언하면 core 소유의 discipline 절 하나가 모든 review method 행에 렌더된다 —
   criterion의 내용은 launch 단위 설정에 절대 들어가지 않고, 위의 prose 옆에
   `ReviewCriterion/v1:` record 한 줄로 packet에 실린다. `--compile-criterion`은
   스키마의 결정 가능한 부분집합을 어긴 문서를 거부하고 canonical findings schema를
   내놓는다; host CLI의 structured-output flag가 probe로 확인되는 곳에서는
   (`--check-schema-flag`) dispatch가 그 schema를 넘기고, `REVIEW_CRITERION_SCHEMA`
   아래의 receipt emission이 class 없는·enum 밖 결과를 거부한다 — receipt가 없고,
   증명되지 않은 dispatch는 이미 stop class다. `--verify-receipts --packet`은
   packet의 record를 재컴파일해서 다른 criterion에서 컴파일된 schema digest를 단
   receipt를 거부한다. flag가 probe에서 absent인 route는 2번으로 돌고 prose
   discipline으로 공시된다 — schema-enforced로 credit되지 않는다.

## Golden 수명주기

- **채택**: 정의가 열어 둔 경계를 결정하는 golden만 — 기록된 분류 불일치나 감사로
  잡힌 오분류가 근거다; 출처는 `measured` 또는 `constructed`로 라벨하고 왜 + 날짜를
  단다.
- **뒤집기**: 실측 반례로만. golden은 제자리에서 고친다 — 이 guide는 현재를 기술한다 —
  그리고 레포가 결정을 기록하는 채널에, 닫힌 golden과 반례를 명시한 날짜 있는 decision
  record를 남긴다. 조용한 삭제는 금지다: 틀린 golden은 reviewer를 체계적으로 틀리게
  만들고, 추적 없는 수정은 그랬다는 사실을 숨긴다.

## 선언, 전환, 혼합 packet

- dispatch되는 모든 packet이 criterion을 이름으로 선언한다. 하네스 라운드는
  `AI harness`를 선언한다; 카탈로그에 항목이 없는 시스템 유형의 라운드는 packet 안에
  위 스키마대로 쓴 **task-local criterion**을 task-local이라 라벨해 선언한다 — 반복
  사용이 카탈로그 항목을 얻는 길이다.
- 혼합 packet은 criterion당 하나로 쪼갠다. 한 궤적의 두 관찰자는 어떤 단일 종료
  조건도 셀 수 없는 finding을 낳는다.
- 루프 중간에 criterion이 바뀌면: 아직 열린 finding만 재분류한다; 이미 기록된
  라운드는 날짜 있는 역사다. 전환 전후의 수를 한 계열로 잇지 않는다 — 서로 다른 것을
  센 수다.

## Evidence base

39라운드 적대적 review loop(3 lens × frontier reviewer, 이웃한 OAuth CLI-API
adapter, 2026-08-13–15)에서 파생: 같은 codebase가 자기보충 criterion 아래에서
17→19→21→23→19로 고원에 걸렸고, class를 분리해 종료를 `behavioral_defect` 위에서만
세기 시작한 라운드에 다시 감소했다(behavioral 10→5). 경계 근거도 같은 루프다:
"coverage gap을 부풀리지 마라"는 packet 지시에도 두 lens가 같은 finding을 `doc_gap`과
`behavioral_defect`로 — 둘 다 근거 있게 — 분류했다; golden 하나면 갈렸다. 비수렴
golden(8→9→10→5→12, 모든 수가 참)은 이 환경 자신의 launcher-review loop다
(2026-08-16–17, 선언되지 않은 "material" criterion 아래). 두 계열은 두 criterion
아래의 두 모집단이고, 정확히 위 전환 규칙의 이유로 따로 인용한다. review route나
바인딩된 모델이 바뀌면 재도출한다.
