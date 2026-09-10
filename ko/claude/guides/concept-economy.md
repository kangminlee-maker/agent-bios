---
guide_id: concept-economy
language: ko
status: active
use_when:
  - 오래 남거나 공유되는 이름을 짓는 모든 경우 — feature, entity, type, field, flag, enum 값, failure kind, artifact, 문서 용어
  - review finding이나 테스트 실패를 없애려고 이름을 하나 추가하고 싶어질 때
  - 어떤 값이 독립된 concept인지, 기존 concept의 property인지 정할 때
  - public surface가 무엇을 노출할지와 truth가 실제로 어디 있는지를 구분해 정할 때
  - 레포 레이아웃을 잡거나, 그 형태가 아직 concept graph와 맞는지 판단할 때
core_rules:
  - concept를 추가하기 전에 가장 가까운 기존 concept를 명명하고, reuse / extend / rename / split 중 하나를 소리 내어 고른다
  - 모든 수정에는 concept surface의 부호가 있다 — 줄이는지, 유지하는지, 늘리는지를 수정 전에 말한다
  - 값 하나에 owner 하나, 나머지 surface는 restate가 아니라 generate한다
---

# Concept Economy

전역 Concept Economy 섹션의 scoped extension이다. 그 변경보다 오래 살아남을 이름을 도입하거나
바꾸려 할 때 사용한다.

이 가이드가 관리하는 비용은 디스크나 토큰이 아니라 **읽는 쪽의 working set**이다. 시스템 안의
서로 다른 이름 하나하나는 사람이나 모델이 붙들고, 구분하고, 형제 개념들과 정합을 맞춰야 하는
대상이다. 하나의 동작에 이름이 둘이면 그것은 중복이 아니라 — 한쪽만 고치고 다른 쪽은 두게 만드는
상시 초대장이며, 그 divergence는 production에서 뭔가 깨질 때까지 조용하다.

## 무엇이 concept인가

**오래 남거나 공유되는 것** 전부다. 목록이 일부러 긴 이유는, 비싼 추가가 architecture처럼
느껴지는 경우가 드물기 때문이다:

feature, entity, 변수, type, helper module, artifact, config key, CLI flag, MCP/tool field,
public response field, artifact field, enum 값, failure kind, retry/recovery token, process 이름,
문서 용어.

concept가 *아닌* 것: transient local, generic container(`items`, `result`, `tmp`), 그리고
framework나 tooling이 강제하는 layout. 판별 기준은 **두 번째 사람이 여기서 일하려고 그 이름을
배워야 하는가**다. loop 변수는 그 선을 넘지 않고, 새 failure kind는 enum 안의 문자열 하나여도
항상 넘는다.

함정은 scale-blindness다. response에 추가한 field는 diff 한 줄이자, 아직 만나지 못한 consumer를
포함한 모든 consumer의 mental model에 영구히 얹히는 항목이다.

## 네 가지 경로

concept를 추가하거나 바꾸기 전에 가장 가까운 기존 concept를 찾고 경로를 **명시적으로** 고른다.
조용히 고르는 것이 near-duplicate가 생기는 방식이다: 아무도 두 번째 이름을 추가하기로 결정하지
않았고, 그저 첫 번째를 찾아보지 않았을 뿐이다.

| 경로 | 고르는 시점 | 그때 지는 의무 |
| --- | --- | --- |
| **Reuse** | 기존 concept가 이미 그 동작을 포괄한다 | 없음 — 기본값이며 정당화가 필요 없다 |
| **Extend** | property 하나를 더하면 기존 concept가 포괄한다 | 그 property, 그리고 기존 reader가 그 부재를 견디는지 확인 |
| **Rename** | 동작은 맞고 이름이 동작에서 멀어졌다 | 모든 site를 한 번의 변경으로 — 반쪽 rename은 양쪽 이름 어느 것보다 나쁘다 |
| **Split** | 아래 split 트리거가 실제로 발동했다 | parent 명명, 이유 진술, alias의 canonical 매핑 |

좁은 near-duplicate보다 정밀한 property를 가진 넓고 안정적인 concept를 선호한다. lifecycle을
공유하는 한 `kind` property를 가진 `Job`이 `ImportJob` / `ExportJob` / `CleanupJob`보다 낫다;
lifecycle 공유가 끝나는 순간 그것은 naming 취향이 아니라 split 트리거다.

### 가장 가까운 concept 찾기

"가장 가까운 기존 concept를 찾으라"는 지시는 **이미 머릿속에 있는 이름으로 검색할 때** 실패한다.
방금 만들어낸 이름은 거기 없을 것이고, 그 부재가 허가처럼 읽힌다. 대신 **동작**으로 검색한다:

- concept 자체가 아니라 그것이 만들어낼 어휘를 grep한다: enum 값, failure 문자열, field 이름,
  log 메시지.
- 형제 concept의 이름이 아니라 정의 전체를 읽는다. 이름은 coverage를 과소 진술한다 — `Session`
  이라는 type이 따로 이름 붙이려던 lifecycle을 이미 담고 있는 경우가 흔하다.
- 기존 concept가 여기서 틀리려면 무엇이 참이어야 하는지 묻는다. 그것을 동작 차이로 진술할 수
  없으면 동의어를 추가하고 있는 것이다.
- 코드보다 먼저 레포가 이미 운영하는 terminology surface — lexicon, glossary, domain manifest —
  를 본다. 더 짧고, 의도적으로 내린 결정이 거기 있다.

그 검색이 아무것도 반환하지 않으면 그 추가는 아마 진짜다. 무엇을 검색했는지 기록한다. 그러지
않으면 다음 사람이 같은 검색을 반복한다.

## 언제 split하는가

split은 두 대상이 **caller가 관찰할 수 있거나 처리해야 하는 것**에서 다를 때 정당하다. 아래가
트리거이고, 나머지는 취향이다:

runtime 동작 · ownership · lifecycle · validation · failure mode · 사용자에게 보이는 동작 ·
audit/replay 요구 · authority · persistence · 사용자 제어 · failure handling

트리거가 아닌 것: 다른 call site, 다른 caller, 길어진 함수, reviewer의 불편함. 이것들은
property, parameter, comment를 추가할 이유다.

split이 필요하면 세 가지가 함께 나가야 하며, 아니면 그 split은 부채를 남긴다:

1. **parent를 명명한다.** 무엇에서 갈라져 나왔는지를 그 변경 안에 명시적으로.
2. **이유를 진술한다.** 어떤 트리거가 발동했는지 한 문장으로, maintainer가 찾을 위치에.
3. **variant를 되돌려 매핑한다.** alias, deprecated 표기, 옛 값이 canonical concept로 해소되게
   한다 — 아니면 옛 이름이 아무도 선언하지 않은 두 번째 concept로 살아남는다.

## derived 값은 derived로 둔다

tool이나 code가 source에서 계산할 수 있는 값은 그 source의 **property나 projection**이지 독립된
concept가 아니다. 그것을 persist하면 첫 번째와 불일치할 수 있는 두 번째 authority가 생기고,
실제로 그렇게 된다: source는 움직이고 사본은 움직이지 않는다.

판별 기준은 **저장된 값을 읽는 쪽 중에 그것을 스스로 도출할 수 없었던 것이 있는가**다. 없다면
그 값은 잘해야 cache이고 나쁘면 모순이다.

**authority는 visibility가 아니다.** 별개의 질문이며, 둘을 뭉개면 두 가지 실패가 동시에 난다:

| | 질문 | 틀린 답의 모습 |
| --- | --- | --- |
| Authority | truth가 어디 있고 누가 바꿀 수 있는가 | writer가 둘, 또는 derived 사본이 source보다 우선함 |
| Visibility | 주어진 surface가 무엇을 볼 수 있는가 | internal projection이 public contract로 새어 나가 이제 바꿀 수 없음 |

public response는 bounded view — 더 적은 field, 더 거친 정밀도, 렌더된 형태 — 를 노출할 수 있고,
그동안 truth의 위치는 source concept나 artifact에 남는다. 그것이 projection이고 올바르다. 올바르지
않은 것은 잘못된 값을 **projection에서 고치는 것**이다.

사용자 동작, 제품 contract, artifact truth가 실제로 요구하지 않는 한 internal projection과 helper
출력은 internal로 둔다. 한 번 노출한 field는 이쪽 일정대로 회수할 수 없다.

## 어휘는 늘리기 전에 재사용한다

enum 값, failure kind, retry/recovery token, result/failure surface는 blast radius가 유난히 큰
concept다: 모든 consumer의 branch coverage가 그 집합의 안정성에 의존한다. 값을 하나 추가하면
exhaustive reader 전부가 그것을 처리해야 하고, near-synonym을 추가하면 처리에 더해 **둘 중 무엇이
실제로 올지 추측**까지 해야 한다.

기존 집합을 먼저 확인하고, 케이스를 더 정밀하게 서술하는 새 값보다 의미가 그 케이스를 실제로
포괄하는 기존 값을 선호한다. 집합을 파편화시키는 정밀도는 얻는 것보다 비싸다.

## 수정을 분류한다

review finding이나 테스트 실패를 고치기 전에, 그 수정이 active concept surface를 어느 쪽으로
움직이는지 말한다:

- **줄임** — 이름을 없애거나, 중복을 합치거나, branch를 지운다. 가장 싸고, finding이 "이 둘은 같은
  일을 한다"일 때 대개 가능하다.
- **유지** — 기존 이름 안에서 동작을 바꾼다. 일반적인 경우다.
- **늘림** — 이름을 추가한다. 정당할 수 있지만 네 경로 질문을 통과해야 하고, review finding 자체는
  concept를 추가할 이유가 되지 못한다.

이것이 중요한 이유는 review finding이 **늘리는 쪽으로 압력**을 만들기 때문이다: flag, kind,
special case를 추가하면 finding은 국소적으로 사라지지만 나머지 모두가 지는 surface는 넓어진다.
변경 전에 방향을 명명하는 것이 그 거래를 의도적으로 유지하는 방법이다.

## Migration 호환

**명시적 migration 호환이 요구될 때는** fallback path, compatibility shim, deprecated alias
normalization을 **쓴다** — 의무는 양방향이다: 요구되는 호환에는 shim을 대고, 기본 hedge로는
아무것도 대지 않는다. 각각은 유지되고 결국 제거되어야 하는 두 번째
concept surface다.

하나를 추가할 때 제거 조건도 함께 나간다: 그 shim이 사라지려면 무엇이 참이어야 하고, 그것이 어디
기록되는지. 끝이 진술되지 않은 호환 경로는 방치로 영구 architecture가 된다.

## 형태를 탐색 가능하게 유지한다

레포의 형태가 concept graph를 반영하게 한다. 공유되고 오래가는 concept의 canonical 이름은 그것이
나타나는 모든 layer — path, module, type/interface, field, public API — 를 가로질러 추적 가능해야
하고, 그래서 구조를 이미 알고 있어야만 쓸 수 있는 translation table이 아니라 concept 이름에서
추측할 수 있어야 한다.

실무 기준: concept 이름은 알지만 이 레포는 모르는 사람이 path를 추측하거나 grep 한 번으로 찾을 수
있어야 한다. schema에서는 이 이름, module에서는 저 이름, URL에서는 또 다른 이름이라는 걸 알아야만
찾을 수 있다면 그 layout은 탐색 가능하기를 그만둔 것이고, 이름들이 일하는 대신 해를 끼치고 있다.

이는 공유 concept에만 적용된다. transient local, generic container, framework나 tooling이 강제하는
layout은 벗어날 수 있고, 그것들을 억지로 맞추는 것은 그 자체로 낭비다.

## 도메인 노트

- **ontology 작업.** entity와 relation은 추가·수정·제거·재연결 어느 쪽이든 먼저 기존 것을 확인한다; 그래프는 중복으로
  가치가 가장 빨리 떨어지는 artifact다 — 노드가 하나 늘 때마다 reader가 고려해야 할 edge가 곱으로
  늘기 때문이다.
- **코드 작업.** repository가 이미 쓰는 naming 패턴을 — 그 파일 먼저, 다음은 이웃 — 따르고, 이번 변경이 만든 변형은 done이라고
  하기 전에 통합한다. 하나의 아이디어에 표기가 셋 남은 변경은 의도와 무관하게 concept를 두 개
  추가한 것이다.
- **comment와 active 문서.** 현재 runtime 동작, failure semantics, retry 정책, ownership,
  authority와 정합을 유지한다. 폐기된 contract를 서술하는 comment는 낡은 문서가 아니라 **두 번째
  거짓 authority**이며, 그것을 먼저 발견한 사람에게는 현재로 읽힌다.
