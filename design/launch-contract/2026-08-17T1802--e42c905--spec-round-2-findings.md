---
created_at: 2026-08-17T18:02:00+09:00
head: e42c905
kind: review
---

# Spec round 2 — the code held against the REVISED invariants specification (raw findings)

Second round under the spec instrument (D-20260817-2284a1), against the revision
`…T1720--4e59154--review-evidence-invariants.md`. Reviewer: `codex exec -s read-only -m
gpt-5.6-sol -c model_reasoning_effort=ultra`; 388,271 tokens. Six code findings (13 in
round 1), two specification defects, three void readings; round-1 closures re-probed for
twins per the packet. Verbatim below.

Reviewed `review-round-20` at `e42c905`. Result: six code findings, two specification defects, and three void readings. All commands below ran from `/Users/kangmin/Documents/agent-bios-fix-tree`, exited 0 with empty stderr, and changed no files.

## Findings

### 1. L6 — a non-`panel` base can reach `achievement=complete`

File/function: [launch/agent-launch.py:review_plan_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1934), `verify_review_receipts`.

The parser rejects `panel` among optional methods but never requires the base itself to be `panel`.

```sh
python3 -c $'import copy,hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda s:hashlib.sha256(s.encode()).hexdigest();C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"model-x","effort":"high","provider":"openai","mechanism":"native","instruction":"","controls":C,"evidence":[]};plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":row,"methods":[]}
for label,mid in (("L6_mutation","renamed-base"),("L6_control","panel")):
 data=copy.deepcopy(plan);data["base"]["method_id"]=mid;report=m["review_plan_from_v1"](data);receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":"child","packet_sha256":h("packet"),"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0};verified,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":h("packet"),"main_dispatch_id":"main","receipts":[receipt]},{mid:C},{mid:()});print(label+"=accepted base_id="+repr(mid)+" has_panel="+str(mid=="panel")+" achievement="+verified.achievement+" verdict="+vs[0].reason)'
```

```text
L6_mutation=accepted base_id='renamed-base' has_panel=False achievement=complete verdict=verified
L6_control=accepted base_id='panel' has_panel=True achievement=complete verdict=verified
```

Proposed fix: require `base.method_id == PANEL_METHOD` in one identity validator shared by parsing and adjudication.

Missed check: [`launcher_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691).

### 2. D6 / V2 / V3 / V4 — no matching offer defaults to empty evidence

File/function: [launch/agent-launch.py:verify_receipts_command](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:8433), [verify_review_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2492).

The launch selector refuses when no `(operation, host)` offer matches. Verification instead leaves the method absent from `required_evidence`, defaults that absence to `()`, and reports complete.

```sh
python3 -c $'import contextlib,copy,hashlib,io,json,runpy,types
m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};M=m["ReviewMethod"]("panel","x","x","x",{"high":"high"},("high",),("x",),1,"fixed",False,"union","cap","op");R=m["ReviewMethodReport"]("panel","OK","perspective_floor","","model-x","high","openai","native","",C,());Q=m["ReviewReport"](R,(),"perspective_floor");h=lambda s:hashlib.sha256(s.encode()).hexdigest();plan=json.dumps(m["review_plan_v1"](Q));receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":h("packet"),"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0};bundle=json.dumps({"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":h("packet"),"main_dispatch_id":"main","receipts":[receipt]})
class P:
 def __init__(s,x):s.x=str(x)
 def expanduser(s):return s
 def read_text(s,encoding=None):return {"plan":plan,"bundle":bundle}[s.x]
 def __str__(s):return s.x
g=m["verify_receipts_command"].__globals__;old=(g["pathlib"],g["load_config"],g["load_review_methods"]);cur={};g["pathlib"]=types.SimpleNamespace(Path=P);g["load_config"]=lambda _:cur["cfg"];g["load_review_methods"]=lambda _:{"panel":M};base={"hosts":{"codex":{"provider":"openai"}},"capabilities":{"cap":{"command":"tool","offers":[{"operation":"op","adapter":"exec-stdio-v1","hosts":["codex"],"evidence":[]}]}}};mut=copy.deepcopy(base);mut["capabilities"]["cap"]["offers"][0]["hosts"]=["claude"]
for label,cfg in (("D6_V4_mutation",mut),("D6_V4_control",base)):
 cur["cfg"]=cfg;binding=m["ReviewBinding"]("openai","codex","model-x","high")
 try:sel=m["derive_review_mechanism"](M,binding,cfg);launch="selected evidence="+repr(list(sel.evidence))
 except Exception as e:launch="refused "+type(e).__name__+":"+str(e)
 out=io.StringIO()
 try:
  with contextlib.redirect_stdout(out):rc=m["verify_receipts_command"]("plan","bundle",P("cfg"))
  verify="rc="+str(rc)+" complete="+str("achievement=complete" in out.getvalue())
 except Exception as e:verify="refused "+type(e).__name__+":"+str(e)
 print(label+" launch_selector="+launch+" verifier="+verify)
g["pathlib"],g["load_config"],g["load_review_methods"]=old'
```

```text
D6_V4_mutation launch_selector=refused LaunchError:capability 'cap' offers no 'op' operation for host 'codex' verifier=rc=0 complete=True
D6_V4_control launch_selector=selected evidence=[] verifier=rc=0 complete=True
```

Proposed fix: use one offer selector for launch and verification. Record a matched offer even when its evidence list is empty; refuse if none matches, and remove `.get(method_id, ())`.

Missed check: [`launcher_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691).

### 3. D2 / F1 — fold-wide dispatch uniqueness is only per method

File/function: [launch/agent-launch.py:_merge_method_passes](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2819), [fold_receipts_command](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2953).

Each method group receives a fresh `seen_ids`, so the public fold emits two receipts with the same dispatch ID.

```sh
python3 -c $'import contextlib,hashlib,io,json,runpy,types
m=runpy.run_path("launch/agent-launch.py");h=lambda s:hashlib.sha256(s.encode()).hexdigest()
def r(mid,did):return {"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":did,"packet_sha256":h("packet"),"result_sha256":h(mid),"provider":"openai","model":"model-x","effort":"high","exit_status":0}
class F:
 def __init__(s,name,data):s.name=name;s.data=data
 def read_text(s,encoding=None):return json.dumps(s.data)
 def __str__(s):return s.name
 def __lt__(s,o):return s.name<o.name
class P:
 files=[]
 def __init__(s,name):s.name=name
 def expanduser(s):return s
 def glob(s,pattern):return [F(str(i)+".json",x) for i,x in enumerate(P.files)]
g=m["fold_receipts_command"].__globals__;oldp,oldh=g["pathlib"],g["_sha256_file"];g["pathlib"]=types.SimpleNamespace(Path=P);g["_sha256_file"]=lambda _:h("packet")
def run(label,items):
 P.files=items;out=io.StringIO()
 with contextlib.redirect_stdout(out):rc=m["fold_receipts_command"]("receipts","packet","main")
 bundle=json.loads(out.getvalue());print(label+"=accepted rc="+str(rc)+" dispatch_ids="+repr([x["dispatch_id"] for x in bundle["receipts"]]))
run("D2_F1_mutation",[r("alpha","shared"),r("beta","shared")]);run("D2_F1_control",[r("alpha","alpha-id"),r("beta","beta-id")]);g["pathlib"],g["_sha256_file"]=oldp,oldh'
```

```text
D2_F1_mutation=accepted rc=0 dispatch_ids=['shared', 'shared']
D2_F1_control=accepted rc=0 dispatch_ids=['alpha-id', 'beta-id']
```

Proposed fix: perform one fold-wide raw-ID scan before grouping, while retaining the per-group check.

Missed check: [`launcher_receipt_adapters`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:5198).

### 4. S3 — an inactive-host FRONTIER contradiction is accepted and normalized away

File/function: [launch/agent-launch.py:build_plan](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:4360), [preset_from_plan](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:5742).

A scalar `frontier_effort="max"` conflicts with an inactive Claude override of `high`. Claude correctly refuses the source, but Codex accepts it and Save As silently emits a Claude preset using only `high`.

```sh
python3 -c $'import copy,pathlib,runpy,tomllib
m=runpy.run_path("launch/agent-launch.py");base=m["load_config"](pathlib.Path("launch/agent-launch.toml"));mut=copy.deepcopy(base);mut["presets"]["balanced"]["tier_overrides"]={"claude":{"frontier":{"effort":"high"}}}
for label,cfg in (("S3_mutation",mut),("S3_control",base)):
 try:source_other="accepted:"+m["tier_effort"](m["build_plan"](cfg,"claude","balanced"),"frontier")
 except Exception as e:source_other="refused:"+str(e)
 plan=m["build_plan"](cfg,"codex","balanced");f,o,r=m["preset_from_plan"](plan,cfg,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];reloaded=copy.deepcopy(cfg);reloaded["presets"]["saved"]=saved;saved_other="accepted:"+m["tier_effort"](m["build_plan"](reloaded,"claude","saved"),"frontier");print(label+" codex_read=accepted source_claude="+source_other+" save=accepted saved_claude="+saved_other)'
```

```text
S3_mutation codex_read=accepted source_claude=refused:balanced authors frontier_effort='max' for claude and tier_overrides.claude.frontier.effort='high'; FRONTIER's effort has one value — remove one of them save=accepted saved_claude=accepted:high
S3_control codex_read=accepted source_claude=accepted:max save=accepted saved_claude=accepted:max
```

Proposed fix: validate the two effort homes for every launchable host during read and write, before default-value elision.

Missed check: [`preset_save`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:11339); its conflict control exercises only the active host.

### 5. L2 — the nested `controls` grammar remains open

File/function: [launch/agent-launch.py:_row_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2070).

The row reader requires only a table. Unknown keys, a Boolean trial count, and closed-domain violations parse and can be adjudicated directly.

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");R=m["ReviewMethodReport"];Q=m["ReviewReport"];good={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};bad={"trials":True,"order":"sideways","swap_augmentation":0,"aggregation":"plurality","future_bar":"ignored"};h=lambda s:hashlib.sha256(s.encode()).hexdigest()
for label,C in (("L2_mutation",bad),("L2_control",good)):
 row=R("panel","OK","perspective_floor","","model-x","high","openai","native","",C,());report=m["review_plan_from_v1"](m["review_plan_v1"](Q(row,(),"perspective_floor")));receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":h("packet"),"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0};verified,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":h("packet"),"main_dispatch_id":"main","receipts":[receipt]},{"panel":C},{"panel":()});print(label+"=accepted controls="+repr(report.base.controls)+" achievement="+verified.achievement+" verdict="+vs[0].reason)'
```

```text
L2_mutation=accepted controls={'trials': True, 'order': 'sideways', 'swap_augmentation': 0, 'aggregation': 'plurality', 'future_bar': 'ignored'} achievement=complete verdict=verified
L2_control=accepted controls={'trials': 1, 'order': 'fixed', 'swap_augmentation': False, 'aggregation': 'union'} achievement=complete verdict=verified
```

Proposed fix: share one controls validator between descriptor parsing and `_row_from_v1`, enforcing exact keys, `type(trials) is int and trials >= 1`, Boolean swap, and the closed order/aggregation domains.

Missed check: [`launcher_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691).

### 6. S5 — failed preset publication leaves its temporary file

File/function: [launch/agent-launch.py:save_preset](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:6199).

The old file remains intact, but an injected `os.replace` failure leaves the completed temporary behind, contrary to the specification’s post-failure residue.

```sh
python3 -c $'import os as realos,runpy,types
m=runpy.run_path("launch/agent-launch.py");G=m["save_preset"].__globals__;keys=("user_presets_path","preset_from_plan","render_preset_block","launchable_hosts","os","fcntl");old={k:G[k] for k in keys}
class P:
 state={"/m/p":"[presets.old]\\nlabel=\\"old\\"\\n"}
 def __init__(s,x):s.x=x
 @property
 def parent(s):return s
 @property
 def name(s):return s.x.rsplit("/",1)[-1]
 def mkdir(s,**k):pass
 def with_name(s,n):return P("/m/"+n)
 def read_text(s,encoding=None):
  if s.x not in P.state:raise FileNotFoundError
  return P.state[s.x]
 def write_text(s,t,encoding=None):P.state[s.x]=t
 def __str__(s):return s.x
class H:
 def __enter__(s):return s
 def __exit__(s,*a):return False
fail={"on":True}
def replace(a,b):
 if fail["on"]:raise OSError("injected-publish")
 P.state[b.x]=P.state.pop(a.x)
o=types.SimpleNamespace(**{k:getattr(realos,k) for k in dir(realos) if not k.startswith("__")});o.open=lambda *a:7;o.fdopen=lambda *a:H();o.getpid=lambda:9;o.replace=replace
G.update(user_presets_path=lambda _:P("/m/p"),preset_from_plan=lambda *a:({}, {}, None),render_preset_block=lambda *a:"[presets.probe]\\nlabel=\\"probe\\"\\n",launchable_hosts=lambda c:set(),os=o,fcntl=types.SimpleNamespace(flock=lambda *a:None,LOCK_EX=1));before=P.state["/m/p"]
try:m["save_preset"]({}, {"presets":{}}, P("cfg"), "probe")
except Exception as e:print("S5_mutation="+type(e).__name__+":"+str(e))
print("S5_mutation_old_intact="+str(P.state["/m/p"]==before)+" temporary_present="+str("/m/.p.9.tmp" in P.state));fail["on"]=False;m["save_preset"]({}, {"presets":{}}, P("cfg"), "probe");print("S5_control_new_complete="+str("probe" in P.state["/m/p"])+" temporary_present="+str("/m/.p.9.tmp" in P.state));G.update(old)'
```

```text
S5_mutation=LaunchError:cannot save preset to /m/p: injected-publish
S5_mutation_old_intact=True temporary_present=True
S5_control_new_complete=True temporary_present=False
```

Proposed fix: wrap temporary write and replace in a cleanup-on-failure block, preferably sharing the atomic-write primitive used by receipt emission.

Missed check: [`preset_save_round_trips`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:11083).

## Spec defects

1. L3 says a `DROPPED` row has “no grade” and any grade is refused, but the closure intentionally retains `NOT_REVIEW` as a non-ladder exclusion marker, and [`launcher_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:4422) positively requires it.

   Probe:

   ```text
   L3_spec_mutation=accepted dropped_grade='NOT_REVIEW'
   L3_spec_control=accepted dropped_grade=None
   ```

   Amend L3 to allow `grade ∈ {None, NOT_REVIEW}` while still refusing every `GRADE_ORDER` value. Changing the code would reverse the recorded closure rather than enforce it.

2. S5 contains incompatible inactive-host requirements. It first says a saved preset on “any launchable host projects what the source projected there,” then says only the active projection is compared and inactive hosts need merely keep building. [The conflicting sentence is here.](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T1720--4e59154--review-evidence-invariants.md:232)

   Narrow it to: active-host projection identity; inactive-host buildability plus S1/S2 carry-through.

## Void readings

Dropped as required:

- D2 hidden, nonrepresentative ID reuse:

  ```text
  D2_hidden_mutation rc=0 bundle_sha256=f915e71811e6defd6e59e6099cb4362c95b0bf5122801afea16caf66aa514807 representatives=['a', 'b']
  D2_hidden_control rc=0 bundle_sha256=f915e71811e6defd6e59e6099cb4362c95b0bf5122801afea16caf66aa514807 representatives=['a', 'b']
  ```

- D3/Q4, invalid `passes` on a one-trial receipt:

  ```text
  D3_one_trial_passes_mutation=('complete', True, 'verified')
  D3_one_trial_passes_control=('complete', True, 'verified')
  ```

- D6, extra control markers on a fixed/no-swap method:

  ```text
  D6_extra_markers_mutation=('complete', True, 'verified')
  D6_extra_markers_control=('complete', True, 'verified')
  ```

## Denominator

- Pinned subject: `review-round-20` at `e42c905`; worktree remained clean.
- Probed: all 33 invariants — L1–L8, D1–D8, F1–F4, V1–V7, S1–S6.
- Read only: none.
- Code-violated IDs: L2, L6, D2, D6, F1, V2, V3, V4, S3, S5.
- Spec-defective clauses: L3 and S5.
- Held on their probed edge: L1, L4, L5, L7, L8, D1, D3, D4, D5, D7, D8, F2, F3, F4, V1, V5, V6, V7, S1, S2, S4, S6.
- All 13 round‑1 closure mutation/control pairs held: D4, D1, V5, L5 disclosure, D7, D8, S5 behavioral comparison, L2 outer plan/row keys, L3 live seat/I1 grade, L6 optional `panel`/duplicate IDs, F2, and both F4 paths.
- Required `--config launch/agent-launch.toml` dry-runs passed for Codex and Claude; neither host CLI was invoked.

## Not examined

- Adapter honesty, semantic aggregation adherence, and review quality.
- Q1–Q9 as design decisions.
- Host CLIs, sandboxing, permission modes, credentials, or access control.
- Runtime surfaces outside the named subsystem.
- The full parity suite, because its fixtures write temporary files; its relevant check bodies were read to identify missed controls.
- Real concurrent-process interleavings; D8/S5 were exercised through bounded in-memory failure traces.
