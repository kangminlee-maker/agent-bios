---
guide_id: verification-discipline
language: ko
status: active
use_when:
  - 느리거나 비싼 실행에 비용을 쓰기 전에, 이 변경에 얼마만큼의 verification이 필요한지 정할 때
  - 도메인별로 무엇을 돌릴지 고를 때 — 코드, ontology, config/데이터, spreadsheet, 문서, release
  - 검사의 케이스 공간을 만들거나, 기대 답이 무엇이어야 하는지 정할 때
  - 검사가 green이거나 비었거나 빨리 끝났고, 그것을 믿으려는 참일 때
  - 독립적·adversarial review를 돌리고, 그 합의가 무슨 값어치인지 판단할 때
core_rules:
  - 실패할 수 있었던 검사만 evidence다 — "no bad X" 주장 전에 subject가 비어 있지 않음을 assert한다
  - 케이스 공간은 그것을 정의하는 아티팩트에서 열거하고, 기대값을 타이핑하는 대신 실제 출력을 기록한다
  - 깊이는 비용·위험·정보 이득에 비례시킨다; single-user 도구는 production 수준 assurance를 필요로 하지 않는다
  - 같은 kind의 reviewer는 blind spot을 공유하므로, 그들이 공유하는 "clean"은 verification이 아니라 이의 부재다
---

# Verification Discipline

전역 Verification Discipline 섹션의 scoped extension이다. 주제는 "테스트를 했는가"가 아니라 그
아래 있는 더 어려운 질문이다: **이 검사는 실패할 수 있었는가?** 아래 전부는 결과를 인용한 뒤가
아니라 믿기 전에 그 질문에 답하는 방법이다.

전역에 남아 있는 규칙들은 그 순간이 스스로를 알리지 않는 것들이다 — 끝났다고 믿는 것, 그 믿음이
곧 실패다. 이 가이드는 자기가 지금 검증 중이라는 걸 안 뒤에 여는 문서다.

## 비용을 쓰기 전에 깊이를 정한다

verification에는 비용과 정보 수확이 있고, 둘은 기본적으로 비례하지 않는다. 깊이를 먼저 정한다:

- 비싼 것을 돌리기 전에 코드에서 진단하고, 바뀐 deterministic logic은 파이프라인 전체를 다시
  돌려 관찰하는 대신 persisted real artifact 위에서 replay한다.
- precondition을 확인한 입력으로 N=1에서 probe한다. real path에 도달하는 잘 고른 케이스 하나가
  거기 못 미치는 백 개보다 낫다.
- N=1 probe는 reachability까지만 인정한다. 케이스 하나는 경로가 동작하는지를 정할 뿐,
  stochastic한 동작이 얼마나 자주 성립하는지는 결코 정하지 않는다. rate 형태의
  속성(determinism, flake rate, A/B 효과)을 인용하기 전에, 메커니즘이 자신의 control을
  존중하는지 확인하고, 이미 가진 run에서 noise floor를 세우고, real path 위의 no-treatment
  control에 대해 그 rate를 bound할 만큼 표본을 모은다. 효과보다 큰 floor는 전제를
  무너뜨린다 — 재설계하기 전에 그것을 기록한다.
- full design-review와 live verification은 first-of-kind 작업과 authority를 바꾸는 변경 — 누가
  결정할 수 있는지, 누가 쓸 수 있는지, 무엇이 되돌릴 수 없는지 — 에 아껴 둔다.
- assurance는 deployment context에 비례시킨다. 자기 데이터를 다루는 single-user 도구는
  production 수준 assurance를 필요로 하지 않고, 그런 것처럼 다루면 얻는 것 없이 delivery만
  늦춘다. 배포를 우선한다.
- 비용이 들거나 되돌릴 수 없는 batch 전에 population을 census한다. 현재 상태를 값싸고
  deterministic하게 읽고 — status 분포, 버전, 계획이 기대하는 artifact의 존재 여부 —
  그것을 batch가 딛고 선 전제와 대조하며, 분포가 전제와 어긋나면 멈추고 다시 진단한다.
  probe는 경로를 검증하고, population이 계획의 가정대로인지는 census만이 검증한다. 항목
  몇 개에 대한 값싼 idempotent batch에는 필요 없다.

이것이 막는 실패는 테스트 부족이 아니다. verification 예산을 위험의 값싼 절반에 다 쓰고, 정작
아플 수 있는 쪽에는 아무것도 남기지 않는 것이다.

## static floor

넓고 값싼 검사를 먼저 돌려 느린 것이 시작되기 전에 실패하게 한다: typecheck, lint, build,
format, schema·config validation, graph validation, workbook 구조 검사, import boundary, 그리고
있으면 security check. 이것들은 floor이지 판정이 아니다 — 아티팩트가 well-formed임을 증명할 뿐
동작을 증명하지는 않는다.

## Verification Menus

바뀐 동작·의미·contract를 증명하는 가장 좁고 신뢰할 수 있는 mix를 고른다. mix 안에서 추가하는
단위는 그것을 증명하는 가장 좁고 신뢰할 수 있는 runtime 또는 semantic 테스트다 — 여기서 "가장
좁은"은 변경이 틀렸다면 실패할 가장 작은 테스트를 뜻하며, 쓰기에 가장 싼 테스트와는 다르다.

- 코드: layered mix — unit test, E2E 구간에 대한 integration test, 바뀐 flow에 대한 targeted E2E, release나 고위험 변경에 대한 full E2E.
- Ontology: static graph check, concept economy gate, changed-path integration check, competency-question E2E check.
- Config·데이터: real parser, schema check, fixture validation, sample transformation.
- Spreadsheet: static workbook check, fixture 기반 출력 check, cross-sheet flow check, visual/layout check, 그리고 formula에 의존하는 결과에 대한 real Microsoft Excel engine 재계산.
- 문서: 링크, 용어, 현재 동작과의 정합, 격리된 historical note에 대한 참조.
- 여러 subject를 다루는 산문: 산출물이 서로 다른 사람·회사·사건에 대한 자료를 함께 쓸 때, 포착하는 시점에 모든 항목을 그 subject와 confirmation 상태에 묶고, 그 묶음이 확인되기 전에는 어떤 subject 아래에서도 서술하지 않는다. 전달 전에 subject별 고유명사와 수치를 모든 산출물에 걸쳐 교차 확인한다 — 한 subject의 용어가 다른 subject 아래 있는 것이 context bleed의 signature다. 떨어져 나온 숫자는 가장 나쁜 쪽으로 읽히므로, 수치는 그 구성과 같은 문장 안에 둔다.
- Release/distribution: 여러 독립적으로 writable한 channel(signed manifest, object storage, release host, embedded updater)에 배포한 뒤, channel별로 참조된 모든 object를 staging original과 digest-verify한다 — 배포 성공과 upload 순서는 근거가 아니다 — 그리고 real installer/updater를 기본 경로로 실행한다.
- A/B 또는 on/off measurement: null result를 받아들이기 전에, 검증 대상 메커니즘에서 두 arm이 실제로 다른 treatment를 받았는지 확인한다 — 공유된 default나 무조건적인 upstream step이 두 arm 모두에 조용히 treatment를 적용할 수 있다.
- nondeterministic stage가 있는 multi-stage pipeline: final-output diff로는 효과나 regression을 특정 stage에 귀속시킬 수 없다 — 변경과 run 간 분산이 뒤섞인다. 모든 stage의 출력을 persist하고, 각 stage가 무엇을 만들고, 무엇을 편집할 수 있고, 무엇만 guard하는지 표로 정리하고, 문제의 콘텐츠를 편집하는 stage로 용의자를 좁히고, 의도한 효과가 사라지거나 결함이 나타나는 첫 stage를 찾는다. 거기서 고치되, 이미 실패한 prompt-level instruction을 하나 더 얹기보다 구조적 재확인을 택한다.
- before/after 비교: 입력을 immutable copy — snapshot이나 versioned artifact — 로 고정하고 두 arm 모두 그것에 대해 돌린다. live artifact(자라는 로그, 다시 생성되는 upstream stage)는 run 사이에 drift하므로 그 위의 어떤 diff도, 일치하는 diff까지 포함해, 아무 근거가 아니기 때문이다; arm이 metered면 baseline의 upstream 입력을 정확히 복원하고 바뀐 stage만 다시 돌린다. 이것은 input identity의 문제이지, 별개인 단위·분모 기준 규칙이 아니다.
- Model-behavior guardrail: recitation이 아니라 바뀐 동작으로 검증한다 — named-trigger case부터 disguised, deconfounded, category-wide, single-variable framing까지 이어지는 staged battery를 쓴다; clean pass는 "known defect 없음"을 뜻하므로 model이 바뀌면 battery를 다시 돌린다.
- Real data에 대한 branch/version test build: 앱이 건드리는 모든 state sink(파일, DB, env override를 무시하는 OS-level store)를 명시적으로 분리하고, launch path가 그 isolation을 child process까지 전파하는지 확인하고, 첫 실행 전에 live data를 백업한다 — write 시 unknown field를 버리는 mismatched schema는 no-op이 아니라 data loss다.
- production에서 파생된 config로 도는 sandbox·replay·재판정 실행: 그 stage가 도달할 수 있는 모든 outbound channel — publish, upload, notify, external write — 을 열거하고, 실행 전에 각각을 끄거나 다른 곳으로 돌리며, path guard를 증명하듯 각 disarm이 실제로 발동함을 증명한다; 입력이나 target path에만 건 guard는 egress를 무장한 채로 남긴다. 실행 전에 모든 external destination을 fingerprint하고 실행 후 diff해서, 빠져나간 write가 수신자가 아니라 그 실행에서 잡히게 한다.
- Irreversible capture switch: activation 자체에 재현 불가능한 비용이 있으면(replay할 수 없는 capture window), 활성화 전에 기존 sample로 downstream consumption path를 증명한다 — code path의 reversibility만으로는 충분하지 않다.

## 케이스 공간 도출

어떤 시나리오가 존재하는지는 semantic 작업이다: diff, 사용자 영향, concept 영향, failure mode에서
도출한다. 그것을 돌리는 일은 아니다 — tool과 code가 케이스를 실행하고 evidence를 보고한다. 이
구분을 유지하는 것이 스위트가 "누군가 상상한 것의 기록"이 되는 걸 막는다.

검사에는 사람이 쓴 절반이 둘 있고, 둘은 다르게 썩는다. **판정**(답이 무엇이어야 하는가)은
처음부터 틀린 믿음을 박아넣는 방식으로 썩고, **공간**(어떤 케이스가 있는가)은 그것이 덮는
대상이 자라는 동안 가만히 있는 방식으로 썩는다. 판정을 기록하는 것은 흔한 관행이지만 공간을
도출하는 쪽은 대개 손으로 남아 있어서, 기대값을 전부 도출한 스위트가 누군가 한 번 타이핑한
집합만 덮고 있을 수 있다.

- green으로 만들기 전에 기준을 falsifiable하게 만든다. 메커니즘이 틀렸을 때 실패하는 signal —
  negative 또는 contrast control — 을 선호한다. 어떤 기준을 판정할 기존 gate가 없으면 실행
  가능한 judge를 만들거나 그 기준이 충족됐다고 주장하지 않는다: 무엇으로도 실패시킬 수 없는
  기준은 작업에 대한 서술이지 작업에 대한 검사가 아니다.
- 판정은 타이핑하지 말고 기록한다. 실제 경로를 돌려 돌아온 것을 저장하면, drift가 믿음이
  아니라 diff로 드러난다.
- 공간은 그것을 정의하는 아티팩트에서 열거한다 — config의 항목, schema의 필드, router의
  route, 설치기의 호출 지점. 거기에 하나 추가하면 여기 수정 없이 커버리지가 넓어져야 한다.
- 예외 규칙도 도출한다. 정당하게 답이 없는 케이스가 있다면, 이름 목록이 아니라 아티팩트가
  지닌 속성으로 판정한다: 목록은 손으로 쓴 공간이 옆문으로 돌아온 것이고, 답이 있어야 할
  케이스가 답을 잃는 회귀를 흡수해버린다.
- 결과를 실제로 결정하는 튜플로 중복을 제거하고, 몇 개가 접혔는지 보고한다. 자기 절단을
  숨기는 커버리지 숫자는 실제보다 커 보인다.
- 공간이 아니라 비용으로 나눈다. 실제 경로에 비용·인증·네트워크가 필요하면 값싼 대역을 매
  커밋에, 진짜를 온디맨드로 돌리되 **같은 열거**를 쓴다 — 그래야 둘이 어떤 케이스가
  존재하는지를 두고 어긋날 수 없다.
- 도출은 저작을 제거하지 않고 옮긴다: 추출기와 불변식은 여전히 손으로 쓴다. 거기에 음성
  통제를 붙이지 않으면 도출된 스위트는 그냥 더 큰 반증 불가 스위트다.
- 통제가 발동함을 증명하려고 위반을 심는 것은 작업 트리에 쓰는 행위이고, 복원은 그것과
  원자적이지 않다: 프로브가 타임아웃·중단·인터럽트될 수 있으면 그 뒤에 놓인 복원은 아예
  실행되지 않고 심은 것이 커밋까지 살아남는다. 형태가 허락하면 사본에 심고, 제자리에
  심어야 한다면 먼저 스냅샷을 뜨고 프로브의 완주를 믿는 대신 별도 단계로 스냅샷에서 복원한다.
- 처방을 고르기 전에 controlled contrast로 결함을 귀속시킨다. 나머지를 전부 고정하고 —
  principal, 경로, 입력 — 후보 변수 하나만 바꿔서, 셀 수 있는 차이(요소 치수, 요청 수,
  status-code 계열)를 읽는다. error 보고가 없다는 것은 면책이 아니다: 채널은 억제되거나,
  관측되지 않거나, 문제의 메커니즘에 아예 연결되지 않았을 수 있으므로, "logged된 위반
  없음"은 contrast에서도 아무것도 나오지 않을 때만 원인을 배제한다. policy 완화를
  제안하기 전에 이미 가진 evidence가 담고 있는 contrast를 읽는다.

## green이 아무 뜻도 아닐 때

통과한 검사와 아예 돌지 않은 검사는 밖에서 보면 똑같다. 근거 없는 green을 만드는 형태들이다:

- **빈 subject.** 빈 집합에 대한 "no bad X"나 "all X satisfy P"는 vacuous하게 참이다. 주장
  **이전에** test 대상 집합의 cardinality가 0보다 큼을 assert하고, gate 자체가 아무것도 판정하지
  않았을 때 clean을 보고하기를 거부하게 만든다.
- **guard를 못 넘는 fixture.** 추가하거나 삭제하는 branch를 건드리는 test는 그 입력이 live
  branch의 entry guard를 만족하는지 확인한다. 새 guard를 통과하지 못하는 복사된 fixture는 조용히
  곧 삭제될 dead branch로 흘러들어가, real 동작이 깨진 뒤에도 green으로 남는다.
- **producer가 결코 내보내지 않는 fixture.** test의 입력은 production에서 그것을 만들어내는
  것이 실제로 만들어냈을 때에만 evidence다. wire fixture는 그것을 파싱할 바로 그 client를
  통해 포착한 raw response여야 하고, 렌더된 목록이나 손으로 쓴 payload여서는 안 된다;
  gated feature의 E2E는 gate를 production 설정에 둔 채, real upstream이 남기는 상태 위에서
  돌아야 한다. live producer에 대고 한 번 replay하고, 같은 방식으로 만든 sibling을 전부
  probe한다.
- **checker 안의 permissive fallback.** gate 안의 `a || b`는 잘못된 가정을 흡수하고 계속
  통과시킨다. checker 코드는 자기가 기대하는 shape를 assert하고 fail loud해야 한다.
- **수상하게 빠르거나 빈 실행.** 검사가 예상보다 빨리 green이 되거나 아무것도 보고하지 않으면,
  믿기 전에 그것이 실제로 무엇을 대상으로 돌았는지 덤프한다. 일찍 죽은 harness와 아무것도 못
  찾은 harness는 같은 exit code를 낸다.
- **crash로 실패한 통제.** negative control은 자기가 이름 붙인 assertion을 통해 실패할 때에만
  evidence다: traceback과 붙잡힌 위반은 같은 exit code를 내고, 이른 crash는 그 뒤의 모든
  통제를 선점해버릴 수 있다. control run에 나온 traceback은, 심은 위반마다 이름 붙은 실패가
  하나씩 보고될 때까지 결함으로 다룬다. 무인으로 도는 gate는 stdin을 닫고 돌려서, prompt에
  닿는 경로가 멈춰 있는 대신 즉시 실패하게 한다.
- **조용해진 통제.** live 목록을 인덱싱하는 negative control은 그 목록이 비면 테스트를 멈추면서
  아무 말도 하지 않는다. 새 통제는 자기 subject를 스스로 만들고, 항목을 해소하면 조용해진 통제가
  없는지 다시 읽는다.
- **조용한 로그.** 활동이 없다는 것은 사용되지 않았다는 근거가 아니다. 조용한 로그를 근거로
  identity·key·endpoint를 폐기하기 전에, 조회한 필드가 그 subject를 기록하는 필드임을 보이고 —
  위임된 동작은 caller에게 귀속되고 대상은 다른 필드에 들어가므로, 틀린 필드는 깨끗한 침묵을
  돌려준다 — 그것을 아직 참조하는 live binding이 없음을 보인다. 참조는 트래픽을 내지 않으면서도
  사용을 증명하기 때문이다. "이 사용이었다면 로그에 남았을 것"을 보인 것만이 미사용의 근거다.
- **줄어든 population.** 명시적인 파일 목록을 스캔하는 gate는 "목록에 있는데 비었다"만 본다:
  subject가 목록에 없는 surface로 옮겨가면 스캔 대상 집합은 작아지되 비지는 않으므로,
  empty-subject guard는 발동하지 않은 채 커버리지만 침식된다. 코드를 옮기는 그 변경 안에서
  gate의 대상을 다시 겨냥하고, 줄어들면 크게 실패하도록 floor를 고정한다 — subject 하나를
  빼내어 증명한다. floor는 ratchet이다: run을 통과시키려고 절대 낮추지 않는다.
- **돌지 않은 mutant.** mutation 판정은 mutant가 valid할 때에만 값어치가 있다: 컴파일되었고,
  실행되는 test가 지나는 경로 위에 있고, guard된 동작을 실제로 바꾼다 — downstream에서
  치유되지도, default와 우연히 일치하지도 않는다. runner는 build failure, unreachable,
  equivalent를 KILLED·SURVIVED와 구분해서 보고하고, anchor가 옮겨졌으면 멈춰야 한다. 그
  mutation이 건드릴 범위보다 더 많은 test가 빨개지면 그것은 mutant 자체를 고발하는
  신호다; survivor는 test를 쓰기 전에 분류한다(재작성, 폐기, 진짜 gap).
  **equivalent는 mutant만큼이나 probe에 대한 판정이다**: 죽었거나 상수를 반환하는 probe는
  모든 mutant를 equivalent로 보고하고, mutant가 건드리지 않는 입력을 겨눈 probe도 똑같이
  보고한다. probe가 **mutation하지 않은 코드에서** 구별력을 보이고 mutant가 겨눈 입력을
  실제로 지나간다는 것이 확인되기 전에는 그 판정을 받지 않는다 — 쓸 수 없는 probe는
  equivalent mutant가 아니라 그 자체로 별개의 결과다.
- **원본을 측정한 probe.** 자기 위치에서 root나 대상을 도출하는 복사된 스크립트(`$0`,
  `BASH_SOURCE`, 자기 부모로의 `cd`)는 사본이 아니라 원본 트리를 스캔하므로, 그 판정은 심어 둔
  mutation에 대해 아무 말도 하지 않는다. 사본 안에서 대상을 고정하거나, 트리 전체를 복사하거나,
  snapshot-restore로 제자리에 심는다. 징후는 mutation하지 않은 실행과 똑같은 결과다; 대상을
  인자로 받는 스크립트는 복사해도 안전하다.

위의 모든 형태를 덮는 규율: 검사를 추가한 뒤 그것이 지키는 수정을 되돌리고 검사가 실패하는지
본다. 충실한 revert에서 살아남은 통제는 자기가 이름 붙인 것을 애초에 테스트하지 않았다. 심은
것이 실제로 박혔음을 증명한다: 거부를 assert하기 전에, 변형된 입력이 원본과 다르다는 것과
통제의 케이스가 변형된 branch에 도달한다는 것을 assert한다. 손상은 deterministic하게
구성한다: 뒤집을 자리를 스캔해서 만드는 방식은 아무것도 실행하지 않은 거부를 보고하는 no-op
mutation을 낳는다.

## metric 변화를 코드 탓으로 돌리기 전에

live metric이 무너지거나 미리 선언한 임계값을 넘으면, 기능을 진단하기 전에 변화를 시간 축에서
국소화한다: 모든 inbound source가 살아 있는지 확인하고, 동시대 cohort만 비교하고, 다시 처리된
행은 절대 쓰지 않고, 그다음 가능한 가장 가는 단위로 전이 지점을 좁혀 그 순간 전후의 deploy
log를 읽는다.

last-good 지점에서 몇 초 떨어져 착륙한 변경이 최우선 용의자다; deploy가 없는 구간의 계단은
input-population shift이고, model이나 코드가 아니라 측정 대상 population을 좁혀서 고친다.
임계값은 보기 전에 선언하고, 실패는 자기 시점이 아니라 fleet의 시점에서 확인한다 — 이것이
비교 기준을 바로잡는 일을 대신하지는 않으며, 그쪽이 먼저다.

## E2E를 정직하게 유지한다

E2E는 flakiness가 환경 잡음으로 오인되고 그대로 무시되는 곳이다. 고정된 데이터, resilient
selector, 격리된 external dependency, sleep이 아닌 explicit wait로 deterministic하게 유지한다.
flaky한 E2E는 약한 테스트가 아니라 **결과가 아무 정보도 담지 않는** 테스트이고, 통과할 때까지
다시 돌리는 스위트는 아무도 결정하지 않은 채 꺼진 것이다.

## 독립 review와 합의의 값어치

사소하지 않은 설계와 고위험 변경에는 서로 다른 lens로 독립적인 adversarial review를 돌린다 —
가급적 구현 전 설계 단계에서, finding에 대응하는 비용이 아직 쌀 때. 그리고 각 finding은 실행에
옮기기 전에 real code에 대해 재검증한다: reviewer는 자기가 본 것으로 추론하고, 그 본 것이 틀렸을
수 있다.

**convergence heuristic by reviewer kind**를 적용한다 — 결과는 개수가 아니라 reviewer kind로 판단한다:

- 같은 kind의 convergence는 high-confidence지만 blind spot을 공유한다. 같은 kind의 reviewer 둘이
  깨끗하다고 합의하는 것은 verification이 아니라 이의의 부재다.
- 다른 kind 사이의 divergence는 해소해야 할 문제가 아니라 예상되는 signal이다. 교집합이 아니라
  **합집합**에 대해 행동한다.
- orchestrated workflow가 스스로 보고하는 all-green은 그 자체로 결코 충분하지 않다. diff 검사와
  verification suite를 직접 다시 돌린다.

진짜 독립성을 사는 가장 싼 방법은 다른 provider이고, 그다음이 다른 model, 그다음이 엄격히 더 높은
effort다. 검사 대상보다 낮은 effort로 돌린 reviewer는 아무것도 사지 못한다 — 더 싼 것은 또 하나의
관점이 아니다.

## 보고

작업 완료를 선언하기 전에 실행한 검사, 그 결과, 검증되지 않고 남은 위험을 말한다. "검증되지
않음"은 정당하고 유용한 결과다; 그것에 대한 침묵은 아니다.
