---
created_at: 2026-08-17T15:17:00+09:00
head: 9d1d668
kind: review
---

# Spec round 1 — the code held against the invariants specification (raw findings)

The FIRST round under the new instrument (D-20260817-2284a1): the reviewer holds
`launch/agent-launch.py` against `design/launch-contract/2026-08-17T1416--2f35f5c--review-evidence-invariants.md`
instead of against the code's own sentences. Reviewer: `codex exec -s read-only -m gpt-5.6-sol
-c model_reasoning_effort=ultra`, packet on stdin (this session's `specround-packet.md`);
497,874 tokens. All 33 invariants probed, none read-only. Thirteen findings across twelve
invariant ids (seven of the eight pre-registered violations confirmed as evidence, one —
visible dispatch-id reuse across methods — REFUTED: the code already refuses it), two
specification defects, two void readings. Verbatim below.

Reviewed `review-round-20` at `9d1d66874040`; the specification’s `head:` is `2f35f5c`, and the intervening commit changes only the specification and decision ledger—not `launch/agent-launch.py`. The worktree remained clean.

Result: 13 findings across 12 invariant IDs, 2 specification defects, and 2 void readings. All 33 invariants were probed; none were read-only-only.

## Findings

### 1. D4 — verification is not bound to independent packet bytes

File/functions: [agent-launch.py:parse_args](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:7963), [verify_receipts_command](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:8025).

Mutation—the valid verification interface has no packet argument:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); a=m["parse_args"](["--config","launch/agent-launch.toml","--verify-receipts","plan.json","bundle.json"]); print("verify_receipts="+repr(a.verify_receipts)); print("packet_argument="+repr(getattr(a,"packet",None))); print("exit_status=0")'
```

```text
verify_receipts=['plan.json', 'bundle.json']
packet_argument=None
exit_status=0
```

Control—trying to supply the independently required packet is structurally rejected:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); m["parse_args"](["--config","launch/agent-launch.toml","--verify-receipts","plan.json","bundle.json","packet.bin"])'
```

```text
usage: -c [-h] [--config CONFIG] [--no-tui] [--preset PRESET] [--custom]
          [--yes] [--dry-run] [--verify-receipts PLAN RECEIPTS]
          [--emit-receipt METHOD_ID SEAT EXIT_STATUS PACKET_FILE RESULT_FILE]
          [--evidence KEY=VALUE]
          [--fold-receipts DIR PACKET_FILE MAIN_DISPATCH_ID]
          [--check-adapter ...]
          [{codex,claude}] ...
-c: error: argument host: invalid choice: 'packet.bin' (choose from 'codex', 'claude')
```

Exit 2.

Fix: add the packet artifact to `--verify-receipts`; hash its exact bytes and require both bundle-anchor equality and equality between its embedded canonical plan and the adjudicated plan.

Missed check: `launcher_receipts`.

V1 itself held: missing/noncanonical bundle anchors and a non-array `receipts` value are already refused. Pre-registration #5 is therefore narrowed to D4.

---

### 2. D1 — one raw singleton receipt can manufacture a multi-pass claim

Files/functions: [agent-launch.py:_receipt_structure_reason](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2111), [_merge_method_passes](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2568).

Mutation:

```sh
python3 -c 'import hashlib,json,runpy; m=runpy.run_path("launch/agent-launch.py"); digest=lambda b:hashlib.sha256(b).hexdigest(); controls={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel","OK","perspective_floor","","gpt-test","high","openai","panel","",controls,()); report=m["ReviewReport"](row,(),"perspective_floor"); receipt={"schema":"ReviewReceipt/v1","method_id":"panel","dispatch_id":"child-1","packet_sha256":digest(b"packet"),"result_sha256":digest(b"result-1"),"provider":"openai","model":"gpt-test","effort":"high","exit_status":0,"passes":[digest(b"result-1"),digest(b"result-2")]}; folded=m["_merge_method_passes"]("panel",[receipt],"main-1"); verified,verdicts=m["verify_review_receipts"](report,{"schema":"ReviewReceipts/v1","packet_sha256":digest(b"packet"),"main_dispatch_id":"main-1","receipts":[folded]},{"panel":controls},{"panel":()}); print(json.dumps({"raw_structure_reason":m["_receipt_structure_reason"](receipt),"folded_pass_count":len(folded["passes"]),"achievement":verified.achievement,"accepted":verdicts[0].accepted,"verdict_reason":verdicts[0].reason},sort_keys=True))'
```

```json
{"accepted": true, "achievement": "complete", "folded_pass_count": 2, "raw_structure_reason": "", "verdict_reason": "verified"}
```

Control—remove only the raw `passes`:

```sh
python3 -c 'import hashlib,json,runpy; m=runpy.run_path("launch/agent-launch.py"); digest=lambda b:hashlib.sha256(b).hexdigest(); controls={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel","OK","perspective_floor","","gpt-test","high","openai","panel","",controls,()); report=m["ReviewReport"](row,(),"perspective_floor"); receipt={"schema":"ReviewReceipt/v1","method_id":"panel","dispatch_id":"child-1","packet_sha256":digest(b"packet"),"result_sha256":digest(b"result-1"),"provider":"openai","model":"gpt-test","effort":"high","exit_status":0}; folded=m["_merge_method_passes"]("panel",[receipt],"main-1"); verified,verdicts=m["verify_review_receipts"](report,{"schema":"ReviewReceipts/v1","packet_sha256":digest(b"packet"),"main_dispatch_id":"main-1","receipts":[folded]},{"panel":controls},{"panel":()}); print(json.dumps({"raw_structure_reason":m["_receipt_structure_reason"](receipt),"passes_present_after_fold":"passes" in folded,"achievement":verified.achievement,"accepted":verdicts[0].accepted,"verdict_reason":verdicts[0].reason},sort_keys=True))'
```

```json
{"accepted": false, "achievement": "none", "passes_present_after_fold": false, "raw_structure_reason": "", "verdict_reason": "carries no pass list, so it evidences fewer than the 2 requested passes"}
```

Fix: add a phase-specific raw-receipt validator and refuse `passes` before folding, including before the singleton return.

Missed check: `launcher_receipt_fold`.

---

### 3. V5 — duplicate selected receipts are adjudicated first-wins

File/function: [agent-launch.py:verify_review_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2265).

Mutation:

```sh
python3 -c 'import hashlib,runpy; m=runpy.run_path("launch/agent-launch.py"); C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; R=m["ReviewMethodReport"]; Q=m["ReviewReport"]; row=R("panel",m["STATUS_OK"],"perspective_floor","","model-x","high","openai","exec-stdio-v1","",C); p=hashlib.sha256(b"packet").hexdigest(); mk=lambda mid,d,r:{"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":d,"packet_sha256":p,"result_sha256":hashlib.sha256(r.encode()).hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; report,verdicts=m["verify_review_receipts"](Q(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[mk("panel","child-1","one"),mk("panel","child-2","two")]},{"panel":C}); print(m["render_receipt_verdicts"](report,verdicts)); print("verdict_count="+str(len(verdicts))); print("exit_status="+str(0 if report.achievement==m["ACHIEVEMENT_COMPLETE"] else 1))'
```

```text
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  panel: ACHIEVED/perspective_floor — verified
verdict_count=1
exit_status=0
```

Control—the second receipt is foreign rather than a duplicate selected method:

```sh
python3 -c 'import hashlib,runpy; m=runpy.run_path("launch/agent-launch.py"); C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; R=m["ReviewMethodReport"]; Q=m["ReviewReport"]; row=R("panel",m["STATUS_OK"],"perspective_floor","","model-x","high","openai","exec-stdio-v1","",C); p=hashlib.sha256(b"packet").hexdigest(); mk=lambda mid,d,r:{"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":d,"packet_sha256":p,"result_sha256":hashlib.sha256(r.encode()).hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; report,verdicts=m["verify_review_receipts"](Q(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[mk("panel","child-1","one"),mk("ghost","child-2","two")]},{"panel":C}); print(m["render_receipt_verdicts"](report,verdicts)); print("verdict_count="+str(len(verdicts))); print("exit_status="+str(0 if report.achievement==m["ACHIEVEMENT_COMPLETE"] else 1))'
```

```text
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  panel: ACHIEVED/perspective_floor — verified
  ghost: PROPOSED — names no selected method in the plan
verdict_count=2
exit_status=0
```

Fix: count receipt occurrences for every selected `method_id` before adjudication and raise a named refusal when any count exceeds one.

Missed check: `launcher_receipts`.

---

### 4. L5 — an enum-valid, underivable independence grade parses

Files/functions: [agent-launch.py:review_plan_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1842), [review_plan_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1856).

Mutation:

```sh
python3 -c 'import copy,json,runpy; m=runpy.run_path("launch/agent-launch.py"); main=m["ReviewBinding"]("openai","codex","gpt-test","high"); reviewer=m["ReviewBinding"]("openai","codex","gpt-test","high"); actual=m["independence_grade"](reviewer,main); controls={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel","OK",actual,"","gpt-test","high","openai","panel","",controls,()); report=m["ReviewReport"](row,(),actual); plan=m["review_plan_v1"](report); forged=copy.deepcopy(plan); forged["base"]["grade"]="provider_difference"; forged["best_grade"]="provider_difference"; parsed=m["review_plan_from_v1"](forged); print(json.dumps({"accepted":True,"actual_launch_grade":actual,"parsed_grade":parsed.base.grade,"grade_matches_actual_launch":parsed.base.grade==actual,"main_seat_serialized":any(key.startswith("main") for key in forged)},sort_keys=True))'
```

```json
{"accepted": true, "actual_launch_grade": "perspective_floor", "grade_matches_actual_launch": false, "main_seat_serialized": false, "parsed_grade": "provider_difference"}
```

Control:

```sh
python3 -c 'import json,runpy; m=runpy.run_path("launch/agent-launch.py"); main=m["ReviewBinding"]("openai","codex","gpt-test","high"); reviewer=m["ReviewBinding"]("openai","codex","gpt-test","high"); actual=m["independence_grade"](reviewer,main); controls={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel","OK",actual,"","gpt-test","high","openai","panel","",controls,()); report=m["ReviewReport"](row,(),actual); plan=m["review_plan_v1"](report); parsed=m["review_plan_from_v1"](plan); print(json.dumps({"accepted":True,"actual_launch_grade":actual,"parsed_grade":parsed.base.grade,"grade_matches_actual_launch":parsed.base.grade==actual,"main_seat_serialized":any(key.startswith("main") for key in plan)},sort_keys=True))'
```

```json
{"accepted": true, "actual_launch_grade": "perspective_floor", "grade_matches_actual_launch": true, "main_seat_serialized": false, "parsed_grade": "perspective_floor"}
```

Fix: evolve the plan schema to pin the main seat and every input used by `independence_grade`, including below-floor tier information; recompute row grades during parsing.

Missed check: `launcher_review_contract`.

---

### 5. D7 — a multi-pass primary result need not appear in `passes`

File/function: [agent-launch.py:_receipt_reason](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2140).

Mutation:

```sh
python3 -c '
import hashlib, runpy
m=runpy.run_path("launch/agent-launch.py"); C={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel",m["STATUS_OK"],"perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=C,evidence=()); report=m["ReviewReport"](row,(),"perspective_floor"); p=hashlib.sha256(b"packet").hexdigest(); primary=hashlib.sha256(b"primary").hexdigest(); h1=hashlib.sha256(b"pass-one").hexdigest(); h2=hashlib.sha256(b"pass-two").hexdigest(); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child-1","packet_sha256":p,"result_sha256":primary,"provider":"openai","model":"model-x","effort":"high","exit_status":0,"passes":[h1,h2]}; out,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[receipt]},{"panel":C}); print("primary_in_passes="+str(primary in receipt["passes"])); print("achievement=%s accepted=%s reason=%s"%(out.achievement,vs[0].accepted,vs[0].reason))
'
```

```text
primary_in_passes=False
achievement=complete accepted=True reason=verified
```

Control:

```sh
python3 -c '
import hashlib, runpy
m=runpy.run_path("launch/agent-launch.py"); C={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel",m["STATUS_OK"],"perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=C,evidence=()); report=m["ReviewReport"](row,(),"perspective_floor"); p=hashlib.sha256(b"packet").hexdigest(); primary=hashlib.sha256(b"primary").hexdigest(); h1=hashlib.sha256(b"pass-one").hexdigest(); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child-1","packet_sha256":p,"result_sha256":primary,"provider":"openai","model":"model-x","effort":"high","exit_status":0,"passes":[primary,h1]}; out,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[receipt]},{"panel":C}); print("primary_in_passes="+str(primary in receipt["passes"])); print("achievement=%s accepted=%s reason=%s"%(out.achievement,vs[0].accepted,vs[0].reason))
'
```

```text
primary_in_passes=True
achievement=complete accepted=True reason=verified
```

Fix: after pass shape, digest, and cardinality checks, require `result_sha256 in passes`.

Missed check: `launcher_receipts`.

---

### 6. D8 — receipt emission can leave a partial final artifact

File/function: [agent-launch.py:emit_receipt_command](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2514).

Mutation, entirely in memory:

```sh
python3 -c 'import os,runpy,types; m=runpy.run_path("launch/agent-launch.py"); trace=[]; state={};
class P:
 def __init__(self,s): self.s=str(s)
 def __str__(self): return self.s
 def expanduser(self): return self
 def mkdir(self,parents=False,exist_ok=False): trace.append(("mkdir",self.s))
 def __truediv__(self,name): return P(self.s+"/"+str(name))
 def write_text(self,data,encoding=None): state[self.s]=data[:1]; trace.append(("write_text",self.s,len(data),"raised_after_partial")); raise OSError("injected after partial write")
g=m["emit_receipt_command"].__globals__; g["pathlib"]=types.SimpleNamespace(Path=P); g["_sha256_file"]=lambda path:"a"*64; g["uuid"]=types.SimpleNamespace(uuid4=lambda:types.SimpleNamespace(hex="child-id")); g["parse_seat"]=lambda seat:("openai","model-x","high"); os.environ[m["RECEIPT_DIR_ENV"]]="/receipts";
try: m["emit_receipt_command"]("panel","openai:model-x/high","0","packet","result")
except m["LaunchError"] as exc: print("error="+str(exc)); print("trace="+repr(trace)); print("final_state="+repr(state.get("/receipts/child-id.json"))); print("exit_status=1")'
```

```text
error=cannot write receipt into /receipts: injected after partial write
trace=[('mkdir', '/receipts'), ('write_text', '/receipts/child-id.json', 328, 'raised_after_partial')]
final_state='{'
exit_status=1
```

Control—failure before bytes are published:

```sh
python3 -c 'import os,runpy,types; m=runpy.run_path("launch/agent-launch.py"); trace=[]; state={};
class P:
 def __init__(self,s): self.s=str(s)
 def __str__(self): return self.s
 def expanduser(self): return self
 def mkdir(self,parents=False,exist_ok=False): trace.append(("mkdir",self.s))
 def __truediv__(self,name): return P(self.s+"/"+str(name))
 def write_text(self,data,encoding=None): trace.append(("write_text",self.s,len(data),"raised_before_write")); raise OSError("injected before write")
g=m["emit_receipt_command"].__globals__; g["pathlib"]=types.SimpleNamespace(Path=P); g["_sha256_file"]=lambda path:"a"*64; g["uuid"]=types.SimpleNamespace(uuid4=lambda:types.SimpleNamespace(hex="child-id")); g["parse_seat"]=lambda seat:("openai","model-x","high"); os.environ[m["RECEIPT_DIR_ENV"]]="/receipts";
try: m["emit_receipt_command"]("panel","openai:model-x/high","0","packet","result")
except m["LaunchError"] as exc: print("error="+str(exc)); print("trace="+repr(trace)); print("final_state="+repr(state.get("/receipts/child-id.json"))); print("exit_status=1")'
```

```text
error=cannot write receipt into /receipts: injected before write
trace=[('mkdir', '/receipts'), ('write_text', '/receipts/child-id.json', 328, 'raised_before_write')]
final_state=None
exit_status=1
```

Fix: write a unique same-directory temporary file, close it, atomically replace the final UUID path, and remove the temporary on every failure.

Missed check: `launcher_receipt_adapters`.

---

### 7. S5 — save reparses syntax but does not compare behavior before replacement

File/function: [agent-launch.py:save_preset](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:5826).

Mutation—inject a syntactically valid projection change; all persistence is mocked:

```sh
python3 -c '
import copy, pathlib, runpy, tomllib
m = runpy.run_path("launch/agent-launch.py")
g = m["save_preset"].__globals__
config = tomllib.loads(pathlib.Path("launch/agent-launch.toml").read_text())
plan = m["build_plan"](config, "codex", "solo")
before = m["project_args"](plan, materialize_agents=False)
mem = {}
class FakePath:
    def __init__(self, name="profiles.toml"): self.name = name
    @property
    def parent(self): return self
    def mkdir(self, **kwargs): return None
    def with_name(self, name): return FakePath(name)
    def read_text(self, **kwargs): raise FileNotFoundError
    def write_text(self, text, **kwargs): mem["candidate"] = text
    def __str__(self): return self.name
class FakeHandle:
    def __enter__(self): return self
    def __exit__(self, *args): return False
g["user_presets_path"] = lambda _: FakePath()
g["os"].open = lambda *args, **kwargs: 7
g["os"].fdopen = lambda *args, **kwargs: FakeHandle()
g["fcntl"].flock = lambda *args, **kwargs: None
g["os"].replace = lambda *args, **kwargs: mem.__setitem__("replaced", True)
render = g["render_preset_block"]
g["render_preset_block"] = lambda *args, **kwargs: render(*args, **kwargs).replace("main_tier = \"helm\"", "main_tier = \"workhorse\"", 1)
m["save_preset"](plan, config, pathlib.Path("unused.toml"), "probe")
parsed = tomllib.loads(mem["candidate"])
reloaded = copy.deepcopy(config)
reloaded["presets"]["probe"] = parsed["presets"]["probe"]
after = m["project_args"](m["build_plan"](reloaded, "codex", "probe"), materialize_agents=False)
print("save=OK parsed=True replaced=%s projection_equal=%s before_model=%s after_model=%s" % (mem.get("replaced"), before == after, before[before.index("--model") + 1], after[after.index("--model") + 1]))
'
```

```text
save=OK parsed=True replaced=True projection_equal=False before_model=gpt-5.6-sol after_model=gpt-5.6-terra
```

Faithful-render control:

```sh
python3 -c '
import copy, pathlib, runpy, tomllib
m = runpy.run_path("launch/agent-launch.py")
g = m["save_preset"].__globals__
config = tomllib.loads(pathlib.Path("launch/agent-launch.toml").read_text())
plan = m["build_plan"](config, "codex", "solo")
before = m["project_args"](plan, materialize_agents=False)
mem = {}
class FakePath:
    def __init__(self, name="profiles.toml"): self.name = name
    @property
    def parent(self): return self
    def mkdir(self, **kwargs): return None
    def with_name(self, name): return FakePath(name)
    def read_text(self, **kwargs): raise FileNotFoundError
    def write_text(self, text, **kwargs): mem["candidate"] = text
    def __str__(self): return self.name
class FakeHandle:
    def __enter__(self): return self
    def __exit__(self, *args): return False
g["user_presets_path"] = lambda _: FakePath()
g["os"].open = lambda *args, **kwargs: 7
g["os"].fdopen = lambda *args, **kwargs: FakeHandle()
g["fcntl"].flock = lambda *args, **kwargs: None
g["os"].replace = lambda *args, **kwargs: mem.__setitem__("replaced", True)
m["save_preset"](plan, config, pathlib.Path("unused.toml"), "probe")
parsed = tomllib.loads(mem["candidate"])
reloaded = copy.deepcopy(config)
reloaded["presets"]["probe"] = parsed["presets"]["probe"]
after = m["project_args"](m["build_plan"](reloaded, "codex", "probe"), materialize_agents=False)
print("save=OK parsed=True replaced=%s projection_equal=%s before_model=%s after_model=%s" % (mem.get("replaced"), before == after, before[before.index("--model") + 1], after[after.index("--model") + 1]))
'
```

```text
save=OK parsed=True replaced=True projection_equal=True before_model=gpt-5.6-sol after_model=gpt-5.6-sol
```

Fix: before writing/replacing, merge and rebuild the parsed candidate for every launchable host and compare `project_args(..., materialize_agents=False)` against the source projections. Refuse by host on mismatch.

Missed check: `preset_save_round_trips`. Its current end-state samples compare today’s renderer output, but do not inject a parseable behavioral mutation and prove that `save_preset` itself refuses before `os.replace`.

---

### 8. L2 — plan and row grammars accept and erase unknown fields

Files/functions: [agent-launch.py:review_plan_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1856), [_row_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1929).

Mutation:

```sh
python3 -c 'import copy,json,runpy; m=runpy.run_path("launch/agent-launch.py"); row={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"gpt-test","effort":"high","provider":"openai","mechanism":"panel","instruction":"","controls":{"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"},"evidence":[]}; plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":row,"methods":[]}; plan["future_plan_bar"]="plan-value"; plan["base"]["future_row_bar"]="row-value"; parsed=m["review_plan_from_v1"](plan); emitted=m["review_plan_v1"](parsed); print(json.dumps({"accepted":True,"future_plan_bar_preserved":"future_plan_bar" in emitted,"future_row_bar_preserved":"future_row_bar" in emitted["base"]},sort_keys=True))'
```

```json
{"accepted": true, "future_plan_bar_preserved": false, "future_row_bar_preserved": false}
```

Control:

```sh
python3 -c 'import json,runpy; m=runpy.run_path("launch/agent-launch.py"); row={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"gpt-test","effort":"high","provider":"openai","mechanism":"panel","instruction":"","controls":{"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"},"evidence":[]}; plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":row,"methods":[]}; parsed=m["review_plan_from_v1"](plan); emitted=m["review_plan_v1"](parsed); print(json.dumps({"accepted":True,"exact_round_trip":emitted==plan},sort_keys=True))'
```

```json
{"accepted": true, "exact_round_trip": true}
```

Fix: define exact plan and row key sets beside the schema authority and reject unknown keys by name.

Missed check: `launcher_review_contract`.

---

### 9. L3 — a DROPPED row may retain a live seat and grade

Files/functions: [agent-launch.py:_resolve_one](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1599), [_row_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1929).

Mutation:

```sh
python3 -c 'import json,runpy; m=runpy.run_path("launch/agent-launch.py"); controls={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; base={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"gpt-test","effort":"high","provider":"openai","mechanism":"panel","instruction":"","controls":controls,"evidence":[]}; dropped={"method_id":"optional","status":"DROPPED","grade":"provider_difference","detail":"did not run","model":"other-model","effort":"max","provider":"anthropic","mechanism":"exec-stdio-v1","instruction":"","controls":None,"evidence":[]}; plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":base,"methods":[dropped]}; parsed=m["review_plan_from_v1"](plan); row=parsed.methods[0]; print(json.dumps({"accepted":True,"grade":row.grade,"seat":[row.provider,row.model,row.effort],"mechanism":row.mechanism},sort_keys=True))'
```

```json
{"accepted": true, "grade": "provider_difference", "mechanism": "exec-stdio-v1", "seat": ["anthropic", "other-model", "max"]}
```

Control:

```sh
python3 -c 'import json,runpy; m=runpy.run_path("launch/agent-launch.py"); controls={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; base={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"gpt-test","effort":"high","provider":"openai","mechanism":"panel","instruction":"","controls":controls,"evidence":[]}; dropped={"method_id":"optional","status":"DROPPED","grade":None,"detail":"did not run","model":None,"effort":None,"provider":None,"mechanism":None,"instruction":"","controls":None,"evidence":[]}; plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":base,"methods":[dropped]}; parsed=m["review_plan_from_v1"](plan); row=parsed.methods[0]; print(json.dumps({"accepted":True,"grade":row.grade,"seat":[row.provider,row.model,row.effort],"mechanism":row.mechanism},sort_keys=True))'
```

```json
{"accepted": true, "grade": null, "mechanism": null, "seat": [null, null, null]}
```

Fix: normalize every `_resolve_one` DROPPED return to null grade/seat/mechanism, and enforce those nulls in `_row_from_v1`.

Missed check: `launcher_review_contract`.

---

### 10. L6 — the serialized plan parser accepts a second selected `panel`

File/function: [agent-launch.py:review_plan_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1856).

Mutation:

```sh
python3 -c 'import copy,json,runpy; m=runpy.run_path("launch/agent-launch.py"); base={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"gpt-test","effort":"high","provider":"openai","mechanism":"panel","instruction":"","controls":{"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"},"evidence":[]}; duplicate=copy.deepcopy(base); plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":base,"methods":[duplicate]}; parsed=m["review_plan_from_v1"](plan); print(json.dumps({"accepted":True,"selected_ids":[parsed.base.method_id]+[row.method_id for row in parsed.methods],"unique_ids":len({parsed.base.method_id,*[row.method_id for row in parsed.methods]})},sort_keys=True))'
```

```json
{"accepted": true, "selected_ids": ["panel", "panel"], "unique_ids": 1}
```

Control:

```sh
python3 -c 'import copy,json,runpy; m=runpy.run_path("launch/agent-launch.py"); base={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"gpt-test","effort":"high","provider":"openai","mechanism":"panel","instruction":"","controls":{"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"},"evidence":[]}; optional=copy.deepcopy(base); optional["method_id"]="optional"; plan={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":base,"methods":[optional]}; parsed=m["review_plan_from_v1"](plan); print(json.dumps({"accepted":True,"selected_ids":[parsed.base.method_id]+[row.method_id for row in parsed.methods],"unique_ids":len({parsed.base.method_id,*[row.method_id for row in parsed.methods]})},sort_keys=True))'
```

```json
{"accepted": true, "selected_ids": ["panel", "optional"], "unique_ids": 2}
```

Fix: reject `PANEL_METHOD` in `methods` and repeated selected IDs in `review_plan_from_v1`; keep adjudication’s duplicate guard as defense in depth.

Missed check: `launcher_review_schema` covers authored `methods.panel`, but not a bare serialized plan.

---

### 11. F2 — folded content depends on receipt order

File/function: [agent-launch.py:_merge_method_passes](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2568).

Mutation:

```sh
python3 -c '
import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py"); p=hashlib.sha256(b"packet").hexdigest()
def r(d,label): return {"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":d,"packet_sha256":p,"result_sha256":hashlib.sha256(label.encode()).hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0,"evidence":{"trace":"same"}}
g=[r("child-a","one"),r("child-b","two")]; a=m["_merge_method_passes"]("panel",g,"main"); b=m["_merge_method_passes"]("panel",list(reversed(g)),"main"); print("content_equal=%s forward_primary=%s/%s reverse_primary=%s/%s"%(a==b,a["dispatch_id"],a["result_sha256"][:8],b["dispatch_id"],b["result_sha256"][:8]))
'
```

```text
content_equal=False forward_primary=child-a/7692c3ad reverse_primary=child-b/3fc4ccfe
```

Singleton control:

```sh
python3 -c '
import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py"); p=hashlib.sha256(b"packet").hexdigest(); r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child-a","packet_sha256":p,"result_sha256":hashlib.sha256(b"one").hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0,"evidence":{"trace":"same"}}; a=m["_merge_method_passes"]("panel",[r],"main"); b=m["_merge_method_passes"]("panel",list(reversed([r])),"main"); print("content_equal=%s primary=%s/%s"%(a==b,a["dispatch_id"],a["result_sha256"][:8]))
'
```

```text
content_equal=True primary=child-a/7692c3ad
```

Fix: canonically order validated receipts before selecting the representative, primary result, evidence values, and propagated failed status.

Missed check: `launcher_receipt_fold`.

---

### 12. F4 — the bundle grammar accepts unknown top-level keys

File/function: [agent-launch.py:verify_review_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2265).

Mutation:

```sh
python3 -c 'import runpy,hashlib; m=runpy.run_path("launch/agent-launch.py"); c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel","OK","perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=c,evidence=()); report=m["ReviewReport"](row,(),"perspective_floor"); packet=hashlib.sha256(b"packet").hexdigest(); receipt={"schema":"ReviewReceipt/v1","method_id":"panel","dispatch_id":"child-1","packet_sha256":packet,"result_sha256":hashlib.sha256(b"result").hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; bundle={"schema":"ReviewReceipts/v1","packet_sha256":packet,"main_dispatch_id":"main-1","receipts":[receipt],"future_bundle_field":"smuggled"}; out,verdicts=m["verify_review_receipts"](report,bundle,{"panel":c}); known={"schema","packet_sha256","main_dispatch_id","receipts"}; print("accepted_unknown=%r achievement=%s verdict=%s"%(sorted(set(bundle)-known),out.achievement,verdicts[0].reason))'
```

```text
accepted_unknown=['future_bundle_field'] achievement=complete verdict=verified
```

Control:

```sh
python3 -c 'import runpy,hashlib; m=runpy.run_path("launch/agent-launch.py"); c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel","OK","perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=c,evidence=()); report=m["ReviewReport"](row,(),"perspective_floor"); packet=hashlib.sha256(b"packet").hexdigest(); receipt={"schema":"ReviewReceipt/v1","method_id":"panel","dispatch_id":"child-1","packet_sha256":packet,"result_sha256":hashlib.sha256(b"result").hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; bundle={"schema":"ReviewReceipts/v1","packet_sha256":packet,"main_dispatch_id":"main-1","receipts":[receipt]}; out,verdicts=m["verify_review_receipts"](report,bundle,{"panel":c}); known={"schema","packet_sha256","main_dispatch_id","receipts"}; print("accepted_unknown=%r achievement=%s verdict=%s"%(sorted(set(bundle)-known),out.achievement,verdicts[0].reason))'
```

```text
accepted_unknown=[] achievement=complete verdict=verified
```

Fix: define `RECEIPT_BUNDLE_KEYS` beside `RECEIPT_KEYS` and reject the difference by name before reading anchors.

Missed check: `launcher_receipts`.

---

### 13. F4 — the public fold accepts an empty `method_id`

File/function: [agent-launch.py:fold_receipts_command](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2701).

Mutation:

```sh
python3 -c '
import hashlib, json, runpy, types
m=runpy.run_path("launch/agent-launch.py"); g=m["fold_receipts_command"].__globals__; p=hashlib.sha256(b"packet").hexdigest()
receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"","dispatch_id":"child-1","packet_sha256":p,"result_sha256":hashlib.sha256(b"result").hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}
class ReceiptPath:
 def __str__(self): return "memory/one.json"
 def read_text(self,**kwargs): return json.dumps(receipt)
class Directory:
 def expanduser(self): return self
 def glob(self,pattern): return [ReceiptPath()]
 def __str__(self): return "memory"
g["pathlib"]=types.SimpleNamespace(Path=lambda _:Directory()); g["_sha256_file"]=lambda _:p
rc=m["fold_receipts_command"]("memory","packet","main")
print("exit_status="+str(rc))
'
```

```text
{"main_dispatch_id": "main", "packet_sha256": "7426afc489d0eef99a0b438def226ad139f752350c25cf2c04900281afbb79e0", "receipts": [{"dispatch_id": "child-1", "effort": "high", "exit_status": 0, "method_id": "", "model": "model-x", "packet_sha256": "7426afc489d0eef99a0b438def226ad139f752350c25cf2c04900281afbb79e0", "provider": "openai", "result_sha256": "f6a214f7a5fcda0c2cee9660b7fc29f5649e3c68aad48e20e950137c98913a68", "schema": "ReviewReceipt/v1"}], "schema": "ReviewReceipts/v1"}
exit_status=0
```

Control changes only the method ID:

```sh
python3 -c '
import hashlib, json, runpy, types
m=runpy.run_path("launch/agent-launch.py"); g=m["fold_receipts_command"].__globals__; p=hashlib.sha256(b"packet").hexdigest()
receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child-1","packet_sha256":p,"result_sha256":hashlib.sha256(b"result").hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}
class ReceiptPath:
 def __str__(self): return "memory/one.json"
 def read_text(self,**kwargs): return json.dumps(receipt)
class Directory:
 def expanduser(self): return self
 def glob(self,pattern): return [ReceiptPath()]
 def __str__(self): return "memory"
g["pathlib"]=types.SimpleNamespace(Path=lambda _:Directory()); g["_sha256_file"]=lambda _:p
rc=m["fold_receipts_command"]("memory","packet","main")
print("exit_status="+str(rc))
'
```

```text
{"main_dispatch_id": "main", "packet_sha256": "7426afc489d0eef99a0b438def226ad139f752350c25cf2c04900281afbb79e0", "receipts": [{"dispatch_id": "child-1", "effort": "high", "exit_status": 0, "method_id": "panel", "model": "model-x", "packet_sha256": "7426afc489d0eef99a0b438def226ad139f752350c25cf2c04900281afbb79e0", "provider": "openai", "result_sha256": "f6a214f7a5fcda0c2cee9660b7fc29f5649e3c68aad48e20e950137c98913a68", "schema": "ReviewReceipt/v1"}], "schema": "ReviewReceipts/v1"}
exit_status=0
```

Fix: require `isinstance(method_id, str) and bool(method_id)` before grouping.

Missed check: `launcher_receipt_adapters` at the public fold boundary; `launcher_receipt_fold` at the merge seam.

## Spec defects

1. D2’s producer-authorship clause is not artifact-falsifiable.

   The failing sentence is: “`dispatch_id` … launcher-generated (uuid4 in `emit_receipt_command`, never adapter-chosen).” An otherwise identical receipt cannot reveal whether the string came from the launcher or an adapter. This also conflicts with the trust-boundary statement that receipts are not authenticated provenance.

   Separate the producer obligation from the artifact-verifiable invariant, or add runtime-authenticated lineage. Likewise, either preserve every per-pass dispatch ID in the folded artifact or explicitly scope cross-method uniqueness to the fold’s raw-input phase.

2. “Each [invariant] is falsifiable: the violation decidable from the artifacts alone” is too strong.

   D8’s “a concurrent reader never observes partial bytes” and S5’s no-lost-concurrent-save clause are temporal properties. A final receipt or preset alone cannot prove what another reader observed or which interleaving occurred. Reword the evidence domain to “artifacts plus a bounded runtime trace/interleaving probe,” or narrow those clauses to post-failure artifact states.

## Void readings

### D2 — hidden cross-method pass-ID reuse

Mutation:

```sh
python3 -c 'import hashlib,json,runpy; m=runpy.run_path("launch/agent-launch.py"); p=hashlib.sha256(b"packet").hexdigest(); C={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; R=m["ReviewMethodReport"]; Q=m["ReviewReport"]; rows=[R(x,m["STATUS_OK"],"perspective_floor","","model-x","high","openai","exec-stdio-v1","",C) for x in ("panel","lens")]; mk=lambda mid,d,r:{"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":d,"packet_sha256":p,"result_sha256":hashlib.sha256(r.encode()).hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; groups=[[mk("panel","panel-first","a1"),mk("panel","hidden-shared","a2")],[mk("lens","lens-first","b1"),mk("lens","hidden-shared","b2")]]; folded=[m["_merge_method_passes"](mid,g,"main") for mid,g in zip(("panel","lens"),groups)]; report,verdicts=m["verify_review_receipts"](Q(rows[0],(rows[1],),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":folded},{"panel":C,"lens":C}); behavior=json.dumps({"folded":folded,"rendered":m["render_receipt_verdicts"](report,verdicts)},sort_keys=True); print("raw_ids="+repr([[r["dispatch_id"] for r in g] for g in groups])); print("behavior_sha256="+hashlib.sha256(behavior.encode()).hexdigest()); print("achievement="+report.achievement); print("exit_status=0")'
```

```text
raw_ids=[['panel-first', 'hidden-shared'], ['lens-first', 'hidden-shared']]
behavior_sha256=d3989899bc956b50a07a0ddc89def8f1712f200f56f2a540d9593e490a2072ca
achievement=complete
exit_status=0
```

Control:

```sh
python3 -c 'import hashlib,json,runpy; m=runpy.run_path("launch/agent-launch.py"); p=hashlib.sha256(b"packet").hexdigest(); C={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; R=m["ReviewMethodReport"]; Q=m["ReviewReport"]; rows=[R(x,m["STATUS_OK"],"perspective_floor","","model-x","high","openai","exec-stdio-v1","",C) for x in ("panel","lens")]; mk=lambda mid,d,r:{"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":d,"packet_sha256":p,"result_sha256":hashlib.sha256(r.encode()).hexdigest(),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; groups=[[mk("panel","panel-first","a1"),mk("panel","panel-hidden","a2")],[mk("lens","lens-first","b1"),mk("lens","lens-hidden","b2")]]; folded=[m["_merge_method_passes"](mid,g,"main") for mid,g in zip(("panel","lens"),groups)]; report,verdicts=m["verify_review_receipts"](Q(rows[0],(rows[1],),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":folded},{"panel":C,"lens":C}); behavior=json.dumps({"folded":folded,"rendered":m["render_receipt_verdicts"](report,verdicts)},sort_keys=True); print("raw_ids="+repr([[r["dispatch_id"] for r in g] for g in groups])); print("behavior_sha256="+hashlib.sha256(behavior.encode()).hexdigest()); print("achievement="+report.achievement); print("exit_status=0")'
```

```text
raw_ids=[['panel-first', 'panel-hidden'], ['lens-first', 'lens-hidden']]
behavior_sha256=d3989899bc956b50a07a0ddc89def8f1712f200f56f2a540d9593e490a2072ca
achievement=complete
exit_status=0
```

The post-fold behavior is byte-identical, so this was dropped as required.

### D3 — invalid `passes` on a one-trial receipt

Mutation:

```sh
python3 -c '
import hashlib, runpy
m=runpy.run_path("launch/agent-launch.py"); C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel",m["STATUS_OK"],"perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=C,evidence=()); report=m["ReviewReport"](row,(),"perspective_floor"); p=hashlib.sha256(b"packet").hexdigest(); result=hashlib.sha256(b"result").hexdigest(); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child-1","packet_sha256":p,"result_sha256":result,"provider":"openai","model":"model-x","effort":"high","exit_status":0,"passes":[m["EMPTY_SHA256"]]}; out,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[receipt]},{"panel":C}); print("passes="+repr(receipt["passes"])); print("achievement=%s accepted=%s reason=%s"%(out.achievement,vs[0].accepted,vs[0].reason))
'
```

```text
passes=['e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855']
achievement=complete accepted=True reason=verified
```

Control:

```sh
python3 -c '
import hashlib, runpy
m=runpy.run_path("launch/agent-launch.py"); C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=m["ReviewMethodReport"]("panel",m["STATUS_OK"],"perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=C,evidence=()); report=m["ReviewReport"](row,(),"perspective_floor"); p=hashlib.sha256(b"packet").hexdigest(); result=hashlib.sha256(b"result").hexdigest(); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child-1","packet_sha256":p,"result_sha256":result,"provider":"openai","model":"model-x","effort":"high","exit_status":0,"passes":[result]}; out,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[receipt]},{"panel":C}); print("passes="+repr(receipt["passes"])); print("achievement=%s accepted=%s reason=%s"%(out.achievement,vs[0].accepted,vs[0].reason))
'
```

```text
passes=['f6a214f7a5fcda0c2cee9660b7fc29f5649e3c68aad48e20e950137c98913a68']
achievement=complete accepted=True reason=verified
```

Both adjudicate identically, so D3 was dropped under the round’s rule.

## Refuted pre-registration: D2 visible ID reuse

Mutation:

```sh
python3 -c '
import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py"); h=lambda x:hashlib.sha256(x).hexdigest(); C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; R=m["ReviewMethodReport"]; rows=[R(x,"OK","perspective_floor","","model-x","high","openai","native","",C,()) for x in ("panel","lens")]; mk=lambda mid,d:{"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":d,"packet_sha256":h(b"packet"),"result_sha256":h(mid.encode()),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; out,vs=m["verify_review_receipts"](m["ReviewReport"](rows[0],(rows[1],),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":h(b"packet"),"main_dispatch_id":"main","receipts":[mk("panel","shared"),mk("lens","shared")]},{"panel":C,"lens":C}); print("achievement="+out.achievement); print([(v.method_id,v.accepted,v.reason) for v in vs])
'
```

```text
achievement=partial
[('lens', False, 'reuses a dispatch id already credited to another method'), ('panel', True, 'verified')]
```

Control:

```sh
python3 -c '
import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py"); h=lambda x:hashlib.sha256(x).hexdigest(); C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; R=m["ReviewMethodReport"]; rows=[R(x,"OK","perspective_floor","","model-x","high","openai","native","",C,()) for x in ("panel","lens")]; mk=lambda mid,d:{"schema":m["RECEIPT_SCHEMA"],"method_id":mid,"dispatch_id":d,"packet_sha256":h(b"packet"),"result_sha256":h(mid.encode()),"provider":"openai","model":"model-x","effort":"high","exit_status":0}; out,vs=m["verify_review_receipts"](m["ReviewReport"](rows[0],(rows[1],),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":h(b"packet"),"main_dispatch_id":"main","receipts":[mk("panel","panel-id"),mk("lens","lens-id")]},{"panel":C,"lens":C}); print("achievement="+out.achievement); print([(v.method_id,v.accepted,v.reason) for v in vs])
'
```

```text
achievement=complete
[('lens', True, 'verified'), ('panel', True, 'verified')]
```

## Denominator

- Probed: all 33 enforced invariants—L1–L8, D1–D8, F1–F4, V1–V7, S1–S6.
- Read only: none.
- Confirmed violated IDs: L2, L3, L5, L6, D1, D4, D7, D8, F2, F4, V5, S5.
- Held on their probed edge: L1, L4, L7, L8, D5, D6, F1, F3, V1, V2, V3, V4, V6, V7, S1, S2, S3, S4, S6.
- Void: D2’s discarded hidden-pass-ID subcase and D3’s one-trial inert `passes`.
- F4 produced two distinct findings: open bundle grammar and empty method identity.

Pre-registered disposition:

1. L2 confirmed.
2. L5 confirmed.
3. D1 confirmed.
4. V5 confirmed; D2 visible reuse refuted and hidden reuse void.
5. D4 confirmed; V1 held.
6. D8 confirmed.
7. F4 open bundle grammar confirmed.
8. S5 confirmed.

## Not examined

- Adapter honesty, semantic aggregation adherence, and review quality—the specification’s explicit outside set.
- Open questions Q1–Q9 as design decisions.
- Host CLIs; neither `codex` nor `claude` was invoked.
- Sandboxing, permission modes, credentials, and every access-control surface.
- Runtime surfaces outside `launch/agent-launch.py`’s review-evidence subsystem.
- The full parity gate suite; existing check bodies were read only to identify the missed controls.
