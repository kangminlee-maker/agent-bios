---
created_at: 2026-08-17T21:01:00+09:00
head: a2f061f
kind: review
---

# Spec round 3 — the code held against the second revision (raw findings)

Third round under the spec instrument, against `…T2012--9c1dad6--review-evidence-invariants.md`.
Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`; 359,530
tokens. Six violations (3 High, 3 Medium; 13 → 6 → 6), two specification defects, void
readings and denominator inside. Verbatim below.

Reviewed `review-round-20` at `a2f061f`. Six code violations and two specification defects were confirmed. The worktree remained clean.

## Findings

### 1. V2 — High — evidence drift comparison is optional

File/function: [launch/agent-launch.py:verify_review_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2508). `required_evidence=None` skips the comparison that V2 calls unconditional.

Mutation:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda x:hashlib.sha256(x.encode()).hexdigest();p=h("packet");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};q=m["ReviewReport"](m["ReviewMethodReport"]("panel","OK","perspective_floor","","model-x","high","openai","native","",C,("must",)),(),"perspective_floor");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0,"evidence":{"must":"yes"}};B={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]};o,v=m["verify_review_receipts"](q,B,{"panel":C},None);print("accepted achievement="+o.achievement+" verdict="+v[0].reason)'
```

```text
accepted achievement=complete verdict=verified
```

Control—supply the current, drifted declaration:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda x:hashlib.sha256(x.encode()).hexdigest();p=h("packet");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};q=m["ReviewReport"](m["ReviewMethodReport"]("panel","OK","perspective_floor","","model-x","high","openai","native","",C,("must",)),(),"perspective_floor");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0,"evidence":{"must":"yes"}};B={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]};
try:m["verify_review_receipts"](q,B,{"panel":C},{"panel":("other",)})
except Exception as e:print("refused "+type(e).__name__+":"+str(e))'
```

```text
refused LaunchError:cannot adjudicate 'panel': the plan recorded evidence ['must'] at launch and the registry now declares ['other'] — the capability's offer changed since; re-launch or verify against the registry of the time
```

Proposed fix: treat `None` as an absent declaration and refuse it; execute the evidence comparison unconditionally.

Missed check: [launcher_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691) tests a missing entry inside a supplied map, not omission of the whole map.

### 2. V3 — High — empty controls default to one pass

File/functions: [verify_review_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2508), [_receipt_reason](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2451). Matching empty snapshot/current maps reach `controls.get("trials", 1)` and earn complete.

Mutation:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda x:hashlib.sha256(x.encode()).hexdigest();p=h("packet");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0};B={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]};C={};q=m["ReviewReport"](m["ReviewMethodReport"]("panel","OK","perspective_floor","","model-x","high","openai","native","",C,()),(),"perspective_floor");o,v=m["verify_review_receipts"](q,B,{"panel":C},{"panel":()});print("accepted achievement="+o.achievement+" verdict="+v[0].reason)'
```

```text
accepted achievement=complete verdict=verified
```

Control:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda x:hashlib.sha256(x.encode()).hexdigest();p=h("packet");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"model-x","effort":"high","exit_status":0};B={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]};C={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"};q=m["ReviewReport"](m["ReviewMethodReport"]("panel","OK","perspective_floor","","model-x","high","openai","native","",C,()),(),"perspective_floor");o,v=m["verify_review_receipts"](q,B,{"panel":C},{"panel":()});print("accepted achievement="+o.achievement+" verdict="+v[0].reason)'
```

```text
accepted achievement=none verdict=carries no pass list, so it evidences fewer than the 2 requested passes
```

Proposed fix: validate both row and current controls against the closed `CONTROLS_KEYS` grammar before comparison, then index `controls["trials"]` without a default.

Missed check: [launcher_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691).

### 3. L1 — High — an evidence name creates a second plan marker

Files/functions: [parse_capability_offers](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:1233), [run_contract](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:7834). An offer’s authored evidence name is serialized into the canonical record without the marker guard.

Mutation:

```sh
python3 -c $'import copy,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));e=m["REVIEW_PLAN_MARKER"]+"shadow";c["capabilities"]["marker-cap"]={"command":"/bin/echo","offers":[{"operation":"marker-review","adapter":"exec-stdio-v1","hosts":["codex"],"evidence":[e]}]};r=copy.deepcopy(c["review_methods"]["codex-exec"]);r.update(capability="marker-cap",operation="marker-review");c["review_methods"]["marker-method"]=r;c["presets"]["balanced"]["review"]["hosts"]["codex"].setdefault("methods",{})["marker-method"]={"provider":"openai","tier":"frontier"};p=m["build_plan"](c,"codex","balanced");x=m["run_contract"](p);print("accepted marker_count="+str(x.count(m["REVIEW_PLAN_MARKER"]))+" evidence="+repr(p["review_report"].methods[0].evidence))'
```

```text
accepted marker_count=2 evidence=('ReviewPlan/v1: shadow',)
```

Control:

```sh
python3 -c $'import copy,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));e="shadow";c["capabilities"]["marker-cap"]={"command":"/bin/echo","offers":[{"operation":"marker-review","adapter":"exec-stdio-v1","hosts":["codex"],"evidence":[e]}]};r=copy.deepcopy(c["review_methods"]["codex-exec"]);r.update(capability="marker-cap",operation="marker-review");c["review_methods"]["marker-method"]=r;c["presets"]["balanced"]["review"]["hosts"]["codex"].setdefault("methods",{})["marker-method"]={"provider":"openai","tier":"frontier"};p=m["build_plan"](c,"codex","balanced");x=m["run_contract"](p);print("accepted marker_count="+str(x.count(m["REVIEW_PLAN_MARKER"]))+" evidence="+repr(p["review_report"].methods[0].evidence))'
```

```text
accepted marker_count=1 evidence=('shadow',)
```

Proposed fix: apply one shared evidence-name validator, including `refuse_plan_marker`, in both capability-offer parsing and `_row_from_v1`.

Missed check: [launcher_review_contract](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:2518).

### 4. L2 — Medium — row prose fields accept wrong containers

File/function: [_row_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2059). `detail` and its twin `instruction` are copied without type validation.

Mutation:

```sh
python3 -c $'import runpy
m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};R={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":["not","text"],"model":"m","effort":"high","provider":"openai","mechanism":"native","instruction":"","controls":C,"evidence":[]};P={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":R,"methods":[]};q=m["review_plan_from_v1"](P);print("accepted detail_type="+type(q.base.detail).__name__+" detail="+repr(q.base.detail))'
```

```text
accepted detail_type=list detail=['not', 'text']
```

Control:

```sh
python3 -c $'import runpy
m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};R={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"not text","model":"m","effort":"high","provider":"openai","mechanism":"native","instruction":"","controls":C,"evidence":[]};P={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":R,"methods":[]};q=m["review_plan_from_v1"](P);print("accepted detail_type="+type(q.base.detail).__name__+" detail="+repr(q.base.detail))'
```

```text
accepted detail_type=str detail='not text'
```

Proposed fix: require `detail` and `instruction` to be strings in `_row_from_v1`.

Missed check: [launcher_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691).

### 5. L3 — Medium — DROPPED accepts an invented grade

File/function: [_row_from_v1](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2125). It rejects ladder grades but accepts arbitrary values outside both permitted DROPPED grades.

Mutation:

```sh
python3 -c $'import runpy
m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};B={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"m","effort":"high","provider":"openai","mechanism":"native","instruction":"","controls":C,"evidence":[]};D={"method_id":"optional","status":"DROPPED","grade":"invented-grade","detail":"did not run","model":None,"effort":None,"provider":None,"mechanism":None,"instruction":"","controls":None,"evidence":[]};P={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":B,"methods":[D]};q=m["review_plan_from_v1"](P);print("accepted dropped_grade="+repr(q.methods[0].grade))'
```

```text
accepted dropped_grade='invented-grade'
```

Control:

```sh
python3 -c $'import runpy
m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};B={"method_id":"panel","status":"OK","grade":"perspective_floor","detail":"","model":"m","effort":"high","provider":"openai","mechanism":"native","instruction":"","controls":C,"evidence":[]};D={"method_id":"optional","status":"DROPPED","grade":None,"detail":"did not run","model":None,"effort":None,"provider":None,"mechanism":None,"instruction":"","controls":None,"evidence":[]};P={"schema":"ReviewPlan/v1","availability":"projected","best_grade":"perspective_floor","achieved_grade":"UNKNOWN_UNTIL_RECEIPTS","base":B,"methods":[D]};q=m["review_plan_from_v1"](P);print("accepted dropped_grade="+repr(q.methods[0].grade))'
```

```text
accepted dropped_grade=None
```

Proposed fix: on a DROPPED row, reject every grade not in `{None, GRADE_NOT_REVIEW}`.

Missed check: [launcher_receipts](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3691).

### 6. S4 — Medium — nested inactive override refusal does not name the entry

File/function: [render_preset_block](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:6043). The active-host reader accepts the profile, but the inactive override reaches `_toml_scalar` and loses its path.

Mutation:

```sh
python3 -c $'import pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["solo"]["tier_overrides"]={"claude":{"workhorse":{"future":{"nested":1}}}};p=m["build_plan"](c,"codex","solo");f,o,r=m["preset_from_plan"](p,c,"saved");
try:m["render_preset_block"]("saved",f,o,r)
except Exception as e:print("refused "+type(e).__name__+":"+str(e))'
```

```text
refused LaunchError:cannot serialize preset value: {'nested': 1}
```

Control:

```sh
python3 -c $'import pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["solo"]["tier_overrides"]={"claude":{"workhorse":{"future":"keep"}}};p=m["build_plan"](c,"codex","solo");f,o,r=m["preset_from_plan"](p,c,"saved");text=m["render_preset_block"]("saved",f,o,r);print("accepted rendered_future="+str("future = \\"keep\\"" in text))'
```

```text
accepted rendered_future=True
```

Proposed fix: generalize the existing recursive table emitter to inactive tier overrides so TOML-producible nested values remain saveable; any genuine refusal must include `tier_overrides.claude.workhorse.future`.

Missed check: [preset_save](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:11745).

## Spec defects

1. **D6 gives incompatible verdicts for undeclared markers.** The invariant says `ordering_seed`/`swap_group` are “present iff” declared, which forbids extras, while its checklist names only a marker being *demanded* when undeclared. The current extra-marker mutation and no-marker control both return `('complete', True, 'verified')`. Amend “present iff” to “required when declared” if extras are intentionally ignored, or explicitly require their absence and add that mutation to the checklist. See [D6](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T2012--9c1dad6--review-evidence-invariants.md:159) and its [checklist](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T2012--9c1dad6--review-evidence-invariants.md:335).

2. **S1 does not define NaN semantic identity.** It requires type-aware preservation while saying NaNs “compare as parsed values,” but parsed NaN is not equal to itself and the sign is independently observable.

   Mutation:

   ```sh
   python3 -c 'import math,tomllib; v=tomllib.loads("x=-nan\n")["x"]; print("sign=%d self_equal=%s" % (math.copysign(1,v), v==v))'
   ```

   ```text
   sign=-1 self_equal=False
   ```

   Control:

   ```sh
   python3 -c 'import math,tomllib; v=tomllib.loads("x=nan\n")["x"]; print("sign=%d self_equal=%s" % (math.copysign(1,v), v==v))'
   ```

   ```text
   sign=1 self_equal=False
   ```

   Specify whether all NaNs are equivalent or whether `math.copysign` must be preserved. Until then, the observed `-nan`→`nan` save cannot be classified as compliant or violating. See [S1](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T2012--9c1dad6--review-evidence-invariants.md:226).

## Void readings

Dropped because mutation and nearest control had identical observable outputs:

- D6 undeclared control markers:

  ```text
  mutation=('complete', True, 'verified')
  control =('complete', True, 'verified')
  ```

- F2 falsey `ordering_seed` present on only one pass versus uniformly present:

  ```text
  mutation=accepted sha256=c79a8dfdc05f588c434d98c425f3239347b0c1dd1337998c0e0b2b3f38ac5f31
  control =accepted sha256=c79a8dfdc05f588c434d98c425f3239347b0c1dd1337998c0e0b2b3f38ac5f31
  ```

- S3 active-host raw effort conflict versus agreement:

  ```text
  mutation=accepted sha256=7159901e0fd334c7111d793c6faf8720172751def27fd790359963a093a014a7
  control =accepted sha256=7159901e0fd334c7111d793c6faf8720172751def27fd790359963a093a014a7
  ```

## Denominator

- Probed: all 33 invariants—L1–L8, D1–D8, F1–F4, V1–V7, S1–S6.
- Read only: none.
- Code-violated IDs: L1, L2, L3, V2, V3, S4.
- Spec-defective IDs: D6, S1.
- Held on their probed enforceable edge: L4–L8; D1–D5 and D7–D8; F1–F4; V1 and V4–V7; S2–S3 and S5–S6.
- All six round-2 closures held on replay, including both readers reached by `_review_identity_reason`, `select_capability_offer`, `controls_value_reason`, and `publish_atomically`.
- Correctly ordered Codex and Claude `--dry-run` commands, each with `--config launch/agent-launch.toml`, exited 0.
- Worktree remained clean at `a2f061f`.

## Not examined

- Adapter honesty, semantic aggregation adherence, and review quality.
- Q1–Q9 as design decisions.
- Host-CLI behavior, credentials, sandboxing, permission behavior, or access-control surfaces.
- Runtime outside the named subsystem.
- Real concurrent-process interleavings; D8/S5 used bounded failure-residue probes.
- The full parity suite, because it creates temporary artifacts; its relevant check bodies were read.

Scope incident: one delegated worker placed global flags after the host positional, briefly reaching both host binaries’ argument parsers. Both exited immediately; those outputs were excluded. No access-control state was inspected, and the subsequent correctly ordered dry-runs did not dispatch either backend.
