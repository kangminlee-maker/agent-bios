---
guide_id: review-request
language: ko
status: active
use_when:
  - 모델과 무관하게 review 요청·packet·reviewer role을 작성할 때
  - reviewer에게 요구할 근거 기준과 verdict 형태를 정할 때
  - review가 noise를 냈거나, 아무것도 못 냈거나, 깨끗한 판정을 냈을 때 원인을 가릴 때
  - 어떤 관점을 돌릴지, deliberation 비용을 낼지 정할 때
core_rules:
  - gap이 아니라 failure path를 요구한다 — "X가 검증되지 않았다"는 죽고 "Y일 때 X가 깨진다"는 산다
  - 모든 finding은 file:line에 anchor하고, 빈 결과는 무엇을 확인했는지 근거를 대게 한다
  - 대상이 무엇이고 무엇이 아닌지 밝힌다 — stage, boundary, 그리고 부재가 뜻하는 바
  - 대상이 의존하는 consumer를 함께 묶는다. 아니면 가장 load-bearing한 주장이 review 불가가 된다
  - carry-forward finding을 금지한다 — "watch"나 "나중에 문서화"로 표현될 것은 finding이 아니다
  - verdict를 믿기 전에 participation을 읽는다. 죽은 harness는 finding 0건을 보고한다
  - finding의 인과 귀속을 severity가 아니라 그 finding의 가장 약한 주장으로 취급한다
verification_focus:
  - zero-findings verdict는 액면가로 받지 않고 participation에 대조해 확인한다
  - finding은 조치 전에 failure path가 명시됐는지 확인한다
  - 빈 결과는 확인한 근거를 인용할 때만 신뢰한다
---

# Review Request Guide

이 guide는 전역 Coding Guidelines의 범위 확장이다. reviewer에게 무엇을
요구할지 — 요청, 근거 기준, verdict 형태 — 를 작성할 때 사용한다. 언제
review할지, 얼마나 깊이, 무엇이 material한지는 다루지 않는다 — 마지막 질문은
둘로 갈린다: *얼마나 나쁜지*는 `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/coding-staged-workflow.md`의
severity ladder와 review loop가 소유하고, 애초에 결함인지·어느 class인지·"0"을
무엇 위에서 세는지는 defect criterion으로,
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/review-defect-criteria.md`가 소유한다.
어느 reviewer 종류로 라우팅할지도
다루지 않는다 — `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/verification-discipline.md`의 convergence heuristic이
소유한다. 특정 model 계열에 맞춘 prompt 표현은 여기 범위 밖이다;
그 지침이 배포되는 곳에서는 그것을 필요로 하는 규칙이 직접 가리킨다.

아래 규칙은 이 환경에서 실제로 돌린 약 330개 multi-lens review 세션에서
파생했다. 그 코퍼스는 사실상 한 model 계열이므로 여기에 model별 주장은 없다.
이것들은 누가 review하든 남는 실패다. 각 규칙은 근거를 명시한다 — 근거 없이
단언하는 review guide는 자기 기준에 스스로 미달하기 때문이다.

## criterion을 선언한다

다른 무엇을 작성하기 전에, 이번 review가 어떤 defect criterion 아래에서 도는지
이름으로 선언한다 — 시스템 유형별 결함의 정의, class enum, 그리고 "0"을 무엇
위에서 세는지. 그 선택은 `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/review-defect-criteria.md`가
소유하고, 이 guide는 하나가 선언돼 있다고 가정한다. packet 맨 위에
`Criterion: <이름>`을 두고 그 criterion의 golden을 그대로 붙인다 — golden 없는
정의는 경계에서 일관되게 분류되지 않고, 선언되지 않은 criterion은 reviewer마다
자기 기준을 쓴다는 뜻이다.

## gap이 아니라 failure path를 요구한다

reviewer의 지배적 실패는 환각이 아니다. 기각된 finding 372개 중 "failure를
보이지 않고 gap만 주장"이 가장 큰 몫(약 34%)이고, 정상 코드 오독은 **1건**,
추측은 7건이다. reviewer는 결함을 지어내지 않는다. 검증되지 않은 것을 보고하고
그걸 finding이라 부른다.

코퍼스는 finding의 틀 짓기로 이를 깔끔히 가른다:

| 틀 | 기각률 |
|---|---|
| `evidence_gap` — "커버 안 됨 / 검증 안 됨" | 94% (n=143) |
| `needs_evidence` | 93% (n=118) |
| `document_only` | 92% (n=144) |
| `root_cause` — 원인이 있는 결함 | 3% (n=878) |
| `fix_now` | 3% (n=1026) |

그러니 요청에 명시한다: **입력, 분기, 관측 가능한 잘못된 동작을 밝혀라.
"X가 검증되지 않았다"는 finding이 아니고, "Y일 때 X가 깨진다"가 finding이다.**
failure를 보일 수 없는 reviewer는 그것을 대상에 대한 finding으로 제출하지 말고
boundary note로 말해야 한다.

## severity floor를 설정한다. low는 결코 살아남지 않는다

severity는 코퍼스에서 가장 결정적인 예측자이며 거의 결정론적이다:

| Severity | 산출물 도달률 |
|---|---|
| `blocker` (n=16) | 100% |
| `high` (n=366) | 96% |
| `medium` (n=1338) | 92% |
| `info` (n=44) | 5% |
| `low` (n=226) | **0%** |

low severity finding은 226건 중 **하나도** 살아남지 못했다. 그것을 만든 token은
두 번 낭비됐다 — 쓸 때 한 번, 읽을 때 한 번.

그러니 요청에 floor를 명시한다: **low로 평가할 finding은 보고하지 마라. 어차피
폐기된다. 그 노력을 medium 이상 finding에 써라.** 이것은 reviewer에 대한 품질
기준이 아니라 비용 결정이다. 코퍼스는 폐기가 어차피 일어남을 보여주므로, 남은
질문은 그것을 생성하는 비용을 먼저 낼 것인가뿐이다. (각 severity의 정의는 이
guide가 아니라 `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/coding-staged-workflow.md`의
ladder가 소유한다.)

## carry-forward finding을 금지한다

코퍼스가 유예 가능으로 분류한 finding은 전부 죽었다: `planned_later` 100%
(n=104), `watch` 100% (n=36), `defer_watch` 97% (n=71), `out_of_scope` 92%
(n=26). 산출물까지 살아남은 것은 하나도 없다.

이 대상에서 지금 바뀌어야 할 것만 요구한다. reviewer가 "carry forward",
"watch", "나중에 문서화"로 표현할 것은 만드는 데 token을 쓰고 읽는 데 token을
쓰고 폐기된다 — 애초에 쓰이지 않도록 미리 말한다.

## 루프는 개수가 아니라 출처로 멈춘다

리뷰 루프의 finding 개수는 다음 라운드를 돌릴지에 대해 아무것도 말하지 않는다. 결정하는 것은
그 finding이 어디서 왔는가다 — 직전 라운드의 **수정**이 만들어낸 finding은 원래 있던 것과 다른
종류다.

각 finding을 둘이 아니라 셋으로 분류한다: 직전 수정이 **원인**인 것, 직전 수정이 **드러낸** 것(수정 때문에 그곳을 보게 됐을 뿐, 결함 자체는 수정이 건드리지 않은 경로에서도 재현되는 것),그리고 기존. 이 구분은 분류가 아니라 되돌리기 규칙이다: 되돌리면 원인인 결함은 사라지지만 드러난 결함은 가려질 뿐이다. 둘을 합치면, 설계 변경을 되돌리고 finding이 정리됐다고 세면서 드러난 쪽은 그대로 살아 있게 된다. 둘을 가르는 시험은 그 결함이 수정이 건드리지 않은 경로에서도 재현되는가다. 그 다음 라운드에 걸쳐 원인 비율을 읽는다.
비율이 오르면 수정이 일감을 만들고 있다는 뜻이고, 이는 결정되지 않은 설계 질문을 그 결과 쪽에서
때우고 있다는 신호다. 리뷰를 멈추고 설계를 별도 과제로 삼는다.

기전은 Concept Economy가 이미 이름 붙인 것이다: 오래 남는 개념 — 필드, 멤버, 계약, 실패 종류,
새 오류 상태 — 을 추가하는 수정은 diff가 아무리 작아도 설계 변경이고, 다음 라운드가 그 결과를
찾아낸다. 개념을 **없애는** 수정이 건강한 모양이다.

멈출 때는 반쯤 설계된 메커니즘을 남겨 두지 말고 트리를 가른다: 순수 결함 수정은 남기고, 설계
변경은 되돌리고, 그 공백을 읽힐 자리에 기록한다.

출처: 로컬 API 어댑터에 대한 외부 13라운드 캠페인. 12·13라운드가 6건 중 3건, 10건 중 6건이
caused-by였고 전부 네임스페이스를 새로 만든 두 줄짜리 수정 하나로 추적됐다. 캠페인 한 건이며
측정된 비율이 아니다 — 옮길 수 있는 것은 임계값이 아니라 기전이다.

## 대상이 무엇인지, 부재가 무엇을 뜻하는지 밝힌다

reviewer가 부족했다고 가장 많이 보고하는 것은 stage 맥락이다. 설계를 review하는데
구현을 볼 수 없으니 모든 finding을 설계 계약 주장으로 완화한다. 세션 전반에
반복되는 그들 자신의 표현: *"이 packet은 구현된 patch가 아니라 설계를
review하므로 정확한 향후 API는 보이지 않는다."*

stage를 명명하고 부재가 뜻하는 바를 말한다 — "이것은 구현 전 설계다. 구현 부재를
결함으로 취급하지 마라." 정확히 그 지시를 받은 세션은 finding 0건을 냈고 비교의
양쪽에 anchor해 자기가 살펴봤음을 증명했다. 그 지시가 없던 세션은 미구현 코드를
blocker로 제출했고 사용자가 수동으로 잡아냈다.

대상에는 revision도 있다. packet이 어느 commit이나 content hash 위에서
dispatch됐는지 명명하고, 그 revision의 모든 reviewer가 돌아올 때까지
artifact를 움직이지 않는다. lens가 아직 떠 있는 동안 수정이 들어가야 한다면,
돌아온 finding을 세기 전에 고정된 revision에 대조해 매핑한다: anchor 텍스트가
더 이상 존재하지 않는 finding은 stale이며, 다시 고치는 것이 아니라 그 매핑으로
닫히고, 결코 open으로 집계되지 않는다.

## artifact만이 아니라 consumer를 함께 묶는다

대상이 "X 참조"라고 말하면 X는 대상의 일부다. 코퍼스에서 가장 날카로운 사례:
reviewer가 설계에서 가장 load-bearing한 연결을 짚어내고는 그것을 review하지 못했다
— *"§6.4는 review boundary 밖이므로 axis-consumption 완전성을 artifact 안에서
검증할 수 없다."* 요청이 자식만 묶고 그것이 의존하는 부모를 빼놨다.

reviewer가 거의 매번 필요로 한 것은 consumer였다: 그 field를 읽는 코드, 가중치를
정의하는 부모 문서, 동작을 증명하는 log. 어떤 주장의 근거가 boundary 밖에 있다면
boundary를 넓히거나 그 주장이 review 불가임을 받아들여야 한다 — 그것에 대한
finding을 기대해선 안 된다.

## 근거를 요청이 아니라 구조로 만든다

이 코퍼스에서 모든 finding은 `file:line` anchor를 달고 모든 빈 결과는 근거를
단다 — 2,466/2,466, 981/981. prompt가 정중히 부탁해서가 아니다. submit schema가
그것 없는 출력을 거부한다. 그 결과 reviewer는 존재 여부에 대해 옳고(토론 후
미해결은 전체 이슈의 0.3%), "아무것도 못 찾음"이 침묵이 아니라 검증된 진술이 되는
코퍼스가 만들어졌다.

이것은 일반적인 capability-boundary 규칙을 review에 적용한 것이다. 출력이 어떤
속성을 반드시 가져야 한다면, 그것 없이는 불가능하게 만든다. review route에 schema가
있으면 anchor를 거기에 넣는다. 없으면 요청에 넣되, 요청만으로 얻는 더 약한 결과를
각오한다.

대상에도 같은 원리가 적용된다. 자기 사실을 `file:line`으로 인용하는 문서는
reviewer에게 반증 가능한 표면을 준다. 코퍼스에서 가장 좋은 finding들은 정확히 그
인용된 사실에 대한 반박이었다. 산문은 확인할 것을 주지 않는다.

## 근거가 증명하는 것만 주장하고, 하나의 root에 귀속시킨다

reviewer는 결함의 존재 여부에는 잘 보정되어 있고 그 원인에는 어긋나 있다.
finding이 좁혀질 때 결함 자체는 거의 항상 살아남는다(97%, n=212). 잘리는 것은
인과 귀속(45%)이나 주장이 덮은 표면(34%)이지, 제안된 fix(10%)도 결함도 아니다.
lens는 이를 일급 stance로 기록한다: `narrow`가 1,320회, `oppose`는 101회. 무언가
깨졌다는 데는 거의 이견이 없고, 무엇이 깨뜨렸는지와 그것이 시스템의 얼마나 많은
부분을 건드리는지에는 일상적으로 이견이 있다.

"narrowed"는 실제로 벌어지는 일에 대한 오해를 부르는 이름이다. 좁혀진 주장은
오히려 **길어진다** — 94%가, 중앙값 약 118자만큼. 좁힘이 텍스트를 지우는 게
아니라 한정과 재귀속을 더하기 때문이다. 최종 root cause는 사실상 재작성이다(원문
대비 텍스트 유사도 중앙값 0.21). 다듬기처럼 보이는 것은 reviewer가 자기 근거가
실제로 뒷받침하는 만큼만 말하게 되는 과정이다.

그래서 좁힘과 기각은 입자도만 다른 같은 힘이다. 근거 너머로 과잉 주장하면,
증명된 핵심이 있으면 좁혀지고 없으면 기각된다. 코퍼스의 언어가 양쪽에서 동일하다
— 살아남은 것들은 "직접 근거된 command-wiring gap으로 좁혀짐", "capsule
authority_refs에서 증명된 파일들로 좁혀짐", "입증된 side-effect 경로로 좁혀짐"이다.

그러니 관측 가능한 failure와 그것을 증명하는 근거를, 그 근거가 덮는 표면으로
범위를 한정해 요구한다. reviewer의 인과 서사는 그 finding의 가장 약한 주장으로
취급한다 — 결론이 아니라 검증할 가설이다. 그리고 제안된 fix가 기본값으로 설계가
되게 두지 않는다.

놓치기 쉬운 축이 하나 있다. 좁힘의 약 17%에서는 모든 lens가 결함도 root도 fix도
받아들이고, 살아 있는 이견은 **얼마나 나쁜가**뿐이다. 이 축은 그 비중이
시사하는 것보다 중요하다. severity가 생존을 결정하기 때문이다 — low로 평가된
finding은 산출물에 도달하지 못한다. severity가 다투어진다면 그것이 판정할
대상이지 평균 내어 넘길 세부가 아니다.

## verdict를 믿기 전에 participation을 읽는다

일곱 세션이 `Finding count: 0`이라는 깨끗한 판정을 `Participating lenses: 0/N`과
함께 냈다. 아무것도 review되지 않았다. 그리고 harness가 죽으면 두 개의 별도 채널이
그 이유에 대해 거짓말을 한다. 스물두 세션이 `failure_kind: output_contract`를
기록했는데, nested stderr를 읽을 수 있는 것들에서 원인은 provider usage-limit
거부다 — *"You've hit your usage limit"*, `exit=1`, model 출력이 전혀 생성되지
않음 — 즉 애초에 contract를 위반할 출력이 없었는데도 label은 model 출력 형식을
탓한다. 그 label로 triage하면 credit을 사야 할 때 prompt를 디버깅한다.

review를 소비하는 쪽에 주는 두 가지 함의:

- 판별 지점은 participation 수와 execution status이지 severity 수치가 아니다.
  죽은 harness는 만점으로 렌더링된다.
- failure의 이름을 단 artifact가 failure를 담고 있지 않을 수 있고, 두 실패가
  겹친다. 바로 그 quota로 죽은 세션들에서 `environment-warnings.yaml`이라는 파일은
  `non_fatal` dispatch trace만 `outputTrustImpact: unknown`으로 기록하고 quota는
  한 번도 언급하지 않았다. 코퍼스 전체로도 약 9,800개 warning을 담고 진짜 실패에
  단 한 번도 fire하지 않았다. 즉 failure의 이름이 붙은 채널은 결코 fire하지 않고,
  fire하는 채널은 틀린 이름을 쓰며, 진실은 nested stderr에만 있다. 원하는 것의
  이름이 붙은 채널이 아니라 메커니즘이 실제로 쓰는 채널을, 저수준 log에 대조해
  읽는다.
- Participation은 lens가 실행됐음을 알려줄 뿐, 전체 subject를 봤음을 뜻하지
  않는다. Git-diff 기반 review tool은 HEAD-range diff에서
  staged-but-uncommitted 변경을 조용히 누락하고, 어떤 diff에서도 untracked
  file을 누락한다. dispatch 전에 `git status --porcelain`으로 subject를
  나열하고 untracked file을 노출한다(`git add -N` 또는 WIP commit); run 뒤에는
  reviewed-file 목록을 그 목록과 대조한다 — 설명되지 않은 gap은 verdict를
  incomplete로 격하시킨다. (우리 자체 dispatch wrapper는 이 check를 스스로
  수행한다; 우리가 소유하지 않은 review route에서는 이를 수동으로 적용한다.)
- review 산출물은 남긴 finding만이 아니라 *기각한* finding도 이름을 올린다.
  따라서 문서에 등장한다는 것이 생존을 뜻하지 않는다. 등장 여부로 생존을 도출하면
  구조적으로 100%가 나온다 — 여기서 실제로 그랬고, material 섹션으로 범위를 좁히자
  같은 finding의 16%가 non-material로 명시된 채 독자에게 도달했음이 드러났다.
  언급이 아니라 verdict field를 읽는다.
- 방출된 item 목록을 harness가 보고하는 모든 총계 — finding 수, verdict 집계,
  item별 decision log — 와 대조한 뒤에 triage한다. finding 0건은 그중 극단적인
  경우일 뿐이다: 부족분이 있다는 것은 집계 과정에서 item이 떨어졌다는 뜻이고,
  떨어진 집합은 무작위가 아니다. merge나 filter는 대개 하나의 class를 통째로
  잃기 때문이다. 차이는 raw item별 record에서 회수해 합집합을 triage한다;
  raw record가 없다면 그 산출물은 깨끗한 것이 아니라 불완전한 것이다.

## 빈 결과는 무엇을 확인했는지 인용할 때만 신뢰한다

빈 결과는 흔하고 대개 옳다. lens 실행의 42%가 아무것도 내지 않으며, 그 실행들은
생산적인 실행보다 입력이 *더 크고* 저장소 review 순서에서 *더 뒤*에 있다 — 이미
고친 대상에 대한 재review다. 명명할 가치가 있는 낭비는 빈 결과가 아니라, 이미
수리한 것을 full pipeline 비용을 내고 다시 review하는 것이다.

빈 결과는 그 근거로 신뢰를 얻는다. 근거 있는 null은 비교의 양쪽에서 확인한 근거를
명명한다. 근거 없는 빈 결과는 깨끗한 판정을 입은 실패한 실행이다 — 비어 있음이
아니라 근거에 gate를 건다.

## deliberation은 판정하는 곳에 쓰고 합의하는 곳에는 쓰지 않는다

이슈의 3분의 2(66%, n=1153)는 deliberation이 아예 필요 없고, halt의 가장 큰 단일
원인은 사용자 취소다. 다만 일찍 취소하지 않는다. 취소된 27개 세션 중 27개가 원시
1차 pass에 도달하고 22개가 통합된 finding ledger에 도달하지만 deliberation까지 간
것은 2개뿐이다. 사용자는 중복 제거되고 severity가 붙은 ledger를 기다려 그것에
조치하고, 다음에 돌았을 deliberation과 synthesis를 버린다. 반면 실제로
deliberation을 거쳐 살아남은 이슈는 코퍼스에서 가장 신뢰도가 높다(material 94% vs
미심의 74%).

즉 deliberation은 다투는 주장을 판정할 때 값어치를 하고, 모든 관점이 이미 합의할
때는 의례다 — 코퍼스에서 가장 큰 deliberation artifact 중 하나는 22건 중 22건을
"deliberation 불필요"로 처리했다. 실제로 쓰이는 부분이 그것이므로 조치 가능한
finding을 앞에 배치한다.

## 물 수 있는 관점을 고른다

관점을 늘리는 것은 공짜가 아니다. 이 코퍼스에서 concept-surface lens는 finding을
가장 적게 내고, 가장 자주 침묵하며, 낸 것의 절반이 폐기된다 — 후보의 43%가 low로
평가되고 low는 결코 살아남지 못하기 때문이다. 이름·중복·추상화 우려는 runtime
동작이나 강제된 semantics를 바꿀 때만 값어치를 한다. 그 조건으로 요구하거나 아예
요구하지 않는다.

반대 실패도 지켜볼 가치가 있다. 진짜 위험을 소유한 관점이 없으면 reviewer는 결함
대신 governance gap을 제출한다 — *"이것은 대상의 설계 결함이 아니라 review-governance
gap이다."* 그건 review가 자기 lens set이 대상에 맞지 않았다고 말해주는 것이다.

## Evidence base

2026-07-16에 이 환경의 저장소 15곳, onto review 세션 약 330개에서 파생했다(분류된
이슈 1,738건, anchor된 finding 2,466건, deliberation 278건, lens stance 14,370건).
여기의 모든 수치는 기록 전에 독립적으로 재현했고, 첫 시도 몇 개는 틀렸다. 문서 등장
여부로 측정한 생존율은 구조적으로 100%가 나오고, 손으로 짠 동사-목적어 집계는 좁힘
축을 약 5배 과소집계했다. 좁힘이 어떻게 갈리는지에 대한 비율은 하한으로 읽고(약
19%가 분류에 저항한다), 크기가 아니라 순서(root > scope > severity > remedy)를
신뢰한다.

이 guide가 주장할 수 있는 범위를 한계 둘이 정한다. 코퍼스의 약 95%가 단일 model
계열이므로 여기에 model별 주장은 없다. 그리고 명세 부족 요청이 하나도 없다 — 가장
짧은 것도 축과 근거 기준을 명명한다 — 따라서 이것들은 *좋은* 요청에서도 남는
실패이지 요청을 더 명세하라는 논거가 아니다. review route나 bind된 model이 바뀌면
새 코퍼스에서 다시 파생한다.
