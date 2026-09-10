---
created_at: 2026-08-17T23:22:00+09:00
head: 6f2d2f7
kind: review
---

# Spec round 4 — the code held against the third revision (raw findings)

Fourth round under the spec instrument, against `…T2310--11ed16b--review-evidence-invariants.md`.
Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`; 243,691
tokens. Three violations (1 High, 2 Medium; 13 → 6 → 6 → 3); NO spec defects — the amended
sentences are internally consistent; all six round-3 closures replayed and held. Verbatim
below.

Reviewed the clean checkout at `review-round-20`, HEAD `6f2d2f7`. Three violations were confirmed.

## Findings

### 1. High — L2/L3/V2: malformed evidence snapshots earn `complete`

File/function: [`verify_review_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2720).

An in-process selected row may carry an empty evidence-field name. When the current declaration and receipt repeat that invalid name, adjudication credits it.

Mutation:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda s:hashlib.sha256(s.encode()).hexdigest();p=h("packet");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row=m["ReviewMethodReport"]("panel","OK","perspective_floor","","m","high","openai","native","",C,("",));q=m["ReviewReport"](row,(),"perspective_floor");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"m","effort":"high","exit_status":0,"evidence":{"":"yes"}};b={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]};o,v=m["verify_review_receipts"](q,b,{"panel":C},{"panel":("",)});print("accepted achievement="+o.achievement+" verdict="+v[0].reason+" evidence="+repr(row.evidence))'
```

```text
accepted achievement=complete verdict=verified evidence=('',)
```

Control:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda s:hashlib.sha256(s.encode()).hexdigest();p=h("packet");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row=m["ReviewMethodReport"]("panel","OK","perspective_floor","","m","high","openai","native","",C,("must",));q=m["ReviewReport"](row,(),"perspective_floor");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"m","effort":"high","exit_status":0,"evidence":{"must":"yes"}};b={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]};o,v=m["verify_review_receipts"](q,b,{"panel":C},{"panel":("must",)});print("accepted achievement="+o.achievement+" verdict="+v[0].reason+" evidence="+repr(row.evidence))'
```

```text
accepted achievement=complete verdict=verified evidence=('must',)
```

The `None` twins also escape as raw errors:

```text
row.evidence=None                    -> TypeError:'NoneType' object is not iterable
required_evidence["panel"]=None      -> TypeError:'NoneType' object is not iterable
valid empty/matching tuple control   -> achievement=complete, verdict=verified
```

Proposed fix: add one shared evidence-snapshot validator, parallel to `controls_snapshot_reason`, and apply it to every in-process row and current declaration before normalization or comparison. Require a sequence of non-empty strings and retain the marker check.

Missed check: [`launcher_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3833). Its direct evidence cases use only valid tuples; malformed evidence is tested only through serialized-plan parsing.

### 2. Medium — F2: falsey-present and absent control markers fold as agreement

File/function: [`_merge_method_passes`](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:3169).

F2 requires `ordering_seed` and `swap_group` to agree on key presence. The fold compares `bool(receipt.get(...))`, so an empty-but-present marker and an omitted marker are treated alike.

Mutation:

```sh
python3 -c $'import hashlib,json,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda x:hashlib.sha256(x.encode()).hexdigest();p=h("packet")
def r(i,z,**x):return {"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":i,"packet_sha256":p,"result_sha256":h(z),"provider":"openai","model":"model","effort":"high","exit_status":0,**x}
x=m["_merge_method_passes"]("panel",[r("a","one",ordering_seed=""),r("b","two")],"main");print(("accepted","ordering_seed" in x,repr(x.get("ordering_seed")),hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()))'
```

```text
('accepted', True, "''", '05a0a92d87adfdf25eff05182315f92f09f803f01c394fabfb211586ee4c9014')
```

Control:

```sh
python3 -c $'import hashlib,json,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda x:hashlib.sha256(x.encode()).hexdigest();p=h("packet")
def r(i,z,**x):return {"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":i,"packet_sha256":p,"result_sha256":h(z),"provider":"openai","model":"model","effort":"high","exit_status":0,**x}
x=m["_merge_method_passes"]("panel",[r("a","one"),r("b","two")],"main");print(("accepted","ordering_seed" in x,repr(x.get("ordering_seed")),hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()))'
```

```text
('accepted', False, 'None', 'ef4cda1b6e5b48898c753943ee535c2149ff7376a76fa94ad74ff8f81b2c536d')
```

The `swap_group=""` twin behaves identically.

Proposed fix: compare `{field_name in receipt for receipt in group}`. Uniform falsey extras remain foldable; mixed key presence is refused.

Missed check: [`launcher_receipt_fold`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:5407). It checks truthy-versus-omitted and truthy-versus-empty, but not empty-present versus omitted.

### 3. Medium — V2/V7: a non-map controls registry fails before validation

File/function: [`verify_review_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:2659).

The round-3 shared controls validator never receives `required_controls=None`; `set(required_controls)` throws first.

Mutation:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda s:hashlib.sha256(s.encode()).hexdigest();p=h("packet");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row=m["ReviewMethodReport"]("panel","OK","perspective_floor","","m","high","openai","native","",C,());q=m["ReviewReport"](row,(),"perspective_floor");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"m","effort":"high","exit_status":0};b={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]}
try:o,v=m["verify_review_receipts"](q,b,None,{"panel":()});print("accepted achievement="+o.achievement+" verdict="+v[0].reason)
except Exception as x:print("refused "+type(x).__name__+":"+str(x))'
```

```text
refused TypeError:'NoneType' object is not iterable
```

Control:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");h=lambda s:hashlib.sha256(s.encode()).hexdigest();p=h("packet");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row=m["ReviewMethodReport"]("panel","OK","perspective_floor","","m","high","openai","native","",C,());q=m["ReviewReport"](row,(),"perspective_floor");r={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":p,"result_sha256":h("result"),"provider":"openai","model":"m","effort":"high","exit_status":0};b={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":p,"main_dispatch_id":"main","receipts":[r]}
try:o,v=m["verify_review_receipts"](q,b,{"panel":C},{"panel":()});print("accepted achievement="+o.achievement+" verdict="+v[0].reason)
except Exception as x:print("refused "+type(x).__name__+":"+str(x))'
```

```text
accepted achievement=complete verdict=verified
```

Proposed fix: require `required_controls` to be a map before computing the unregistered set, raising a named `LaunchError`; keep `controls_snapshot_reason` as the per-method validator.

Missed check: [`launcher_receipts`](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:3833). Its direct-controls helper always constructs the outer map.

## Round-3 closure replays

All six closures still hold:

| Invariant | Mutation now | Control now |
|---|---|---|
| L1 | Marker-bearing offer drops marker-free; `marker_count=1`, `evidence=()` | `marker_count=1`, `evidence=('shadow',)` |
| L2 | List `detail` refused by name | String `detail` accepted |
| L3 | Invented DROPPED grade refused | `None` and `NOT_REVIEW` accepted |
| V2 | Whole evidence map `None` refused by named `LaunchError` | Drifted evidence declaration refused by name |
| V3 | Empty controls snapshot refused | Complete two-trial controls reach the pass-count refusal |
| S4 | Nested inactive override renders successfully | Scalar inactive override renders successfully |

The instruction-field, row-reader, registry-controls, record-span, `swap_group`, review-arm, and named nested-refusal twins were also reached.

## Spec defects

None confirmed. The amended D6 and S1 sentences are now internally consistent, and L5’s main-seat derivability limit is explicitly disclosed rather than rendered as derived.

## Void readings

- A dictionary-valued current evidence declaration and its tuple control both return:

  ```text
  accepted achievement=complete verdict=verified
  ```

  Dropped: the dictionary is outside the declared offer shape and produced no differing adjudication output.

- The original round-3 F2 arrangement, where the canonical representative omitted the falsey marker, remains void:

  ```text
  mutation=accepted sha256=ef4cda1b6e5b48898c753943ee535c2149ff7376a76fa94ad74ff8f81b2c536d
  control =accepted sha256=ef4cda1b6e5b48898c753943ee535c2149ff7376a76fa94ad74ff8f81b2c536d
  ```

  Finding 2 is the discriminating twin where the canonical representative carries the falsey-present key.

## Denominator

- Probed: all 33 invariants — L1–L8, D1–D8, F1–F4, V1–V7, S1–S6.
- Read only: none.
- Violated IDs: L2, L3, F2, V2, V7.
- Both required dry-runs exited 0 with `--config launch/agent-launch.toml`.
- Relevant gate bodies were inspected; the full parity suite was not run.
- Worktree remained clean at `6f2d2f7`.

## Not examined

- Adapter honesty, semantic aggregation adherence, or review quality.
- Q1–Q9 as defects.
- Host-CLI execution.
- Credentials or excluded access-control surfaces.
- Runtime outside the named subsystem.
- Real concurrent filesystem interleavings for D8/S5; bounded injected-failure probes covered their post-failure residue.
