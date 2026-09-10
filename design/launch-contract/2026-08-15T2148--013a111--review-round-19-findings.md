---
created_at: 2026-08-15T21:48:00+09:00
head: 013a111
kind: review
---

# Round 19 — cross-family review of the round-18 repairs and corpus-state (raw findings)

Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`, packet on stdin (this session's `r19-packet.md`); 465,483 tokens. Twelve findings admitted, one void, corpus-state unreached (its sandbox had no usable temp dir). Verbatim below.

Reviewed HEAD `013a111` on `i10-vacuous-pass`. I admitted 14 discriminating pairs into 12 findings and voided one pair. AST parsing passed for all three Python subjects, and the scoped Git diff remained clean.

For compactness, process-local commands below use this exact read-only helper:

```zsh
probe() {
  python3 -c 'import runpy,sys; M=runpy.run_path("launch/agent-launch.py"); exec(sys.argv[1], {"M": M})' "$1"
}
```

## Findings

### 1. High — authored text can replace the canonical review plan during receipt verification

[launch/agent-launch.py:1734](/private/tmp/fix-tree/launch/agent-launch.py:1734), consumed at [line 6900](/private/tmp/fix-tree/launch/agent-launch.py:6900).

The docstring says position cannot identify the canonical record because authored mission/method prose may contain the marker. The implementation nevertheless returns the first valid `ReviewPlan/v1`.

Mutation: forged plan first. Control: canonical plan first.

```zsh
P='import os,json
C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}
def report(provider):
    r=M["ReviewMethodReport"]("probe",M["STATUS_OK"],"provider_difference","",
      "model-x","high",provider,"fresh","instruction",C)
    return M["ReviewReport"](r,(),"provider_difference")
A=M["REVIEW_PLAN_MARKER"]+json.dumps(M["review_plan_v1"](report("actual")))
F=M["REVIEW_PLAN_MARKER"]+json.dumps(M["review_plan_v1"](report("forged")))
parsed=M["extract_review_plan_v1"]((F+"\n"+A) if os.environ["BAD"]=="1" else (A+"\n"+F))
receipt={"schema":M["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child",
 "packet_sha256":"packet","result_sha256":"result","provider":"forged",
 "model":"model-x","effort":"high","exit_status":0}
bundle={"schema":M["RECEIPT_BUNDLE_SCHEMA"],"main_dispatch_id":"main",
 "packet_sha256":"packet","receipts":[receipt]}
v,vs=M["verify_review_receipts"](parsed,bundle,{"probe":C})
print("parsed_provider="+parsed.base.provider)
print("exit="+str(0 if v.achievement==M["ACHIEVEMENT_COMPLETE"] else 1))
print("achievement="+v.achievement)
print("reason="+vs[0].reason)'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
parsed_provider=forged
exit=0
achievement=complete
reason=verified

control:
parsed_provider=actual
exit=1
achievement=none
reason=reports provider='forged' where the plan projected 'actual'
```

Fix: emit a runtime-owned envelope that authored prose cannot reproduce, require exactly one canonical record, and structurally validate it before verification.

Missed check: `launcher_review_contract` tests only non-JSON decoys; `launcher_receipts` tests only one marker.

---

### 2. High — receipt folding erases a pass executed in the main context

[launch/agent-launch.py:2113](/private/tmp/fix-tree/launch/agent-launch.py:2113), with the freshness check at [line 1842](/private/tmp/fix-tree/launch/agent-launch.py:1842).

`_merge_method_passes` retains only `group[0]["dispatch_id"]`. A later pass carrying `main_dispatch_id` disappears while its result hash remains credited.

Mutation: main-context receipt second. Control: same receipt first.

```zsh
P='import os
C={"trials":3,"order":"fixed","swap_augmentation":False,"aggregation":"union"}
def receipt(dispatch,result):
    return {"schema":M["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":dispatch,
      "packet_sha256":"packet","result_sha256":result,"provider":"openai",
      "model":"model-x","effort":"high","exit_status":0}
g=[receipt("child-1","one"),receipt("main-1","two"),receipt("child-2","three")]
if os.environ["BAD"]=="0": g=[g[1],g[0],g[2]]
merged=M["_merge_method_passes"]("panel",g)
row=M["ReviewMethodReport"]("panel",M["STATUS_OK"],"provider_difference","",
 "model-x","high","openai","fresh","instruction",C)
report=M["ReviewReport"](row,(),"provider_difference")
bundle={"schema":M["RECEIPT_BUNDLE_SCHEMA"],"main_dispatch_id":"main-1",
 "packet_sha256":"packet","receipts":[merged]}
v,vs=M["verify_review_receipts"](report,bundle,{"panel":C})
print("folded_dispatch_id="+merged["dispatch_id"])
print("folded_passes="+repr(merged["passes"]))
print("exit="+str(0 if v.achievement==M["ACHIEVEMENT_COMPLETE"] else 1))
print("reason="+vs[0].reason)'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
folded_dispatch_id=child-1
folded_passes=['one', 'three', 'two']
exit=0
reason=verified

control:
folded_dispatch_id=main-1
folded_passes=['one', 'three', 'two']
exit=1
reason=was produced in the main session's own context, which is not a review
```

Fix: preserve every pass’s dispatch ID and validate each before folding: nonempty, distinct, and not `main_dispatch_id`.

Missed check: `launcher_receipt_adapters` checks result-hash distinctness but not every folded dispatch identity.

---

### 3. High — `ReviewPlan.controls` is mandatory to parse but ignored when setting the audit bar

The field claims to carry the declaration read by “the ReviewPlan/v1 row … and the verifier” at [line 1497](/private/tmp/fix-tree/launch/agent-launch.py:1497). It is serialized at [line 1782](/private/tmp/fix-tree/launch/agent-launch.py:1782), but verification recomputes controls from the current registry at [line 6867](/private/tmp/fix-tree/launch/agent-launch.py:6867).

A registry change after launch can therefore lower the recorded three-pass bar to one pass:

```zsh
P='import os
plan={"trials":3,"order":"randomized","swap_augmentation":True,"aggregation":"majority"}
registry={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"} if os.environ["BAD"]=="1" else plan
row=M["ReviewMethodReport"]("probe",M["STATUS_OK"],"provider_difference","",
 "model-x","high","openai","fresh","instruction",plan)
report=M["ReviewReport"](row,(),"provider_difference")
receipt={"schema":M["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child",
 "packet_sha256":"packet","result_sha256":"one","provider":"openai",
 "model":"model-x","effort":"high","exit_status":0}
bundle={"schema":M["RECEIPT_BUNDLE_SCHEMA"],"main_dispatch_id":"main",
 "packet_sha256":"packet","receipts":[receipt]}
v,vs=M["verify_review_receipts"](report,bundle,{"probe":registry})
print("registry_controls="+repr(registry))
print("exit="+str(0 if v.achievement==M["ACHIEVEMENT_COMPLETE"] else 1))
print("reason="+vs[0].reason)'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
registry_controls={'trials': 1, 'order': 'fixed', 'swap_augmentation': False, 'aggregation': 'union'}
exit=0
reason=verified

control:
registry_controls={'trials': 3, 'order': 'randomized', 'swap_augmentation': True, 'aggregation': 'majority'}
exit=1
reason=evidences fewer than the 3 requested passes
```

Conversely, an older `ReviewPlan/v1` without this presently unused field crashes:

```zsh
P='import os,json
C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}
r=M["ReviewMethodReport"]("probe",M["STATUS_OK"],"provider_difference","",
 "model-x","high","openai","fresh","instruction",C)
data=M["review_plan_v1"](M["ReviewReport"](r,(),"provider_difference"))
if os.environ["BAD"]=="1": data["base"].pop("controls")
try:
    x=M["extract_review_plan_v1"]("prefix "+M["REVIEW_PLAN_MARKER"]+json.dumps(data))
    print("exit=0\nrestored="+str(x is not None))
except Exception as e:
    print("exit=1\nexception="+type(e).__name__+": "+str(e))'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
exit=1
exception=KeyError: 'controls'

control:
exit=0
restored=True
```

Fix: preserve registry authority but add a descriptor fingerprint/snapshot to the plan and fail on mismatch. Either keep missing `controls` compatible within v1 or introduce a new schema version.

Missed checks: `launcher_receipts` always builds plan and registry together; `launcher_review_contract` round-trips only current-schema rows.

---

### 4. High — forwarded collision detection both misses real overrides and refuses unrelated supported keys

[launch/agent-launch.py:6525](/private/tmp/fix-tree/launch/agent-launch.py:6525), used at [line 7041](/private/tmp/fix-tree/launch/agent-launch.py:7041).

First, attached `--config=…` is accepted by installed `codex-cli 0.146.0` but is not parsed by `forwarded_collisions`.

Mutation:

```zsh
python3 launch/agent-launch.py --config launch/agent-launch.toml \
  --no-tui --preset balanced --yes --dry-run codex -- \
  '--config=model_reasoning_effort="low"'
```

Control:

```zsh
python3 launch/agent-launch.py --config launch/agent-launch.toml \
  --no-tui --preset balanced --yes --dry-run codex -- \
  -c 'model_reasoning_effort="low"'
```

```text
mutation:
exit=0
projected=model_reasoning_effort="xhigh"
forwarded=--config=model_reasoning_effort="low"
contract contains: a projected option cannot be overridden

control:
exit=2
agent-launch: forwarded argument(s) -c model_reasoning_effort would override what this launch projects and the contract describes...
```

Second, line 6561 compares only the top-level root, so adding a separate supported dynamic agent is refused as though it overwrote the projected frontier/workhorse/sweep agents. Installed Codex accepted the same reviewer registration:

```text
codex -c 'agents.reviewer.config_file="/Users/kangmin/.codex/agents/reviewer.toml"' --version
exit=0
codex-cli 0.146.0
```

Mutation:

```zsh
python3 launch/agent-launch.py --config launch/agent-launch.toml \
  --no-tui --preset balanced --yes --dry-run codex -- \
  -c 'agents.reviewer.config_file="/Users/kangmin/.codex/agents/reviewer.toml"'
```

Control:

```zsh
python3 launch/agent-launch.py --config launch/agent-launch.toml \
  --no-tui --preset balanced --yes --dry-run codex -- \
  -c notice.hide_full_access_warning=true
```

```text
mutation:
exit=2
forwarded argument(s) -c agents.reviewer.config_file would override...

control:
exit=0
forwarded=['-c', 'notice.hide_full_access_warning=true']
```

Fix: normalize separate and attached config syntax plus `--enable/--disable`; compare exact owned keys or genuinely overlapping nested prefixes rather than every key sharing `agents`.

Missed check: `agent_materialization` covers separated `-c` only and treats any `agents.*` key as a collision.

---

### 5. Medium — delegation-off contracts still promise a child-agent fallback

[launch/agent-launch.py:6307](/private/tmp/fix-tree/launch/agent-launch.py:6307) versus [delegation_clause at line 6405](/private/tmp/fix-tree/launch/agent-launch.py:6405).

The repaired tier clause truthfully says no child binding is projected, but `_cross_review_route` still instructs the session to fall back “via the configured child agents.”

Mutation/control differ only in delegation:

```zsh
P='import os,pathlib,copy
cfg=M["load_config"](pathlib.Path("launch/agent-launch.toml"))
cfg["presets"]["probe"]=copy.deepcopy(cfg["presets"]["solo"])
cfg["presets"]["probe"]["delegation"]=os.environ["BAD"]=="0"
cfg["presets"]["probe"]["review_setup"]="ultracode"
cfg["presets"]["probe"]["review_family"]="cross"
plan=M["build_plan"](cfg,"claude","probe")
M["validate_review_setup"](plan)
argv=M["project_args"](plan,materialize_agents=False)
contract=M["run_contract"](plan)
print("delegation="+str(plan["delegation"]))
print("agents_projected="+str("--agents" in argv))
print("says_delegation_off="+str("Delegation=off" in contract))
print("says_child_fallback="+str("via the configured child agents" in contract))'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
delegation=False
agents_projected=False
says_delegation_off=True
says_child_fallback=True

control:
delegation=True
agents_projected=True
says_delegation_off=False
says_child_fallback=True
```

Fix: condition the native fallback sentence on delegation. With delegation off, state that no child fallback is available.

Missed check: `launcher_delegation_clause` checks the tier clause but not route prose. `review_matrix` currently pins the contradictory sentence.

---

### 6. Medium — randomized and swap controls are not audited when `trials=1`

[launch/agent-launch.py:1885](/private/tmp/fix-tree/launch/agent-launch.py:1885).

The parser permits non-panel methods with one trial, randomized order, and swap augmentation. Seed and swap checks are incorrectly nested under `required_passes > 1`.

Mutation: one trial. Control: two trials; the same two hashes satisfy pass count.

```zsh
P='import os
n=1 if os.environ["BAD"]=="1" else 2
C={"trials":n,"order":"randomized","swap_augmentation":True,"aggregation":"majority"}
r=M["ReviewMethodReport"]("probe",M["STATUS_OK"],"provider_difference","",
 "model-x","high","openai","fresh","instruction",C)
receipt={"schema":M["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child",
 "packet_sha256":"packet","result_sha256":"one","provider":"openai",
 "model":"model-x","effort":"high","exit_status":0,"passes":["one","two"]}
bundle={"schema":M["RECEIPT_BUNDLE_SCHEMA"],"main_dispatch_id":"main",
 "packet_sha256":"packet","receipts":[receipt]}
v,vs=M["verify_review_receipts"](M["ReviewReport"](r,(),"provider_difference"),bundle,{"probe":C})
print("exit="+str(0 if v.achievement==M["ACHIEVEMENT_COMPLETE"] else 1))
print("achievement="+v.achievement)
print("reason="+vs[0].reason)'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
exit=0
achievement=complete
reason=verified

control:
exit=1
achievement=none
reason=omits the ordering seed its randomized order requires, so the panel controls are unproven
```

Fix: keep only pass-count validation conditional; audit every independently declared order/swap control regardless of trial count.

Missed check: `launcher_receipts` covers multi-pass randomized and fixed-order cases, not the valid one-trial randomized/swap combination.

---

### 7. Medium — receipt evidence is selected by offer order rather than the resolved review host

[launch/agent-launch.py:6888](/private/tmp/fix-tree/launch/agent-launch.py:6888). Mechanism resolution correctly matches the host at [line 1332](/private/tmp/fix-tree/launch/agent-launch.py:1332); verification does not.

Mutation: Claude offer first, then Codex. Control: Codex first. The plan and receipt both identify the OpenAI/Codex seat and contain `codex_trace`.

```text
mutation output:
Review achievement (achievement=none [0/1 evidenced], achieved_grade=UNKNOWN_UNTIL_RECEIPTS, availability=projected — launch-time projection, unchanged by verification)
  lens: PROPOSED — reports none of claude_trace, which this capability's offer declares it returns — a dispatch that reported nothing is not evidenced
exit=1

control output:
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=provider_difference, availability=projected — launch-time projection, unchanged by verification)
  lens: ACHIEVED/provider_difference — verified
exit=0
```

The two process-local `verify_receipts_command` commands used identical plan, receipt, method and capability objects; only the two offer dictionaries were reversed:

```zsh
ORDER=claude-first probe "$OFFER_ORDER_PROBE"
ORDER=codex-first probe "$OFFER_ORDER_PROBE"
```

Here `OFFER_ORDER_PROBE` constructed two valid `exec-stdio-v1` offers for operation `review`, patched only the function’s file/config inputs, and invoked `verify_receipts_command`; no adjudication logic was replaced.

Fix: parse the plan first, derive the host from the row’s uniquely mapped provider, and select the offer matching both operation and host.

Missed check: `launcher_receipts`’ fixture has only one matching offer; its helper repeats the same first-operation lookup.

---

### 8. Medium — merely reselecting the current review setup makes a temporary family fallback permanent

[launch/agent-launch.py:5158](/private/tmp/fix-tree/launch/agent-launch.py:5158), recorded by [apply_review_plan at line 3337](/private/tmp/fix-tree/launch/agent-launch.py:3337).

On a single-host machine, `plan["review_family"]` is the effective `same`; `review_family_requested` remains `cross`. Customize passes the effective value into `legacy_review_plan`, overwriting the request. The save path then faithfully saves the already-corrupted value.

Mutation: `review → none → start`. Control: `start`.

```zsh
P='import os,pathlib
cfg=M["load_config"](pathlib.Path("launch/agent-launch.toml"))
cfg["hosts"].pop("claude",None); cfg["backends"].pop("claude",None)
plan=M["build_plan"](cfg,"codex","solo")
print("before="+repr((plan["review_family"],plan["review_family_requested"])))
answers=iter(["review","none","start"] if os.environ["BAD"]=="1" else ["start"])
g=M["customize"].__globals__; old=g["choose"]; g["choose"]=lambda *a,**k: next(answers)
try: M["customize"](plan,cfg,pathlib.Path("launch/agent-launch.toml"))
finally: g["choose"]=old
saved=M["preset_from_plan"](plan,cfg,"saved")[0]
print("after="+repr((plan["review_family"],plan["review_family_requested"])))
print("saved_review_family="+repr(saved["review_family"]))
print("contract_discloses_fallback="+str("configured cross" in M["run_contract"](plan)))'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
before=('same', 'cross')
after=('same', 'same')
saved_review_family='same'
contract_discloses_fallback=False

control:
before=('same', 'cross')
after=('same', 'cross')
saved_review_family='cross'
contract_discloses_fallback=True
```

Fix: pass `plan["review_family_requested"]` or `plan["review_plan"].legacy_family` into `legacy_review_plan`, then derive the effective family.

Missed check: `cross_family` calls `apply_review_plan` with the intact plan but never traverses Customize’s legacy lowering path.

---

### 9. Medium — a slot value can inject the controls clause that template validation refuses

The static refusal is at [line 1174](/private/tmp/fix-tree/launch/agent-launch.py:1174). The formatted-body guard at [line 1378](/private/tmp/fix-tree/launch/agent-launch.py:1378) checks only the severity marker.

Mutation: a perspective contains `; controls trials=1`. Control: ordinary perspective.

```text
mutation:
exit=0
controls_clause_count=2
panel: ... perspectives correctness; controls trials=1, security ...
  [...; controls trials=3, order=randomized, swap_augmentation=true, aggregation=majority]

control:
exit=0
controls_clause_count=1
panel: ... perspectives correctness, security ...
  [...; controls trials=3, order=randomized, swap_augmentation=true, aggregation=majority]
```

Commands:

```zsh
BAD=1 probe 'import dataclasses,pathlib
cfg=M["load_config"](pathlib.Path("launch/agent-launch.toml"))
x=M["load_review_methods"](cfg)["panel"]
x=dataclasses.replace(x,perspectives=("correctness; controls trials=1","security"))
b=M["ReviewBinding"]("openai","codex","gpt-5.6-sol","max")
line=M["render_review_method"](x,M["derive_review_mechanism"](x,b,cfg))
print("exit=0\ncontrols_clause_count="+str(line.count("; controls "))+"\n"+line)'

BAD=0 probe 'import dataclasses,pathlib
cfg=M["load_config"](pathlib.Path("launch/agent-launch.toml"))
x=M["load_review_methods"](cfg)["panel"]
x=dataclasses.replace(x,perspectives=("correctness","security"))
b=M["ReviewBinding"]("openai","codex","gpt-5.6-sol","max")
line=M["render_review_method"](x,M["derive_review_mechanism"](x,b,cfg))
print("exit=0\ncontrols_clause_count="+str(line.count("; controls "))+"\n"+line)'
```

Fix: apply both core-marker checks to the fully formatted body; optionally constrain perspective labels at parse time.

Missed checks: `launcher_review_schema` tests a literal template marker; `launcher_review_methods` tests formatted severity injection but not formatted controls injection.

---

### 10. Medium — a misspelled tier-override host is silently ignored

[launch/agent-launch.py:3397](/private/tmp/fix-tree/launch/agent-launch.py:3397).

Leaf override keys are closed, but the host keys are not validated. Since the CLI accepts only `codex` and `claude`, `codxe` can never become active.

Mutation/control:

```zsh
P='import os,pathlib,copy
cfg=M["load_config"](pathlib.Path("launch/agent-launch.toml"))
cfg["presets"]["probe"]=copy.deepcopy(cfg["presets"]["solo"])
host="codxe" if os.environ["BAD"]=="1" else "codex"
cfg["presets"]["probe"]["tier_overrides"]={host:{"workhorse":{"model":"gpt-probe"}}}
plan=M["build_plan"](cfg,"codex","probe")
print("exit=0\noverride_host="+host+"\nworkhorse_model="+plan["tiers"]["workhorse"]["model"])'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
exit=0
override_host=codxe
workhorse_model=gpt-5.6-terra

control:
exit=0
override_host=codex
workhorse_model=gpt-probe
```

Fix: validate every `tier_overrides` host against the supported/configured host set before selecting the active host.

Missed check: `profile_validation` checks misspelled keys inside a host/tier override but not the host key itself.

---

### 11. Medium — saving a valid active arm raw-crashes on malformed nested data in the inactive arm

[launch/agent-launch.py:4742](/private/tmp/fix-tree/launch/agent-launch.py:4742), called outside the save error boundary at [line 4918](/private/tmp/fix-tree/launch/agent-launch.py:4918).

The renderer converts a non-table outer arm into `LaunchError`, but blindly calls `.items()` on `base`, `methods`, and method bindings.

Mutation: inactive `codex.methods` is a string. Control: empty table.

```zsh
P='import os,pathlib,copy
cfg=M["load_config"](pathlib.Path("launch/agent-launch.toml"))
cfg["presets"]["probe"]=copy.deepcopy(cfg["presets"]["balanced"])
cfg["presets"]["probe"]["review"]["hosts"]["codex"]["methods"]="not-a-table" if os.environ["BAD"]=="1" else {}
plan=M["build_plan"](cfg,"claude","probe")
f,o,r=M["preset_from_plan"](plan,cfg,"saved")
try:
    text=M["render_preset_block"]("saved",f,o,r)
    print("exit=0\nsaved_has_codex_arm="+str("[presets.saved.review.hosts.codex.base]" in text))
except Exception as e:
    print("exit=1\nexception="+type(e).__name__+": "+str(e))'
BAD=1 probe "$P"
BAD=0 probe "$P"
```

```text
mutation:
exit=1
exception=AttributeError: 'str' object has no attribute 'items'

control:
exit=0
saved_has_codex_arm=True
```

Fix: structurally validate inactive arms’ `base`, `methods`, and each binding before serialization, raising an arm-anchored `LaunchError`.

Missed check: `launcher_review_save` proves a well-formed inactive arm survives, but does not exercise the raw shape the deferred parser intentionally preserves.

---

### 12. Medium — valid JSON inside `passes` can escape as `TypeError`

[launch/agent-launch.py:1887](/private/tmp/fix-tree/launch/agent-launch.py:1887).

The verifier builds a set before checking that pass identifiers are nonempty strings. Nested arrays raise; truthy numbers are accepted as pass evidence.

Mutation: `["p1", ["nested"]]`. Control: `["p1", ""]`.

```text
mutation:
exit=1
exception=TypeError: cannot use 'list' as a set element (unhashable type: 'list')

control:
exit=1
achievement=none
reason=evidences fewer than the 2 requested passes
```

Fix: first require a list of nonempty strings, then deduplicate it. Return a named receipt defect for every malformed value.

Missed check: `launcher_receipts` checks insufficient string hashes but not other valid JSON element types.

## Void readings

I dropped the candidate “an advisory service-tier row must never be credited.” The tier request is dropped, but the review itself still runs on the effective default seat; both cases correctly adjudicated the review identically.

```text
mutation:
status=ADVISORY
achievement=complete
reason=verified

control:
status=OK
achievement=complete
reason=verified
```

## Corpus-state evidence limitation

I read `list`, `project`, `rollback`, `record-apply`, the installer callsites, and the new self-test, but admitted no `corpus-state.py` finding. Your rule requires a real disposable Git repository and disposable deployment/status directories. This environment could not create that fixture:

```text
$ python3 compose/corpus-state.py --self-test
exit=1
FileNotFoundError: [Errno 2] No usable temporary directory found in [...]
```

I did not substitute an in-memory fake and present it as equivalent evidence. `list --repo .` was the only executable corpus command reached; it returned one unavailable version, which is not a mutation/control pair.

Registered denominator: `gates/check_parity.py --list` reported 61 checks. Relevant missed checks were `launcher_review_contract`, `launcher_delegation_clause`, `launcher_receipts`, `launcher_receipt_adapters`, `launcher_review_save`, `launcher_review_methods`, `profile_validation`, `review_matrix`, `agent_materialization`, and `cross_family`.

Not examined: corpus-state mutation behavior at the required disposable-repository evidence bar; the wizard’s `_trial_registration` path, which also needs a disposable tree; actual external reviewer/backend execution; full TUI rendering beyond the pure Customize loop; and scope-excluded surfaces.
tokens used
465,483
Reviewed HEAD `013a111` on `i10-vacuous-pass`. I admitted 14 discriminating pairs into 12 findings and voided one pair. AST parsing passed for all three Python subjects, and the scoped Git diff remained clean.

For compactness, process-local commands below use this exact read-only helper:

```zsh
probe() {
  python3 -c 'import runpy,sys; M=runpy.run_path("launch/agent-launch.py"); exec(sys.argv[1], {"M": M})' "$1"
}
```

