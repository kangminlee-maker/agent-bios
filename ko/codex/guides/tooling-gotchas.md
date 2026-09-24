---
guide_id: tooling-gotchas
language: ko
status: active
use_when:
  - shell command의 exit code나 output이 pass/fail 또는 verification 판정을 gate할 때
  - tool이 다른 evidence와 모순되는 empty / no-match / not-found output을 낼 때
  - range에 대해 git diff를 돌리거나, local 변경이 있는 worktree로 pull할 때
  - dynamic하거나 untrusted한 문자열을 shell command line에 넘길 때
  - cloud/managed-service CLI, update API, secret을 담은 config를 다룰 때
  - subprocess나 long-lived handle을 spawn할 때
core_rules:
  - outcome이 ambient state(interpreter, CLI context, command resolution)에 의존하면 그것을 pin한다
  - piped command의 exit code는 마지막 stage만 반영한다 — test 대상 stage를 직접 capture한다
  - 뜻밖의 empty output은 world fact이기 전에 tool artifact 가설로 다룬다
  - git two-dot diff는 range exclusion이 아니라 snapshot comparison이다; pull 전에 dirty worktree를 보호한다
  - spawn한 것의 lifecycle 전체를 소유한다
---

# Tooling Gotchas

전역 원칙 뒤에 있는 구체적인 tool 수준 함정들이다. Claude·Codex 공통 hook injection은
이 파일에서 텍스트를 derive한다 — 편집은 여기서만 하고, hook data에서는 절대
하지 않는다(single source of truth).

## Ambient state drifts — pin it

전역 규칙의 instance다: ambient state는 조용히 drift한다; outcome이 그것에
의존하면 환경을 신뢰하는 대신 explicit하게 pin한다.

- **Interpreter**: 기본 shell은 머신마다 다르고(zsh/bash/dash) bash-only
  idiom은 다른 곳에서 조용히 오동작한다(unquoted-variable word splitting,
  `read -r -d ''` hang). command마다 shell을 probe하지 말고 shell identity를
  무의미하게 만든다: inline one-liner는 POSIX-portable하게 유지하고,
  bash-specific 기능(array, `read -d`, `PIPESTATUS`)이 필요하면
  `#!/bin/bash` script file이나 `bash -c '…'`로 interpreter를 pin한다. session
  environment block이 이미 shell을 선언해 두었으니 그걸 공짜로 읽고, probe는
  오동작을 진단할 때만 한다.
- **Command resolution**: command 이름은 고정된 binary가 아니다 — interactive
  shell은 function/alias를 먼저 resolve하고, programmatic spawn은 raw PATH를
  resolve하며, 같은 이름의 package가 system tool을 가려 조용한 empty output을
  낼 수 있다. execution context를 넘어 결과를 신뢰하기 전에 resolve된 대상을
  확인한다(`type -a`, absolute path). prefix wrapper가 빠져도 똑같이 조용히
  실패한다 — GNU `timeout`은 BSD 계열 시스템에 흔히 없다 — 그러니 wrapper도
  함께 확인한다.
- **Cloud CLI context**: gcloud/aws/kubectl/terraform은 세션 사이에 drift하는
  mutable ambient context(active project, profile, cluster)를 갖는다.
  environment에 영향을 주는 첫 command 전에 — 또는 resume 직후에 — intent에
  대조해 확인하고, global default를 한 번 고치는 대신 매 command마다
  target을 explicit하게 pin한다(`--project`, `--profile`, `--context`).
  forge CLI(`gh`/`glab`)도 checkout의 remote에서 자신이 다룰 repository를
  읽는다: fork와 upstream이 함께 있으면 엉뚱한 repo에 대해 답할 수 있으니,
  그 답이 결정으로 이어지는 곳에서는 `--repo`를 넘긴다.
- **Installed is not running**: live process는 재시작되거나 reload되기
  전까지 옛 코드를 유지한다. update, config 변경, dependency bump가 적용됐는지
  확인할 때는 on-disk artifact에서 멈추지 말고 실행 중인 process의 실제
  version/동작을 확인하거나 재시작을 강제한다.
- **Producer가 consumer보다 새로울 때**: 배포된 binary가 내가 만든
  artifact(서명된 config나 manifest)를 검증한다면, 그 binary가 빌드된 바로 그
  commit으로 checkout한 producer tooling으로 그것을 만들고 검증한다 — 현재
  tree의 tooling으로 하는 local verify는 더 새로운 tooling이 그것을 받아들인다는
  사실만 증명한다. consumer의 build commit은 현재 branch가 아니라 image
  provenance에서 확인한다; 버전 불일치는 무엇이든 release blocker다. 같은
  commit에서 다시 빌드한 consumer라면 통상적인 검증으로 충분하다.
- **dev라고 이름 붙은 datastore target은 주장일 뿐이다**: localhost URL이나
  export한 override는 그 target이 non-production이라는 증거가 아니다 — 로컬
  포트가 유일한 실제 인스턴스로 proxy될 수 있고, tool의 config loader가 내가
  export한 값 위에 dotenv를 다시 읽어 덮을 수 있다. 처음으로 쓰기를 수행하는
  command(migration, seeder) 전에, 그 connection이 무엇에 닿는지를 tool 자신의
  경로 안에서 출력하고 그것이 의도한 target인지 assert한다; loader를 믿을 수
  없는 곳에서는 DDL을 추출해 직접 적용한다.

## Shell execution traps

- **Pipe exit masking**: pipeline 뒤의 `$?`는 마지막 stage만 반영한다; 앞쪽
  stage의 real failure가 성공한 `tail`/`grep`/`jq`에 가려져 green으로 읽힌다.
  test 대상 stage 자신의 status를 capture한다: unpiped로 돌리거나, `$?`를 즉시
  저장하거나, `set -o pipefail`/`PIPESTATUS`를 쓴다 — pipefail이 early-exit
  consumer(`cmd | head -1`, 긴 producer에 건 `grep -q` → SIGPIPE 141)를
  깨뜨리므로 이는 command별 선택이다. 마지막 stage가 곧 assertion인 경우의
  예외(`cmd | grep -q pattern`)는 pipefail이 없을 때만 성립한다; pipefail
  아래에서는 output을 capture하고 그 status를 먼저 확인한다.
- **직접 만드는 CLI의 passthrough 인자**: 다른 명령의 플래그를 실어 나르는
  옵션에는 "탐욕적이지만 대시에서 멈추는" 개수를 쓸 수 없다 — Python의
  `nargs="+"`는 `-`로 시작하는 첫 토큰에서 끝나므로, 감싼 명령의 `--model x`가
  다음 positional로 흘러들어가고 에러는 호출자가 말한 적 없는 파라미터를
  지목한다. 파서의 "이후 전부" 형태(`argparse.REMAINDER`)를 쓴다. 맨 `--`
  구분자는 별개의 두 번째 함정이다: argparse가 그것을 자기 positional 표식으로
  remainder보다 먼저 삼키므로, 모든 호출자가 처음 손대는 형태가 바로 깨지는
  형태다 — 파싱 전에 `argv`에서 정규화해 없앤다.
- **실행되어 버리는 CLI flag probe**: CLI는 실제 작업을 할 수 없는 형태로만
  probe한다 — help 형태이거나, 후보 flag를 실행을 금지하는 control
  flag(dry-run, 유효하지 않은 required argument)와 짝지은 형태다. subcommand를
  맨몸으로 돌리지 않고, flag 뒤의 값이 positional input으로 읽힐 수 있다고
  가정한다: boolean flag는 그 값을 소비하지 않으므로 값이 흘러내려 실행이
  일어난다. boolean인지 등록되지 않은 flag인지는 실행이 성공했다는 사실이
  아니라 parser의 error로 판별한다.
- **Reserved parameter names**: reserved shell 이름(`UID`, `EUID`, `GID`,
  `PPID`)에 대입하면 값을 저장하는 대신 bound된 system 동작을 invoke할 수
  있다 — script 중간에 조용히 process credential을 바꾼다. reserved되지 않은
  이름을 쓴다; 그런 대입이 side-effecting command와 함께 이미 실행됐다면, 그
  실수가 command를 막았다고 가정하지 말고 결과 system state를 직접 확인한다.
- **Metacharacter-bearing values**: `$`, backtick, quote, glob을 담을 수 있는
  prompt, 파일명, content 문자열은 raw CLI argument로 inline하면 안 된다 —
  target process가 보기 전에 shell이 그것을 expand하거나 망가뜨린다. stdin,
  heredoc, temp file로 넘긴다. (우리 dispatch script인
  codex-run/codex-helm은 이미 stdin을 받는다 — 그 경로를 쓴다.)
- **Multi-line pasted commands**: continuation marker 없이 여러 줄에 걸쳐
  붙여넣은 command는 두 개의 invocation으로 다시 wrap되어 trailing flag를
  조용히 떨어뜨릴 수 있다(실제 사례: auth flow 중 `--scopes`가 사라져 →
  wrong-scope credential). 하나를 실행한 뒤 target의 실제 state(부여된
  scope, 적용된 setting)를 확인한다; 재실행할 때는 한 줄로 합치거나 explicit
  continuation을 쓴다.

## Tool output is a rendering, not the bytes

- **grep binary heuristic**: grep은 heavy non-ASCII거나 NUL을 담은 text
  file을 조용히 binary로 취급해서 error 없이 false no-match를 낸다. no-match가
  다른 evidence(git diff, 이전 read)와 모순되면 harness의 Grep tool(ripgrep)이나
  `grep -a`로 다시 확인하거나 파일을 직접 읽는다.
- **Viewer normalization**: file-read tool은 non-printable byte(NUL)를
  시각적으로 구별되지 않는 빈칸으로 render할 수 있다. correctness가
  byte-exact content(delimiter, encoding)에 걸려 있으면 rendered view가
  아니라 `hexdump`/`od`나 byte-comparing script로 확인한다.
- **Stale caches in rapid loops**: mtime/size로 키를 잡는 compile이나
  rewrite cache는 mutate→test cycle이 timestamp 해상도 안에서 돌면(mutation
  testing) 이전 파일의 결과를 다시 낼 수 있다. cache를 지우거나 iteration마다
  no-cache로 돌리고, cache clear 뒤 unmutated baseline이 여전히 통과하는지
  재확인한다.
- **transport limit은 provider의 단위로, wire payload 위에서 측정된다**:
  단위와 값은 provider의 rejection이나 live probe에서 가져오고 docs나 변수
  이름에서 가져오지 않으며, 내가 조립한 객체가 아니라 consumer가 실제로 받는
  serialized payload를 — encoding과 wrapper를 거친 뒤에 — 측정한다. byte
  limit에 character count를 대면 multibyte 텍스트를 적게 세고, input이 ASCII인
  동안은 그 사실이 숨는다; item count는 어떤 크기도 bound하지 않는다. dispatch
  chokepoint 한 곳에서 강제하고, 모든 budget을 그 상수에서 derive한다.

## Git operations

- **뒤처진 로컬 base가 range를 부풀린다**: branch가 무엇을 담고 있는지 추론하거나
  PR을 열기 전에 `git fetch`를 돌리고, 로컬 tracking ref가 아니라 remote 기준으로
  묻는다 — 어떤 commit이 내 것인지는 `git log origin/<base>..HEAD`, diff는 아래의
  merge-base 형태. 공유 repo에서는 pull하기 전까지 로컬 base가 뒤처지므로
  `<base>..HEAD`는 이미 merge된 작업을 조용히 끌어들인다. range가 놀랍게 크면
  branch보다 base를 먼저 의심한다.
- **"mergeable"은 sibling이 아니라 base 기준이다**: 플랫폼 flag는 각 PR이 base에
  merge된다는 뜻이고, 두 PR이 각각 깨끗하면서 서로 충돌할 수 있다. merge 순서를
  정하기 전에 changed-file set을 diff하고 그 순서를 simulate한다.
- **Two-dot diff semantics**: `git diff A..B`는 direct snapshot
  comparison이다 — `git log A..B`와 달리 아무것도 exclude하지 않으므로,
  뒤처진 merge-base가 무관한 upstream 변경을 diff에 주입한다. PR/review
  diff에는 `git diff origin/base...HEAD`(merge-base form)를 쓴다; diff가
  너무 크거나 건드리지 않은 파일에 deletion이 보이면 이 메커니즘을 먼저
  의심한다.
- **경로를 되돌리는 것은 내 편집을 취소하는 게 아니다**: `git checkout <path>`와
  `git restore <path>`는 그 파일의 *모든* 미커밋 변경을 버린다. 심어둔 프로브를
  치우려고 쓰면 그 파일에 진행 중이던 다른 것까지 함께 사라지고, 그 손실은
  조용하다. 먼저 `git diff <path>`를 확인하거나, 사본에 심고 사본에서 복원한다.
  같은 비대칭이 복원 단계도 취약하게 만든다 — 프로브가 타임아웃되거나 중단될 수
  있으면 복원을 같은 호출의 다음 명령으로 두지 말고, 실패가 건너뛸 수 없는 곳에 둔다.
- **ignore rule이 durable record를 삼킬 수 있다**: 어떤 경로를 durable하다고
  — 새 ledger, 인용되는 authority라고 — 다루기 전에 `git check-ignore -v
  <path>`와 `git ls-files --error-unmatch <path>`를 돌린다. 넓은 runtime-state
  패턴(`*.jsonl`, `runs/`, `out/`)은 새 파일을 흡수하고, ignore된 경로를
  가리키는 tracked 파일은 한 checkout에만 존재하는 authority다. 계속 ignore되는
  sibling으로 증명한 negation rule로 고치고, 정말로 ephemeral한 output은
  ignore된 채로 둔다.
- **Dirty-worktree pulls**: staged/unstaged/untracked 변경이 있는
  worktree로 pull하기 전에 먼저 fetch하고 들어오는 경로를 모든 dirty
  경로와 비교한다; overlap이나 non-fast-forward가 있으면 멈추고 conflict
  위험을 없앤다(stash, commit, 질문). 그렇지 않으면 `--ff-only`로 pull하고,
  dirty 변경이 살아남았는지 확인하고, input이 갱신된 local derived
  artifact를 재생성한다.
- **쪼갠 commit 계열은 commit 하나하나로 증명한다**: 의존 순서대로 정렬하고,
  각각을 버려도 되는 worktree로 checkout해 push 전에 build, test, gate를
  돌린다. tip에서만 green이면 깨진 bisect 지점과 혼자서는 revert할 수 없는
  commit이 숨는다 — 대개 rename이나 공유 hunk가 엉뚱한 commit에 들어간
  경우다. handoff가 그 branch의 hash를 인용한다면 merge commit으로 merge한다:
  squash와 rebase는 모든 hash를 다시 쓴다.
- **공유 tree에는 다른 작업자의 작업이 들어 있다**: 내가 만들지 않은 commit,
  editor가 디스크에서 바뀌었다고 알리는 파일, 내가 add한 적 없는 staged 경로,
  예측한 post-state보다 하나 많은 field — 설명되지 않는 delta는 noise가 아니라
  다른 사람의 작업으로 다룬다. 광범위한 쓰기(`git add -A`/`.`, `commit -a`,
  `stash`, `clean`, `reset --hard`) 전에 그 출처를 밝히고(`git status`, reflog
  timestamp, 다른 live 세션), 내 것이라고 증명할 수 있는 것에만 작용한다 —
  이름으로 add한다.

## Config, secrets, and managed services

- **Verbatim slicing over parse-reserialize**: secret과 comment를 담을 수
  있는 사용자의 structured config(TOML/YAML/INI) 일부를 provisioning할
  때는 parsing 후 re-serializing하는 대신 그 section의 raw text를 추출한다
  — rewrite는 comment, formatting, secret 값을 조용히 떨어뜨린다. parser는
  real structural change에만 쓰고, slicer는 실제 shape에 먼저 테스트한다.
- **Merge-not-replace update APIs**: managed-service update call(secret
  rotation, mount 변경)은 흔히 새 definition을 기존 set에 merge해서, stale하고
  참조되지 않는 definition을 live로 남긴다. update 후에는 resource를
  다시 읽고, definition과 active reference를 따로 확인하고, orphan을
  explicit하게 제거한다.
- **새 revision은 template이 아니라 live revision에서 derive한다**:
  replace-semantics update는 command가 다시 진술하지 않은 모든 field를
  떨어뜨리고, wrapper는 흔히 mount된 secret을 off로 default한다. command가
  실제로 보낼 field 집합을 live resource에서 derive해 그대로 렌더하고 field
  단위로 diff한다; 사라지는 field나 뒤로 물러나는 operational 값은 받아들일
  default가 아니라 설명해야 할 blocker다. command가 자신의 semantics를 표시하는
  일은 드물므로, 그 뒤에 resource를 다시 읽는다.
- **A new revision is not live traffic**: named revision에 트래픽을 pin한
  runtime(예: fixed split을 건 Cloud Run)에서는 `gcloud run deploy`(또는 그
  equivalent)가 새 revision을 만들 뿐 트래픽을 옮기지 않는다 — 명시적인
  `gcloud run services update-traffic` 전까지는 이전 revision이 계속 서빙한다.
  "deploy succeeded" 메시지는 "revision이 존재한다"로 읽되 "새 코드가
  서빙된다"로 읽지 않는다; deploy가 실제로 반영됐다고 결론짓기 전에 라이브
  트래픽 split을 확인한다.
- **job log는 execution보다 오래 남는다**: 한 이름으로 두 번 이상 돈 managed
  job은 — 삭제 후 같은 이름으로 다시 만든 경우까지 포함해 — job 이름으로 log를
  읽으면 이전 incarnation의 output을 돌려준다. 모든 읽기를 launch 때 받은
  execution id로 scope하고, timestamp 창이 그 run을 덮는지 확인한다. scope하지
  않은 읽기는 이전 run들을 현재로 합쳐, scope된 읽기가 뒤집게 될 확신에 찬
  오진을 낳는다.
- **dispatch status는 execution이 아니다**: CLI `--wait`가 돌아오거나
  timeout되는 것, scheduler가 성공을 보고하는 것, trigger가 error 없이
  받아들여지는 것 — 각각은 dispatcher가 본 것을 보고할 뿐, target이 실제로
  돌았는지 어떤 state에 이르렀는지를 말하지 않는다. 재시도하거나 완료를
  선언하기 전에 target 자신의 record(execution describe, handler의 log)에서
  id로 run을 맞춰 state를 다시 derive하고, 수동 probe는 scheduled probe와
  구별되게 둔다. 눈감고 다시 launch하는 것은 side effect를 동반한 중복
  execution이다.
- **confirmation 전에 끊긴 apply는 unconfirmed다** — 완료도 미실행도 아니다:
  side effect가 있는 multi-statement apply(migration, batch write)가
  confirmation 채널을 잃으면, 대상 object 중 무엇이 이미 store에 존재하는지
  열거하고 그 부분 상태에서 rerun을 계획한다; 순진한 rerun은 "already
  exists"에서 반쯤 실패해 두 번째 부분 상태를 남긴다. runner가 exit status만
  노출하는 경우에는 의도적인 실패를 통해 object 목록을 밖으로 빼낸다.
  transactional하거나 idempotent함이 증명된 apply라면 confirmation만 있으면
  된다.
- **traffic rollback은 config rollback이 아니다**: revision에 트래픽을 pin한
  runtime에서 이전 revision으로 트래픽을 되돌리면 동작은 복구되지만, 추가한
  env var나 secret binding은 service template에 남아 다음 deploy에서 조용히
  다시 켜진다. 트래픽 split과 service spec이 둘 다 이전 상태로 돌아왔을 때에만
  rollback을 완료로 센다 — spec을 다시 읽고 그 변경을 explicit하게 제거한다.
  이전 spec 자체를 다시 배포하는 runtime(immutable-artifact, GitOps)에는 그런
  틈이 없다.
- **Perimeter controls need the enforcement point's own logs**: agent-side
  fetch는 독립적인 observer가 아니다 — egress IP와 caching 경로가 opaque하고,
  protected network를 공유하거나 stale한 cached response를 낼 수 있다. allow와
  deny 방향 모두를 그 log로 확인하고, front-side cache/CDN은 따로 확인한다.
  probe는 app이 credential 없이도 답하는, 보호 대상 unit 안의 sentinel을
  겨눈다: app이 어차피 내놓는 denial은 control이 꺼져 있어도 통과하고, 그리로
  향하는 redirect는 bypass다. IP 기반 rule이 비교하는 address는 그
  enforcement point에서 선택된 것이며, configuration만으로는 어느 것인지
  확정되지 않을 수 있다: proxy나 CDN 뒤에서는 configure된 forwarded-header
  trust chain이 app에 건네는 client address일 수 있고, managed platform은
  특정 destination을 원래 configure된 NAT path 바깥으로 라우팅할 수 있다 —
  GCP에서는 `privateIpGoogleAccess: false`에도 불구하고 Google API 트래픽이
  Cloud NAT address를 쓰지 않았다. allowlist나 perimeter rule을 작성하거나
  편집하기 전에, 실제 workload와 destination에 대해 enforcement point에서의
  address를 관찰하고, 다른 값을 보여야 하는 control path도 함께 둔다.
- **Locating a credential must not print it**: secret의 위치를 찾거나 설정
  여부를 확인하려는 command도, 그 값을 transcript로 emit하면 노출시킨다 —
  env file을 `cat`하는 것, `printenv`, `echo $TOKEN`, `-w`를 쓴 keychain
  read, match가 secret line인 grep이 그렇다. secret character를 하나도
  emit하지 않고 존재 여부, length, shape를 확인한다(`[ -n "${X:-}" ]`,
  `wc -c < file`, key 이름만 나열하기, nonprinting format check).
  consumer가 실제로 필요로 할 때만 environment나 credential store에서
  값을 직접 읽게 둔다. 부분 prefix조차 출력하지 않는다. transcript에
  도달한 값은 노출된 것이다: rotate한다.
- **노출을 조이는 것은 외부 client에게는 동작 변경이다**: ingress mode를
  바꾸거나 allowlist를 추가하거나 auth를 요구하는 일은, 호출자가 내 redeploy
  바깥에 살 때는 안전하지 않다. 어떤 client가 어떤 hostname으로 그 endpoint에
  닿는지 열거하고, client 쪽 시점에서 확인하고, inbound 물량이 0으로 떨어지지
  않았는지 확인한다 — 내가 끊어 버린 client는 내 쪽에 아무 error도 남기지
  않으므로, enforcement-point log만으로는 ingestion을 조용히 끊을 수 있다. 같은
  변경에서 함께 redeploy하는 호출자라면 통상적인 deploy 확인으로 충분하다.
- **Smoke limits outlive the smoke test**: env var/flag/config에 남은 item
  cap, sample size, row limit은 나중의 "full-scale" run이 slice에서 조용히
  성공하게 만든다. 그것을 지우거나 부재를 explicit하게 확인하는 것이 full
  run 선언의 precondition이다.
- **remote handle은 읽은 그 순간에만 유효하다**: 자동 정렬되는 sheet의 row
  index, 호스팅된 파일의 내려받은 사본 — 각각은 내 읽기와 내 쓰기 사이에
  움직인다. 쓰기 전에 live source에서 target을 다시 확립한다: row는 기억한
  위치가 아니라 key column으로 다시 찾고, 쓴 뒤에 key가 일치하는지 assert한다;
  원본의 version을 내가 편집한 사본과 비교하고, 움직였으면 다시 내려받아 편집을
  다시 적용한다. 로컬의 single-writer 파일에는 이 중 아무것도 필요 없다.
- **packaging과 ignore rule은 내 tree가 아니라 경로와 환경으로 판정된다**:
  release 전에 실제 tarball을 pack하고, lifecycle script를 켠 채로 깨끗하게
  설치해 smoke한다 — repo 안에서는 멀쩡한 postinstall hook이 build
  toolchain이 없는 환경에서는 배포된 runtime을 지울 수 있다. 디렉터리를
  옮기거나 이름을 바꾼 뒤에는 모든 ignore rule이 새 경로에 대해 무효다: 거기서
  다시 확인하고 staged diff의 파일 수를 읽는다 — 옛 경로 패턴이 더는 매치하지
  않아 제외됐어야 할 데이터가 stage에 들어온다.
- **Shared live config has concurrent writers**: 공유 state/config
  파일에 대한 자신의 편집이 사라졌거나 corrupt됐다고 결론짓기 전에, 짧은
  live observation(mtime과 자신이 바꾼 field)으로 concurrent writer를
  배제하고, merge/union 연산은 의도한 field로만 scope한다.
- **일률적인 실패는 구조적이다 — 저장된 이유를 읽고 빌드된 artifact를 확인한다**:
  batch의 모든 item이 실패하고 item별 error가 log 바깥(상태 column, 결과
  record)에 저장돼 있다면, key나 quota나 model 가용성을 탓하기 전에 그것을
  읽는다. 그리고 코드가 working directory에서 sibling 파일을 읽는다면, 빌드된
  image 안에서 그 파일들을 나열하거나 hash해 거기에 존재함을 증명한다:
  선별적인 copy는 repo 쪽 검사를 모두 통과하고 runtime에서만 실패한다.
- **Production probes expose data**: production store에 대한 기본
  diagnostic query는 read-only server-side aggregation(count, type,
  presence, hash)으로 한정한다 — raw payload를 log, prompt, transcript로
  절대 끌어오지 않는다 — 그리고 결정 후 scratch probe resource를 삭제한다.
- **build-context ignore 패턴은 root에 anchor된다**: `.dockerignore`나 root에
  anchor되는 모든 filter에서, 맨 파일명은 context root에서만 매치하고 하위
  디렉터리에서는 결코 매치하지 않으며, 확장자 glob은 같은 용도이면서 다른
  확장자를 단 credential 파일을 놓친다. 배포되는 image에 secret이 없다고 패턴만
  보고 결론짓지 않는다 — 빌드된 artifact 자신의 파일시스템에서 credential
  모양의 파일(env 파일, key, service-account JSON)을 나열하는 것을 이름 붙은
  negative control로 두고, build context나 ignore 파일이 바뀔 때마다 반복한다.
- **revoke는 token 단위가 아니라 grant 단위다**: 사용자의 살아 있는 세션이
  공유하는 client id 아래에서 발급된 무언가를 revoke하면 그 세션들도 함께
  무효화되고, 그 실패는 나중에, 다른 곳에서, 재인증 prompt도 없이 드러난다.
  probe는 자기 혼자 소유한 것만 정리해도 된다 — 최소 scope와 전용 client id를
  쓰고, probe token은 revoke하는 대신 만료되게 둔다. 공유된 grant에 대한
  revoke가 불가피하다면, blast radius를 밝히고 그 시점을 사용자와 맞춘다.

## Own what you spawn

전역 규칙의 instance다: 자신이 만든 것의 lifecycle 전체를 소유한다.

- **Subprocess/handle lifecycle**: subprocess를 만든다는 것은 spawn(process
  group 구성), result 획득, teardown을 소유한다는 뜻이다 — 소유한 stdio
  handle을 닫고, 정확히 그 group을 kill하고(wrapper PID만 죽이면 real
  child가 orphan된다), exit을 기다린다. unref'd된 child handle이나 열린
  stdin pipe는 parent의 event loop를 살려 두어 나머지가 완료된 command를
  hang시킨다.
- **사람에게 건넨 handle은 약속이다**: consent URL을 한 번 건넨 뒤에는, 그
  사람이 아직 행동할 수 있는 동안 그 뒤의 listener를 재시작하거나 port를
  바꾸거나 교체해서는 안 된다 — callback이 도착할 때까지 살려 두거나, 그 링크가
  죽었다고 분명히 말한다. handler는 credential을 write-once로 capture하고 이후
  요청은 무시한다; 순진한 handler는 브라우저의 favicon 요청만으로도 지워지기
  때문이다. 사람에게 다시 클릭해 달라고 하기 전에, 모의 callback으로 handler를
  직접 돌려 본다.
- **stop은 process 목록이 아니라 sink에서 확인된다**: descendant 하나를 놓친
  kill은 그 stage가 끝까지 돌아 publish하게 두고, process 목록은 어느 쪽이든
  깨끗해 보인다. multi-stage run을 멈춘 뒤에는 stop 시각 이후에 쓰인 것이
  있는지 output sink를 나열하고, 있으면 오염된 것으로 보고 되돌린다. rollback
  경로의 retention을 읽는다 — noncurrent-version expiry는 backup이 아니라 복구
  창이다 — 그리고 위험한 run 전에 snapshot을 떠 두고 restore 지점을 timestamp로
  고른다.
- **호출보다 오래 살아야 하는 것은 detach한다**: harness tool call 안에서
  시작한 process는 그 call의 process group에 속한다: 뒤에 붙인 `&`는 call이
  돌아올 때 거둬지고, 다른 background task가 끝날 때 harness가 그 group에
  signal을 보낼 수도 있다. 한 call보다 오래 살아야 하는 것은 harness의
  background 기능으로 띄우거나 완전히 detach해서(nohup/setsid) 띄우고, 진행
  상황은 resume이 읽을 수 있는 durable 파일에 쓴다. 0바이트 output 파일은 그것이
  살아남은 적이 없다는 뜻이다. detach해도 소유는 그대로다 — PID 파일과 정지
  경로를 둔다.
- **이름 substring 조회는 liveness check가 아니다**: `pgrep -f <name>`과
  `ps | grep <name>`은 그 질의를 돌리는 shell 자신의 argv에 매치하고, 같은
  이름을 담은 무관한 process — 다른 세션, 형제 dispatch, launcher 자신의 계획
  텍스트 — 에도 매치한다. dispatch한 job이 살아 있는지 판단할 때는 launch 때
  capture한 PID나 handle, 그 process-group 상태, 또는 그 job 자신의 output
  artifact가 자라는지를 쓴다. substring 조회는 발견용일 뿐이고, 그마저도 앞의
  것들 중 하나로 먼저 확인한 뒤에 쓴다.
