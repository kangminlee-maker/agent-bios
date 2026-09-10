---
created_at: 2026-08-16T23:05:00+09:00
head: 17292a8
kind: review
---

# Round 21 — cross-family review of the round-20 repairs (raw findings)

Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`, packet on stdin (this session's `r21-packet.md`: the round-20 repairs in `68bb011`, host CLIs not to be invoked); 354,505 tokens. Nine findings admitted (3 High, 5 Medium, 1 Low), two candidates void; corpus-state and the wizard trial path again unreached. Verbatim below.

Review result: 9 findings—3 high, 5 medium, 1 low. No files changed and no host CLI was invoked. Commands below ran from `/private/tmp/fix-tree` at `17292a8`.

## Findings

### 1. High — `panel` can be selected twice, and one receipt certifies both rows

[launch/agent-launch.py:815](/private/tmp/fix-tree/launch/agent-launch.py:815), [launch/agent-launch.py:2022](/private/tmp/fix-tree/launch/agent-launch.py:2022)

What it says: the editor states that `panel` is the mandatory base and therefore never belongs in the optional method map.

What it does: the composable schema accepts `methods.panel`. The resulting report contains two selected `panel` rows, which `verify_review_receipts` collapses into one dictionary entry. One receipt then yields `complete`.

Mutation:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["presets"]["balanced"]["review"]["hosts"]["claude"]["methods"]={"panel":{"provider":"openai","tier":"helm"}}; p=m["build_plan"](c,"claude","balanced"); r=p["review_report"]; row=r.base; controls=m["method_controls"](m["load_review_methods"](c)["panel"]); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":row.provider,"model":row.model,"effort":row.effort,"exit_status":0,"passes":["a","b","c"],"ordering_seed":"seed","swap_group":"swap"}; v,vs=m["verify_review_receipts"](r,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"panel":controls}); print("selected_rows=%d ids=%r verdicts=%d achievement=%s" % (1+len(r.methods),[r.base.method_id,*[x.method_id for x in r.methods]],len(vs),v.achievement)); print(m["render_receipt_verdicts"](v,vs))'
```

```text
selected_rows=2 ids=['panel', 'panel'] verdicts=1 achievement=complete
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=provider_difference, availability=projected — launch-time projection, unchanged by verification)
  panel: ACHIEVED/provider_difference — verified
```

Control—same two rows, but distinct IDs:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=lambda i:R(i,m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",c); r=RR(row("probe"),(row("probe-2"),),"perspective_floor"); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; v,vs=m["verify_review_receipts"](r,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":c,"probe-2":c}); print("selected_rows=2 ids=%r verdicts=%d achievement=%s" % (["probe","probe-2"],len(vs),v.achievement)); print(m["render_receipt_verdicts"](v,vs))'
```

```text
selected_rows=2 ids=['probe', 'probe-2'] verdicts=2 achievement=partial
Review achievement (achievement=partial [1/2 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  probe: ACHIEVED/perspective_floor — verified
  probe-2: PROPOSED — no receipt was supplied
```

Proposed fix: reject reserved method ID `panel` while parsing optional methods, and defensively reject duplicate selected method IDs before verification.

Missed check: `launcher_review_schema` should mutate a valid block with `methods.panel`. `launcher_review_editor` proves only that the UI does not author it.

### 2. High — fold validates only the first pass’s receipt schema

[launch/agent-launch.py:2245](/private/tmp/fix-tree/launch/agent-launch.py:2245), [launch/agent-launch.py:2308](/private/tmp/fix-tree/launch/agent-launch.py:2308)

What it says: “Every pass is judged BEFORE anything is folded.”

What it does: per-pass validation omits the receipt schema. The fold retains the first receipt’s schema, so a later receipt with a bogus schema contributes a credited result hash and disappears.

Mutation—valid receipt first, bogus schema second:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",c); base={"method_id":"probe","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0}; good=base|{"schema":m["RECEIPT_SCHEMA"],"dispatch_id":"child-1","result_sha256":"one"}; wrong=base|{"schema":"NotAReceipt/v1","dispatch_id":"child-2","result_sha256":"two"}; merged=m["_merge_method_passes"]("probe",[good,wrong],"main"); verified,vs=m["verify_review_receipts"](RR(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"probe":c}); print("folded_schema=%s passes=%r achievement=%s" % (merged["schema"],merged["passes"],verified.achievement)); print(m["render_receipt_verdicts"](verified,vs))'
```

```text
folded_schema=ReviewReceipt/v1 passes=['one', 'two'] achievement=complete
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  probe: ACHIEVED/perspective_floor — verified
```

Control—the same receipts reversed:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",c); base={"method_id":"probe","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0}; good=base|{"schema":m["RECEIPT_SCHEMA"],"dispatch_id":"child-1","result_sha256":"one"}; wrong=base|{"schema":"NotAReceipt/v1","dispatch_id":"child-2","result_sha256":"two"}; merged=m["_merge_method_passes"]("probe",[wrong,good],"main"); verified,vs=m["verify_review_receipts"](RR(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"probe":c}); print("folded_schema=%s passes=%r achievement=%s" % (merged["schema"],merged["passes"],verified.achievement)); print(m["render_receipt_verdicts"](verified,vs))'
```

```text
folded_schema=NotAReceipt/v1 passes=['one', 'two'] achievement=none
Review achievement (achievement=none [0/1 evidenced], achieved_grade=UNKNOWN_UNTIL_RECEIPTS, availability=projected — launch-time projection, unchanged by verification)
  probe: PROPOSED — not a ReviewReceipt/v1 record
```

Proposed fix: apply one shared structural receipt validator to every raw pass before folding, including schema and allowed/required fields. Folding should not make an invalid pass unobservable.

Missed check: `launcher_receipt_fold` covers pass IDs, results, evidence table shape, and seat agreement, but not a bad schema in a later pass.

### 3. High — a later pass’s empty required evidence is hidden by folding

[launch/agent-launch.py:1954](/private/tmp/fix-tree/launch/agent-launch.py:1954), [launch/agent-launch.py:2297](/private/tmp/fix-tree/launch/agent-launch.py:2297)

What it says: a dispatch that reports no value for a capability-required field “is not evidenced,” and every pass is judged before folding.

What it does: folding compares only evidence key sets and retains the first pass’s values. A later `{"reached_seat": ""}` is credited when the first pass supplied a non-empty value.

Mutation:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",c); base={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0}; first=base|{"dispatch_id":"child-1","result_sha256":"one","evidence":{"reached_seat":"seat-1"}}; blank=base|{"dispatch_id":"child-2","result_sha256":"two","evidence":{"reached_seat":""}}; merged=m["_merge_method_passes"]("probe",[first,blank],"main"); v,vs=m["verify_review_receipts"](RR(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"probe":c},{"probe":("reached_seat",)}); print("folded_evidence=%r achievement=%s" % (merged["evidence"],v.achievement)); print(m["render_receipt_verdicts"](v,vs)); print("later_alone=%s" % m["_receipt_reason"](blank,row,{"packet_sha256":"packet","main_dispatch_id":"main"},set(),c,("reached_seat",)))'
```

```text
folded_evidence={'reached_seat': 'seat-1'} achievement=complete
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  probe: ACHIEVED/perspective_floor — verified
later_alone=reports none of reached_seat, which this capability's offer declares it returns — a dispatch that reported nothing is not evidenced
```

Control—the same later pass omits the key entirely:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); base={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0}; first=base|{"dispatch_id":"child-1","result_sha256":"one","evidence":{"reached_seat":"seat-1"}}; missing=base|{"dispatch_id":"child-2","result_sha256":"two","evidence":{}};
try: m["_merge_method_passes"]("probe",[first,missing],"main")
except m["LaunchError"] as e: print("REFUSED: %s" % e)'
```

```text
REFUSED: receipts for 'probe' report different evidence fields ([[], ['reached_seat']]); a pass that reported less is not evidenced by one that reported more
```

Proposed fix: preserve per-pass evidence and apply the capability’s required-evidence bar to every pass. At minimum, folding must not discard falsey later values that `_receipt_reason` treats as missing.

Missed check: `launcher_receipt_fold` tests different evidence field sets, not an identical field set with one empty required value.

### 4. Medium — Claude execution mode changes argv while the injected contract is identical

[launch/agent-launch.py:6641](/private/tmp/fix-tree/launch/agent-launch.py:6641), [launch/agent-launch.py:6952](/private/tmp/fix-tree/launch/agent-launch.py:6952)

What it says: forwarded collisions are refused “so what is described here is what runs.”

What it does: `claude_permission_mode` changes projected argv but is absent from the contract. This is strictly a value-fidelity finding, not an assessment of either mode.

Mutation:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); a=m["build_plan"](c,"claude","balanced"); c["presets"]["balanced"]["claude_permission_mode"]="standard"; b=m["build_plan"](c,"claude","balanced"); print("contract_equal=%s" % (m["run_contract"](a)==m["run_contract"](b))); print("first_policy_tokens=%r" % [x for x in m["project_args"](a,False) if "permission" in x or x=="--dangerously-skip-permissions"]); print("second_policy_tokens=%r" % [x for x in m["project_args"](b,False) if "permission" in x or x=="--dangerously-skip-permissions"]); print("contract_mentions_values=%s/%s" % (a["claude_permission_mode"] in m["run_contract"](a),b["claude_permission_mode"] in m["run_contract"](b)))'
```

```text
contract_equal=True
first_policy_tokens=['--dangerously-skip-permissions']
second_policy_tokens=[]
contract_mentions_values=False/False
```

Control—change a value the contract does project:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); a=m["build_plan"](c,"claude","balanced"); c["hosts"]["claude"]["tiers"]["helm"]["model"]="claude-fable-5"; b=m["build_plan"](c,"claude","balanced"); print("contract_equal=%s" % (m["run_contract"](a)==m["run_contract"](b))); print("models=%r/%r" % (m["project_args"](a,False)[1],m["project_args"](b,False)[1]))'
```

```text
contract_equal=False
models='claude-opus-5'/'claude-fable-5'
```

Proposed fix: render the resolved Claude mode into `run_contract` from the same plan field consumed by `project_args`.

Missed check: `backend_dispatch` verifies the mode’s argv projection but never compares it with the injected contract. The review-matrix golden freezes both outputs independently.

### 5. Medium — Save As loses inactive-host tier overrides

[launch/agent-launch.py:4918](/private/tmp/fix-tree/launch/agent-launch.py:4918), [launch/agent-launch.py:4925](/private/tmp/fix-tree/launch/agent-launch.py:4925)

What it says: only the active host is rebuilt; “every other host is written back as authored.”

What it does: inactive overrides are loaded from `config["presets"][name]`, where `name` is the destination. Saving under a new name therefore finds no source overrides.

Mutation—save `balanced` as `balanced-copy`:

```sh
python3 -c 'import runpy,pathlib,tomllib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["presets"]["balanced"]["tier_overrides"]={"codex":{"workhorse":{"model":"gpt-5.6-sol"}},"claude":{"workhorse":{"model":"claude-fable-5"}}}; p=m["build_plan"](c,"codex","balanced"); f,o,r=m["preset_from_plan"](p,c,"balanced-copy"); saved=tomllib.loads(m["render_preset_block"]("balanced-copy",f,o,r))["presets"]["balanced-copy"]; print("source_hosts=%r saved_hosts=%r" % (sorted(c["presets"]["balanced"]["tier_overrides"]),sorted(saved.get("tier_overrides",{})))); print("saved_claude_model=%r" % saved.get("tier_overrides",{}).get("claude",{}).get("workhorse",{}).get("model"))'
```

```text
source_hosts=['claude', 'codex'] saved_hosts=['codex']
saved_claude_model=None
```

Control—save back under the source name:

```sh
python3 -c 'import runpy,pathlib,tomllib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["presets"]["balanced"]["tier_overrides"]={"codex":{"workhorse":{"model":"gpt-5.6-sol"}},"claude":{"workhorse":{"model":"claude-fable-5"}}}; p=m["build_plan"](c,"codex","balanced"); f,o,r=m["preset_from_plan"](p,c,"balanced"); saved=tomllib.loads(m["render_preset_block"]("balanced",f,o,r))["presets"]["balanced"]; print("source_hosts=%r saved_hosts=%r" % (sorted(c["presets"]["balanced"]["tier_overrides"]),sorted(saved.get("tier_overrides",{})))); print("saved_claude_model=%r" % saved.get("tier_overrides",{}).get("claude",{}).get("workhorse",{}).get("model"))'
```

```text
source_hosts=['claude', 'codex'] saved_hosts=['claude', 'codex']
saved_claude_model='claude-fable-5'
```

Proposed fix: carry the source preset’s raw host overrides in the plan/save input, then replace only the active-host block. Never infer the source from the destination name.

Missed checks: `preset_save_round_trips` uses shipped presets with no cross-host tier overrides and compares only the active host. `preset_save` checks active override isolation, not source-to-new-name preservation.

### 6. Medium — malformed `ReviewPlan/v1` rows escape as `AttributeError`

[launch/agent-launch.py:1822](/private/tmp/fix-tree/launch/agent-launch.py:1822), [launch/agent-launch.py:1847](/private/tmp/fix-tree/launch/agent-launch.py:1847)

What it says: a record “holding the wrong shape is named, not tracebacked.”

What it does: `_row_from_v1` assumes a dictionary. A string row reaches `.get()` while formatting the intended refusal and leaks `AttributeError`, which the caller does not catch.

Mutation:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); bad={"schema":m["REVIEW_PLAN_SCHEMA"],"availability":"projected","best_grade":"perspective_floor","achieved_grade":m["ACHIEVED_UNKNOWN"],"base":"not-a-row","methods":[]};
try: m["review_plan_from_v1"](bad)
except Exception as e: print("%s: %s" % (type(e).__name__,e))'
```

```text
AttributeError: 'str' object has no attribute 'get'
```

Control—dictionary row missing the same required field:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); bad={"schema":m["REVIEW_PLAN_SCHEMA"],"availability":"projected","best_grade":"perspective_floor","achieved_grade":m["ACHIEVED_UNKNOWN"],"base":{},"methods":[]};
try: m["review_plan_from_v1"](bad)
except Exception as e: print("%s: %s" % (type(e).__name__,e))'
```

```text
LaunchError: ReviewPlan/v1 row None carries no 'controls'; the record predates the declaration the verifier audits against — re-launch
```

Proposed fix: require `base` and each `methods` element to be dictionaries, and require `methods` itself to be an array, before row conversion.

Missed check: `launcher_receipts` covers absent and null `controls`, but not a non-table base/method row passed through the verifier.

### 7. Medium — an extra foreign receipt produces `complete [1/2 evidenced]`

[launch/agent-launch.py:1998](/private/tmp/fix-tree/launch/agent-launch.py:1998), [launch/agent-launch.py:2069](/private/tmp/fix-tree/launch/agent-launch.py:2069), [launch/agent-launch.py:2108](/private/tmp/fix-tree/launch/agent-launch.py:2108)

What it says: the verifier returns “one verdict per selected method,” and the displayed fraction describes review coverage.

What it does: it retains verdicts for receipts naming no selected method. Completeness compares accepted receipts against selected methods, while rendering uses every verdict as the denominator.

Mutation:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",c); good={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; ghost=good|{"method_id":"ghost","dispatch_id":"ghost-child"}; v,vs=m["verify_review_receipts"](RR(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[good,ghost]},{"probe":c}); print(m["render_receipt_verdicts"](v,vs))'
```

```text
Review achievement (achievement=complete [1/2 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  ghost: PROPOSED — names no selected method in the plan
  probe: ACHIEVED/perspective_floor — verified
```

Control:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",c); good={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; v,vs=m["verify_review_receipts"](RR(row,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[good]},{"probe":c}); print(m["render_receipt_verdicts"](v,vs))'
```

```text
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  probe: ACHIEVED/perspective_floor — verified
```

Proposed fix: calculate coverage solely over selected methods and render foreign-receipt diagnostics separately—or reject foreign receipts at the bundle boundary.

Missed check: `launcher_receipts` tests an unknown receipt only by replacing selected evidence, never by adding one to an otherwise complete bundle.

### 8. Medium — shipped `solo` summary advertises a cross-family route that does not exist

[launch/agent-launch.py:6601](/private/tmp/fix-tree/launch/agent-launch.py:6601), [launch/agent-launch.py:7035](/private/tmp/fix-tree/launch/agent-launch.py:7035)

What it says: `review_setup="none"` means no review route for either family. The injected contract correctly says so.

What it does: `print_summary` appends `cross-family review on …` whenever the family is `cross`, even when `effective_review` is empty.

Mutation—shipped `solo`:

```sh
python3 -c 'import runpy,pathlib,io; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); p=m["build_plan"](c,"codex","solo"); out=io.StringIO(); m["print_summary"](p,"codex",m["project_args"](p,False),out); print(next(x.strip() for x in out.getvalue().splitlines() if "Review setup" in x)); print("effective=%r contract=%s" % (m["effective_review"](p)[0], "No additional review route requested" in m["run_contract"](p)))'
```

```text
Review setup   none · cross-family review on claude · configured/requested · completed: not enforced
effective=[] contract=True
```

Control—same preset with `review_family="same"`:

```sh
python3 -c 'import runpy,pathlib,io; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["presets"]["solo"]["review_family"]="same"; p=m["build_plan"](c,"codex","solo"); out=io.StringIO(); m["print_summary"](p,"codex",m["project_args"](p,False),out); print(next(x.strip() for x in out.getvalue().splitlines() if "Review setup" in x)); print("effective=%r contract=%s" % (m["effective_review"](p)[0], "No additional review route requested" in m["run_contract"](p)))'
```

```text
Review setup   none · configured/requested · completed: not enforced
effective=[] contract=True
```

Proposed fix: share the `not effective and requested == "none"` result between `run_contract` and `print_summary`; append cross-family details only when a route exists.

Missed check: `launcher_delegation_clause` already enumerates `solo` and renders its summary, but asserts only delegation/tier prose. `cross_family` checks the contract, not the summary.

### 9. Low — a valid literal dotted TOML key is falsely refused as an override

[launch/agent-launch.py:6790](/private/tmp/fix-tree/launch/agent-launch.py:6790), [launch/agent-launch.py:6874](/private/tmp/fix-tree/launch/agent-launch.py:6874)

What it says: keys are canonicalized “as TOML reads” them, and only settings that actually override projected values are refused; everything else forwards verbatim.

What it does: canonicalization dot-joins parsed segments. TOML’s nested key `agents.sweep.description` and distinct literal key `"agents.sweep.description"` therefore collapse to the same string.

Mutation:

```sh
python3 -c 'import runpy,tomllib; m=runpy.run_path("launch/agent-launch.py"); p=["-c","agents.sweep.description=\"owned\""]; f=["-c","\"agents.sweep.description\"=\"forwarded\""]; print("collisions=%r" % m["forwarded_collisions"](p,f)); print("canonical=%r/%r" % (m["canonical_config_key"]("agents.sweep.description"),m["canonical_config_key"]("\"agents.sweep.description\""))); print("toml=%r / %r" % (tomllib.loads("agents.sweep.description=\"owned\""),tomllib.loads("\"agents.sweep.description\"=\"forwarded\"")))'
```

```text
collisions=['-c agents.sweep.description']
canonical='agents.sweep.description'/'agents.sweep.description'
toml={'agents': {'sweep': {'description': 'owned'}}} / {'agents.sweep.description': 'forwarded'}
```

Control—an actually separate nested key:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); p=["-c","agents.sweep.description=\"owned\""]; f=["-c","agents.reviewer.config_file=\"/x\""]; print("collisions=%r canonical=%r" % (m["forwarded_collisions"](p,f),m["canonical_config_key"]("agents.reviewer.config_file")))'
```

```text
collisions=[] canonical='agents.reviewer.config_file'
```

All four supported `-c`/`--config` spellings produced the same false collision.

Proposed fix: retain TOML keys as tuples of parsed segments and compare tuple prefixes. Do not serialize the segments back into an ambiguous dotted string.

Missed check: `agent_materialization` covers whitespace and a quoted single-segment key, but not a quoted segment containing dots.

## Void readings

The proposed `--custom` twin did not survive its control. With only the interactive editor replaced by a no-op, both the explicit and picker entry points rebased Vanilla to `builder` and produced configured arguments.

Explicit path:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); g=m["select_plan"].__globals__; c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); g["customize"]=lambda *a,**k: None; p=m["select_plan"](c,"codex","vanilla",True); print("entry=explicit preset=%s mode=%s projected_empty=%s" % (p["preset"],p["mode"],m["project_args"](p,False)==[]))'
```

```text
entry=explicit preset=vanilla mode=builder projected_empty=False
```

Picker path:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); g=m["select_plan"].__globals__; c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); g["customize"]=lambda *a,**k: None; g["pick_mode_and_preset"]=lambda *a,**k:("vanilla",True,m["SWE_MODE"]); p=m["select_plan"](c,"codex",None,False); print("entry=picker preset=%s mode=%s projected_empty=%s" % (p["preset"],p["mode"],m["project_args"](p,False)==[]))'
```

```text
entry=picker preset=vanilla mode=builder projected_empty=False
```

I also dropped the marker-recovery candidate. `run_contract` enforces one raw marker in what it emits, while `extract_review_plan_v1` deliberately scans a larger surrounding transcript for decodable records. One valid record plus a malformed textual mention parses; two valid records are refused:

```text
markers=2 parsed=True
```

```text
markers=2
REFUSED: the contract carries 2 ReviewPlan/v1 records; exactly one is the plan, and this cannot tell which
```

## Denominator

Executed:

- All 12 shipped dry-runs: 2 hosts × `balanced`, `deep-review`, `fast-batch`, `solo`, `vanilla`, `session-distill`; all exited 0.
- Direct paired probes over `build_plan`, `run_contract`, `project_args`, `print_summary`, `effective_review`, composable review parsing, save/render/reload, marker extraction, plan reconstruction, receipt verification, and receipt folding.
- All four `-c`/`--config` spellings.
- Empty inactive review-arm render/reload: the inactive arm remained present; selecting a missing active arm still refused.
- `gates/check_parity.py --list` to identify each existing check’s intended surface.

The full parity umbrella was not run because this was a read-only review.

Not examined: host CLI execution; access-control posture; `compose/corpus-state.py`; the wizard trial load; writable on-disk save/receipt flows; full parity-gate execution.
tokens used
354,505
