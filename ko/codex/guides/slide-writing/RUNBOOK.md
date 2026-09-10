# 정적 HTML/PDF 작성·검토 페어 실행

이 companion은 요청된 정적 HTML/PDF job을 위한 opt-in 실행 절차다. 형제
[slide-writing guide](../slide-writing.md)가 semantic criteria를 소유하며, 모든
슬라이드와 프레젠테이션 작업의 기본값이다. 이 경로의 모든 role request는 같은
criterion text를 받는다.

요청한 산출물과 검토가 실제로 정적 `section.slide` HTML/PDF 경로를 사용할 수 있을
때만 이 runbook을 쓴다. 요청된 native presentation format은 보존한다. 이 renderer가
그 형식을 bind할 수 없다면 적절한 authoring tool에 primary guide를 적용하고 어떤
runtime check를 하지 않았는지 밝힌다. HTML 산출물로 바꾸거나 무관한 screenshot이 이
paired runtime을 통과했다고 주장하지 않는다.

`<runbook-root>`는 이 파일과 `scripts/` directory를 담는 directory이고, `<job>`은
immutable corpus bundle 밖의 새 directory다. Runtime은 이미 있는 job directory를
거부한다. 입력이나 산출물을 고치면 새 job revision을 쓴다. 모든 명령에서 `--base`는
companion directory를 가리킨다. Criteria source는 그 형제인
`<runbook-root>/../slide-writing.md`다.

## 준비

원본 텍스트, JSON 작업 명세, 필요한 local asset을 제공한다. Criteria에 맞춰 형식과
presentation 값을 명세에 기록한다. HTML runtime에는 정적 `section.slide` element,
같은 페이지 크기, print page break가 필요하다. 명세의 양의 정수 `pages`는 실제
render 결과와 대조한다.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" check
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" prepare \
  --source "<source.md>" \
  --spec "<work-spec.json>" \
  --asset "<optional-local-asset>" \
  --job "<job>"
```

Asset이 없으면 `--asset`을 생략하며, 여러 파일에는 반복해서 쓴다. Asset basename은
고유해야 한다. Asset은 `input/assets/<name>`으로 복사되므로 `output/deck.html`에서
URL은 `../input/assets/<name>`을 사용한다.

`check`는 primary criteria source를 parse하고 validate할 뿐 guide bundle에 쓰지 않는다.
`prepare`는 `<job>/input/slide-writing.md`와 job 전용
`<job>/input/ORACLE.json`을 만들고, 원본, 명세, asset, runtime version과 함께
freeze한다. Guide bundle에는 source `ORACLE.json`도 build command도 없다. 실제 writer에
`writer.md`와 그것이 가리키는 frozen input을 주고 결과를 `<job>/output/deck.html`에
저장한다. 실제 invocation record를 남긴다. Request file만으로 writer가 이를 읽었다는
사실이 증명되지는 않는다.

## 제출된 HTML 렌더링

현재 환경에서 Node executable, Playwright module file, browser executable을 찾아
그 경로를 명시적으로 전달한다.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" render \
  --job "<job>" \
  --node "<node-executable>" \
  --playwright "<playwright-module-file>" \
  --browser "<chromium-browser-executable>"
```

Runtime은 HTML과 asset을 seal한 뒤 그 복사본에 renderer를 실행한다. Renderer는 network
request와 sealed root 밖의 file request를 막는다. Slide style을 주입하지 않는다. PDF,
page image, measurement를 만들고 등록 전에 PDF/HTML page count와 dimension을 확인한다.
임의로 제공한 image는 이 renderer invocation을 대신하지 못한다.

`font_px`는 계산된 CSS 크기를 기록한다. Glyph bound, transform, font loading, 실제
image는 별도 근거로 남는다. Render error가 나면 완료된 render는 남지 않는다. 진단을
보존하고 수정한 시도에는 새 job을 쓴다.

## 화면 읽기를 고정한다

별도 검토 context에 `reader.md`와 그 파일이 열거한 rendered artifact를 준다. 이 첫
관찰 단계에서는 source/specification 내용이나 writer의 설명을 주지 않는다. 생성된
request가 response contract와 typed template을 제공한다.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" observe \
  --job "<job>" \
  --request "<job>/reader-request.json" \
  --payload "<observations-proposal.json>"
```

수락된 관찰은 request binding과 함께 `observations.json`에 저장된다. 그 뒤에만 runtime이
frozen source, specification, observation, 같은 common criteria를 담은 `judge.md`와
`judge-request.json`을 만든다. Packet 분리는 운영체제 수준의 read jail을 만들지 않는다.
실제로 사용한 review context와 수행한 visual inspection을 기록한다.

## 비교하고 제출한다

Judge에게 생성된 judge request와 그것이 열거한 artifact를 준다. 그 request가 낸
contract의 semantic field로 응답하며, 병렬 response schema를 만들거나 거절된 값을
수락된 값으로 바꾸지 않는다.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" submit \
  --job "<job>" \
  --request "<job>/judge-request.json" \
  --payload "<judgment-proposal.json>"
```

Runtime은 누락되거나 중복된 criteria, 맞지 않는 page coverage, 지원하지 않는 evidence
reference, stale input, 잘못된 request를 거부한다. 수락된 record에서 `review.json`을
쓰고 `review.md`를 만든다. 둘 중 어느 것도 독립적으로 편집하지 않는다. Result를
해석할 때 semantic criteria를 적용한다. Structural acceptance는 quality verdict가 아니다.

## 검증 또는 수정

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" verify --job "<job>"
```

모든 consuming command는 자체 preflight check도 수행한다. 편집 내용은 다음에 activate한
corpus snapshot과 다음에 준비하는 job에서 사용할 수 있다. 기존 job은 원래의 immutable
corpus snapshot, freeze한 criterion source, derived oracle, runtime version으로 검증한다.
원래 snapshot을 쓰지 않고 그 job이 기록한 guide나 code path를 바꾸면 binding이 무효가
된다. Job의 source document, specification, asset, HTML, request, 등록된 render/result를
바꿔도 마찬가지다. 이전 job은 그 revision의 근거로 보존하고, current하게 보이도록 상태나
hash를 고치지 말고 새 job을 준비한다.

Immutable guide bundle은 read-only input이다. 모든 job data는 그 밖에 둔다. 설치된
snapshot을 제자리에서 고치지 않는다. 다른 criteria로 하는 local experiment는 공유
guide를 갱신하는 일이 아니라, 별도로 식별한 authoring copy다.

Protocol에는 provider dispatcher나 automatic publishing step이 없다. 사용 가능한
승인된 authoring/review tool을 쓰고 실제 invocation evidence를 보존하며, 실행하지 않은
check나 불확실한 check는 밝힌다. 이 절차는 shared criteria와 binding을 검증한다.
Model interpretation과 visual-detection accuracy에는 별도 근거가 필요하다.
