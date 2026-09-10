---
created_at: 2026-08-15T19:41:53+09:00
head: b773ccc
kind: review
---

# Round 18 — cross-family review of the launch contract (raw findings)

Verbatim from the reviewer, kept because it carries the reproduction command AND
the control for each finding. Two are already closed (see the handoff beside this
file); the rest are open. The full transcript, including the exec traces these
were derived from, was 1MB of session scratchpad and is not preserved — what a
later reader needs is the paired commands, which are here.

Reviewer: gpt-5.6-sol at ultra, read-only, fresh context. Packet asked for
discriminating controls and a denominator; the "Void readings" section at the end
is the reviewer dropping its own candidates that failed their controls.

---

## Findings

### 1. High — `solo` requests no review but tells the session to run cross-family review

[agent-launch.toml:225](/private/tmp/fix-tree/launch/agent-launch.toml:225), [agent-launch.py:6049](/private/tmp/fix-tree/launch/agent-launch.py:6049), [agent-launch.py:6145](/private/tmp/fix-tree/launch/agent-launch.py:6145)

The preset says `review_setup="none"` and `effective_review` resolves no route. `_cross_review_route` nevertheless emits “run EVERY review route” because it lacks a `none` branch.

Commands:

```sh
probe() {
  PROBE_FAMILY="$1" python3 -c '
import copy,json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
p=copy.deepcopy(c["presets"]["solo"])
p["review_family"]=os.environ["PROBE_FAMILY"]
c["presets"]["probe"]=p
plan=m["build_plan"](c,"codex","probe")
contract=m["run_contract"](plan)
effective,_,_=m["effective_review"](plan)
print(json.dumps({
  "family":os.environ["PROBE_FAMILY"],
  "setup":plan["review_setup"],
  "effective":effective,
  "contract_says_no_route":"No additional review route requested" in contract,
  "contract_says_run_every":"run EVERY review route" in contract
},sort_keys=True))
'; echo "exit=$?"
}
probe cross   # mutation
probe same    # control
```

Outputs:

```text
mutation:
{"contract_says_no_route": false, "contract_says_run_every": true, "effective": [], "family": "cross", "setup": "none"}
exit=0

control:
{"contract_says_no_route": true, "contract_says_run_every": false, "effective": [], "family": "same", "setup": "none"}
exit=0
```

Fix: short-circuit `review_setup == "none"` before family routing and render only the setup’s no-review contract.

Missed check: `review_matrix` covers these cells but its golden records the defect at [review-matrix.json:178](/private/tmp/fix-tree/gates/goldens/review-matrix.json:178).

### 2. High — forwarded model and effort values are carried but absent from the contract

[agent-launch.py:6165](/private/tmp/fix-tree/launch/agent-launch.py:6165), [agent-launch.py:6307](/private/tmp/fix-tree/launch/agent-launch.py:6307), [agent-launch.py:6752](/private/tmp/fix-tree/launch/agent-launch.py:6752)

The contract is rendered from configured defaults before forwarded arguments are appended. Its generic “may supersede” warning does not name the actual second model/effort pair in argv.

Commands:

```sh
probe() {
  PROBE_MODE="$1" python3 -c '
import json,os,subprocess,sys
changed=os.environ["PROBE_MODE"]=="changed"
cases=(
 ("codex",["--model","gpt-override" if changed else "gpt-5.6-sol",
           "-c","model_reasoning_effort=\"low\"" if changed else "model_reasoning_effort=\"xhigh\""]),
 ("claude",["--model","claude-override" if changed else "claude-opus-5",
            "--effort","low" if changed else "xhigh"])
)
for host,forward in cases:
 r=subprocess.run([sys.executable,"launch/agent-launch.py","--no-tui",
   "--preset","balanced","--yes","--dry-run",host,"--",*forward],
   capture_output=True,text=True)
 a=json.loads(r.stdout.splitlines()[-1])
 if host=="codex":
  c=json.loads(next(x.split("=",1)[1] for x in a
                    if x.startswith("developer_instructions=")))
  efforts=[x.split("=",1)[1].strip("\"") for x in a
           if x.startswith("model_reasoning_effort=")]
 else:
  c=a[a.index("--append-system-prompt")+1]
  efforts=[a[i+1] for i,x in enumerate(a[:-1]) if x=="--effort"]
 models=[a[i+1] for i,x in enumerate(a[:-1]) if x=="--model"]
 print(json.dumps({"host":host,"exit":r.returncode,
   "contract_main":c.split(";",1)[0],"argv_models":models,
   "argv_efforts":efforts,
   "contract_matches_last":f"({models[-1]}/{efforts[-1]})" in c},sort_keys=True))
'; echo "exit=$?"
}
probe changed   # mutation
probe equal     # control
```

Outputs:

```text
mutation:
{"argv_efforts": ["xhigh", "low"], "argv_models": ["gpt-5.6-sol", "gpt-override"], "contract_main": "LaunchPlan: main=helm (gpt-5.6-sol/xhigh)", "contract_matches_last": false, "exit": 0, "host": "codex"}
{"argv_efforts": ["xhigh", "low"], "argv_models": ["claude-opus-5", "claude-override"], "contract_main": "LaunchPlan: main=helm (claude-opus-5/xhigh)", "contract_matches_last": false, "exit": 0, "host": "claude"}
exit=0

control:
{"argv_efforts": ["xhigh", "xhigh"], "argv_models": ["gpt-5.6-sol", "gpt-5.6-sol"], "contract_main": "LaunchPlan: main=helm (gpt-5.6-sol/xhigh)", "contract_matches_last": true, "exit": 0, "host": "codex"}
{"argv_efforts": ["xhigh", "xhigh"], "argv_models": ["claude-opus-5", "claude-opus-5"], "contract_main": "LaunchPlan: main=helm (claude-opus-5/xhigh)", "contract_matches_last": true, "exit": 0, "host": "claude"}
exit=0
```

Fix: reject configured-launch forwards that collide with launcher-owned model, effort, contract, or child-binding keys, or parse those overrides before rendering. Rejection is safer because arbitrary backend syntax cannot be reconstructed reliably.

Missed check: `agent_materialization` verifies only that forwarded arguments are last and that a generic warning exists.

### 3. High — configured launches discard valid backend `passthrough_args`

[agent-launch.py:2433](/private/tmp/fix-tree/launch/agent-launch.py:2433), [agent-launch.py:6680](/private/tmp/fix-tree/launch/agent-launch.py:6680), [agent-launch.py:6694](/private/tmp/fix-tree/launch/agent-launch.py:6694), [agent-launch.py:6752](/private/tmp/fix-tree/launch/agent-launch.py:6752)

`resolve_backend` returns the configured backend arguments. The bare branch carries them; the configured branch reconstructs argv from `project_args` and silently drops them.

Commands:

```sh
probe() {
  PROBE_MODE="$1" python3 -c '
import contextlib,importlib.util,io,json,os,pathlib,sys,tomllib
s=importlib.util.spec_from_file_location("al_passthrough","launch/agent-launch.py")
m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m)
c=tomllib.loads(pathlib.Path("launch/agent-launch.toml").read_text())
c["backends"]["codex"]={"command":sys.executable,
                        "passthrough_args":["BACKEND-DEFAULT","alpha"]}
m.load_config=lambda _:c
if os.environ["PROBE_MODE"]=="managed":
 o=io.StringIO()
 with contextlib.redirect_stdout(o):
  rc=m.main(["--no-tui","--preset","solo","--yes","--dry-run","codex"])
 a=json.loads(o.getvalue().splitlines()[-1])
else:
 seen={}
 class Stop(Exception): pass
 def fake(command,args,env=None):
  seen.update(command=command,args=args); raise Stop
 m.exec_backend=fake
 try: m.main(["--no-tui","codex"])
 except Stop: pass
 a=[seen["command"],*seen["args"]]; rc=0
print(json.dumps({"mode":os.environ["PROBE_MODE"],
 "configured_passthrough":["BACKEND-DEFAULT","alpha"],
 "carried_sequence":any(a[i:i+2]==["BACKEND-DEFAULT","alpha"]
                        for i in range(len(a)-1)),"rc":rc},sort_keys=True))
'; echo "exit=$?"
}
probe managed   # mutation
probe bare      # control
```

Outputs:

```text
mutation:
{"carried_sequence": false, "configured_passthrough": ["BACKEND-DEFAULT", "alpha"], "mode": "managed", "rc": 0}
exit=0

control:
{"carried_sequence": true, "configured_passthrough": ["BACKEND-DEFAULT", "alpha"], "mode": "bare", "rc": 0}
exit=0
```

Fix: one argv assembler should combine backend defaults, plan projection, and user-forwarded tail for every launch path.

Missed checks: `backend_dispatch` tests passthrough only on the direct branch; `vanilla_mode` hardcodes `[backend]`, preserving the divergence.

### 4. High — same-family deep review on Claude names the Codex route

[agent-launch.py:407](/private/tmp/fix-tree/launch/agent-launch.py:407), [agent-launch.py:431](/private/tmp/fix-tree/launch/agent-launch.py:431), [agent-launch.py:6021](/private/tmp/fix-tree/launch/agent-launch.py:6021), [agent-launch.py:4366](/private/tmp/fix-tree/launch/agent-launch.py:4366)

The setup description says the deep mechanism follows the review host. The legacy implementation hardwires `ultracode` to the Codex capability even when same-family review lands on Claude.

Commands:

```sh
probe() {
  PROBE_HOST="$1" python3 -c '
import copy,json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
host=os.environ["PROBE_HOST"]
p=copy.deepcopy(c["presets"]["solo"])
p.pop("review",None)
p.update({"review_setup":"ultracode","review_family":"same","delegation":True})
c["presets"]["probe"]=p
contract=m["run_contract"](m["build_plan"](c,host,"probe"))
actual="claude" if "Claude workflow" in contract else \
       ("codex" if "Codex" in contract else "unnamed")
print(json.dumps({"family":"same","launch_host":host,
 "expected_review_host":host,"actual_named_review_host":actual,
 "matches_expected":actual==host},sort_keys=True))
'; echo "exit=$?"
}
probe claude   # mutation
probe codex    # control
```

Outputs:

```text
mutation:
{"actual_named_review_host": "codex", "expected_review_host": "claude", "family": "same", "launch_host": "claude", "matches_expected": false}
exit=0

control:
{"actual_named_review_host": "codex", "expected_review_host": "codex", "family": "same", "launch_host": "codex", "matches_expected": true}
exit=0
```

Fix: derive the deep capability, description, command, and availability from the effective review host.

Missed check: `same_family` at [check_parity.py:8119](/private/tmp/fix-tree/gates/check_parity.py:8119) explicitly asserts the defective Claude-to-Codex combination.

### 5. High — cross-family slash review renders mutually exclusive instructions

[agent-launch.py:386](/private/tmp/fix-tree/launch/agent-launch.py:386), [agent-launch.py:443](/private/tmp/fix-tree/launch/agent-launch.py:443), [agent-launch.py:2569](/private/tmp/fix-tree/launch/agent-launch.py:2569), [agent-launch.py:6060](/private/tmp/fix-tree/launch/agent-launch.py:6060), [agent-launch.py:6110](/private/tmp/fix-tree/launch/agent-launch.py:6110)

`effective_review` correctly classifies slash review as a same-family floor. The renderer first commands every route to run cross-family, then says this route cannot run cross-family.

Commands:

```sh
probe() {
  PROBE_FAMILY="$1" python3 -c '
import copy,json,os,pathlib,re,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
p=copy.deepcopy(c["presets"]["solo"])
p.pop("review",None)
p["review_setup"]="slash-review"
p["review_family"]=os.environ["PROBE_FAMILY"]
c["presets"]["probe"]=p
plan=m["build_plan"](c,"claude","probe")
contract=m["run_contract"](plan)
effective,_,floor=m["effective_review"](plan)
print(json.dumps({"effective":effective,"floor":floor,
 "cross_claim":"run EVERY review route on OpenAI/Codex" in contract,
 "same_family_claim":"cannot be dispatched cross-family" in contract,
 "contract_header":re.search(r"Review family=.*?Review setup=[^:]+:",
                             contract).group(0)},sort_keys=True))
'; echo "exit=$?"
}
probe cross   # mutation
probe same    # control
```

Outputs:

```text
mutation:
{"contract_header": "Review family=cross. Review setup=slash-review:", "cross_claim": true, "effective": [], "floor": "slash", "same_family_claim": true}
exit=0

control:
{"contract_header": "Review family=same. Review setup=slash-review:", "cross_claim": false, "effective": ["slash"], "floor": null, "same_family_claim": false}
exit=0
```

Fix: render from `effective` and `floor`. When only a floor remains, state that cross was requested but not projected; never emit the unconditional cross-route sentence.

Missed check: the golden at [review-matrix.json:370](/private/tmp/fix-tree/gates/goldens/review-matrix.json:370) pins both contradictory sentences.

### 6. High — three accepted review controls have no runtime consumer

[agent-launch.py:919](/private/tmp/fix-tree/launch/agent-launch.py:919), [agent-launch.py:943](/private/tmp/fix-tree/launch/agent-launch.py:943), [agent-launch.py:1072](/private/tmp/fix-tree/launch/agent-launch.py:1072), [agent-launch.py:1403](/private/tmp/fix-tree/launch/agent-launch.py:1403), [agent-launch.py:1671](/private/tmp/fix-tree/launch/agent-launch.py:1671)

`order`, `swap_augmentation`, and `aggregation` are parsed as supported controls but never enter the rendered instruction, report, or `ReviewPlan/v1`. Contrary policies produce identical contracts.

Commands:

```sh
probe() {
  PROBE_CASE="$1" python3 -c '
import json,os,runpy
m=runpy.run_path("launch/agent-launch.py")
binding=m["ReviewBinding"]("anthropic","claude","claude-opus-5","xhigh")
mechanism=m["ReviewMechanism"]("probe","exec-stdio-v1",
 m["REVIEW_ADAPTERS"]["exec-stdio-v1"],"/bin/echo",binding)
def render(order,swap,aggregation,trials):
 raw={"label":"Probe","description":"Probe","capability":"probe-kit",
  "operation":"probe-review","instructions":"dispatch {command} for {trials} passes",
  "output":"review-v1","perspectives":["correctness"],"trials":trials,
  "order":order,"swap_augmentation":swap,"aggregation":aggregation,
  "severity_emits":["high"],"severity_map":{"high":"high"}}
 return m["render_review_method"](
   m["parse_review_method"]("probe",raw,"review_methods.probe"),mechanism)
if os.environ["PROBE_CASE"]=="controls":
 a=render("fixed",False,"union",3)
 b=render("randomized",True,"majority",3)
 changed=["order","swap_augmentation","aggregation"]
else:
 a=render("fixed",False,"union",2)
 b=render("fixed",False,"union",3)
 changed=["trials"]
print(json.dumps({"changed":changed,"identical_contract_text":a==b,
 "a":a.split(" [",1)[0],"b":b.split(" [",1)[0]},sort_keys=True))
'; echo "exit=$?"
}
probe controls   # mutation
probe trials     # control
```

Outputs:

```text
mutation:
{"a": "probe: dispatch /bin/echo for 3 passes", "b": "probe: dispatch /bin/echo for 3 passes", "changed": ["order", "swap_augmentation", "aggregation"], "identical_contract_text": true}
exit=0

control:
{"a": "probe: dispatch /bin/echo for 2 passes", "b": "probe: dispatch /bin/echo for 3 passes", "changed": ["trials"], "identical_contract_text": false}
exit=0
```

Fix: put all mechanical controls in the core-owned report and machine record, render their exact values, and ensure the downstream dispatcher consumes that record.

Missed checks: `launcher_review_methods` and `launcher_review_contract` populate these fields without mutating or asserting them.

### 7. High — a capability-backed method can report `OK` without naming its command

[agent-launch.py:973](/private/tmp/fix-tree/launch/agent-launch.py:973), [agent-launch.py:1100](/private/tmp/fix-tree/launch/agent-launch.py:1100), [agent-launch.py:1305](/private/tmp/fix-tree/launch/agent-launch.py:1305), [agent-launch.py:1538](/private/tmp/fix-tree/launch/agent-launch.py:1538)

`{command}` is optional in method instructions. A capability can therefore resolve successfully and report `OK` while the launched session receives no invocation route.

Commands:

```sh
probe() {
  PROBE_INSTRUCTIONS="$1" python3 -c '
import json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
c["capabilities"]["probe-kit"]={"command":"/bin/echo",
 "offers":[{"operation":"probe-review","adapter":"exec-stdio-v1",
            "hosts":["claude"]}]}
raw={"label":"Probe","description":"Probe","capability":"probe-kit",
 "operation":"probe-review","instructions":os.environ["PROBE_INSTRUCTIONS"],
 "output":"review-v1","perspectives":["correctness"],"trials":1,
 "order":"fixed","swap_augmentation":False,"aggregation":"union",
 "severity_emits":["high"],"severity_map":{"high":"high"}}
method=m["parse_review_method"]("probe",raw,"review_methods.probe")
binding=m["ReviewBinding"]("anthropic","claude","claude-opus-5","xhigh")
row=m["_resolve_one"](method,binding,binding,c)
print(json.dumps({"status":row.status,"resolved_command":"/bin/echo",
 "command_named":"/bin/echo" in row.instruction,
 "instruction":row.instruction.split(" [",1)[0]},sort_keys=True))
'; echo "exit=$?"
}
probe "review this packet"                         # mutation
probe "dispatch {command} to review this packet" # control
```

Outputs:

```text
mutation:
{"command_named": false, "instruction": "probe: review this packet", "resolved_command": "/bin/echo", "status": "OK"}
exit=0

control:
{"command_named": true, "instruction": "probe: dispatch /bin/echo to review this packet", "resolved_command": "/bin/echo", "status": "OK"}
exit=0
```

Fix: append the resolved command through core-owned prose, or structurally require `{command}` for capability-backed methods.

Missed checks: both generic-method canaries always include `{command}`.

### 8. High — a configured cross-family request is silently rewritten to same-family

[agent-launch.py:3302](/private/tmp/fix-tree/launch/agent-launch.py:3302), [agent-launch.py:6145](/private/tmp/fix-tree/launch/agent-launch.py:6145)

On a supported single-host profile, `build_plan` overwrites its only copy of the requested family. The session is told `Review family=same` as if that were the configured choice.

Commands:

```sh
probe() {
  PROBE_SINGLE="$1" python3 -c '
import copy,json,os,pathlib,re,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
c["presets"]["probe"]=copy.deepcopy(c["presets"]["solo"])
c["presets"]["probe"]["review_family"]="cross"
if os.environ["PROBE_SINGLE"]=="1":
 c["hosts"].pop("claude",None)
 c["backends"].pop("claude",None)
p=m["build_plan"](c,"codex","probe")
s=m["run_contract"](p)
print(json.dumps({"configured":"cross","plan_family":p["review_family"],
 "contract_header":re.search(r"Review family=.*?Review setup=[^:]+:",
                             s).group(0),
 "configured_family_named":"Review family=cross" in s},sort_keys=True))
'; echo "exit=$?"
}
probe 1   # mutation
probe 0   # control
```

Outputs:

```text
mutation:
{"configured": "cross", "configured_family_named": false, "contract_header": "Review family=same. Review setup=none:", "plan_family": "same"}
exit=0

control:
{"configured": "cross", "configured_family_named": true, "contract_header": "Review family=cross. Review setup=none:", "plan_family": "cross"}
exit=0
```

Fix: preserve `review_family_requested` separately from `review_family_effective` and render both whenever they differ.

Missed check: `cross_family` at [check_parity.py:7962](/private/tmp/fix-tree/gates/check_parity.py:7962) asserts only that coercion happens and does not crash.

### 9. Medium — delegation-off contracts claim child bindings were projected

[agent-launch.py:6130](/private/tmp/fix-tree/launch/agent-launch.py:6130), [agent-launch.py:6153](/private/tmp/fix-tree/launch/agent-launch.py:6153), [agent-launch.py:6323](/private/tmp/fix-tree/launch/agent-launch.py:6323), [agent-launch.py:6341](/private/tmp/fix-tree/launch/agent-launch.py:6341)

The contract always lists child tiers and says their defaults are projected. Both host argv builders omit child bindings when delegation is off.

Commands:

```sh
probe() {
  PROBE_PRESET="$1" python3 -c '
import json,os,pathlib,re,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
out={}
for host in ("codex","claude"):
 p=m["build_plan"](c,host,os.environ["PROBE_PRESET"])
 s=m["run_contract"](p)
 a=m["project_args"](p,materialize_agents=False)
 out[host]={"delegation":p["delegation"],
  "authority":re.search(r"Main and .*?projected\.",s).group(0),
  "child_binding_in_argv":
    ("--agents" in a if host=="claude"
     else any(x.startswith("agents.") for x in a))}
print(json.dumps(out,sort_keys=True))
'; echo "exit=$?"
}
probe solo       # mutation
probe balanced   # control
```

Outputs:

```text
mutation:
{"claude": {"authority": "Main and child model/effort defaults are CLI-projected.", "child_binding_in_argv": false, "delegation": false}, "codex": {"authority": "Main and native child model/effort defaults are config-projected.", "child_binding_in_argv": false, "delegation": false}}
exit=0

control:
{"claude": {"authority": "Main and child model/effort defaults are CLI-projected.", "child_binding_in_argv": true, "delegation": true}, "codex": {"authority": "Main and native child model/effort defaults are config-projected.", "child_binding_in_argv": true, "delegation": true}}
exit=0
```

Fix: with delegation off, name only the main binding and explicitly identify child tiers as inactive.

Missed checks: `launcher_delegation_clause` checks only the on/off sentence; `profile_validation` checks only argv absence.

### 10. Medium — service tier is reported as dropped but injected into the instruction

[agent-launch.py:1315](/private/tmp/fix-tree/launch/agent-launch.py:1315), [agent-launch.py:1533](/private/tmp/fix-tree/launch/agent-launch.py:1533)

The report says a nondefault tier is unprojectable and dropped; the renderer substitutes the requested value into live contract prose anyway.

Commands:

```sh
probe() {
  PROBE_SERVICE_TIER="$1" python3 -c '
import json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
c["capabilities"]["probe-kit"]={"command":"/bin/echo",
 "offers":[{"operation":"probe-review","adapter":"exec-stdio-v1",
            "hosts":["claude"]}]}
raw={"label":"Probe","description":"Probe","capability":"probe-kit",
 "operation":"probe-review",
 "instructions":"dispatch {command} with service_tier={service_tier}",
 "output":"review-v1","perspectives":["a","b"],"trials":2,
 "order":"fixed","swap_augmentation":False,"aggregation":"union",
 "severity_emits":["high"],"severity_map":{"high":"high"}}
method=m["parse_review_method"]("probe",raw,"review_methods.probe")
binding=m["ReviewBinding"]("anthropic","claude","claude-opus-5","xhigh",
                            os.environ["PROBE_SERVICE_TIER"])
row=m["_resolve_one"](method,binding,binding,c)
print(json.dumps({"status":row.status,"detail":row.detail,
 "instruction":row.instruction.split(" [",1)[0]},sort_keys=True))
'; echo "exit=$?"
}
probe fast       # mutation
probe disabled   # control
```

Outputs:

```text
mutation:
{"detail": "service_tier='fast' is not projectable at launch; dropped", "instruction": "probe: dispatch /bin/echo with service_tier=fast", "status": "ADVISORY"}
exit=0

control:
{"detail": "", "instruction": "probe: dispatch /bin/echo with service_tier=disabled", "status": "OK"}
exit=0
```

Fix: resolve one effective binding. If the value is dropped, remove it from the instruction or substitute the effective default.

Missed check: `launcher_review_report` asserts `ADVISORY` and the detail text but uses a template without `{service_tier}`.

### 11. Medium — an unknown tier-override key is silently discarded

[agent-launch.py:3241](/private/tmp/fix-tree/launch/agent-launch.py:3241)

`build_plan` validates the host and tier but never rejects unknown override leaves. A misspelled `model` key launches and advertises the default model.

Commands:

```sh
probe() {
  PROBE_KEY="$1" python3 -c '
import copy,json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
key=os.environ["PROBE_KEY"]
p=copy.deepcopy(c["presets"]["solo"])
p["main_tier"]="workhorse"
p["tier_overrides"]={"codex":{"workhorse":{key:"custom-gpt"}}}
c["presets"]["probe"]=p
plan=m["build_plan"](c,"codex","probe")
a=m["project_args"](plan,materialize_agents=False)
print(json.dumps({"authored_key":key,"authored_value":"custom-gpt",
 "plan_model":plan["tiers"]["workhorse"]["model"],
 "argv_model":a[a.index("--model")+1],
 "contract_names_custom":
   "custom-gpt" in m["run_contract"](plan).split(". ")[0]},sort_keys=True))
'; echo "exit=$?"
}
probe modle   # mutation
probe model   # control
```

Outputs:

```text
mutation:
{"argv_model": "gpt-5.6-terra", "authored_key": "modle", "authored_value": "custom-gpt", "contract_names_custom": false, "plan_model": "gpt-5.6-terra"}
exit=0

control:
{"argv_model": "custom-gpt", "authored_key": "model", "authored_value": "custom-gpt", "contract_names_custom": true, "plan_model": "custom-gpt"}
exit=0
```

Fix: reject `set(override) - {"model", "effort"}` before rebuilding the tier.

Missed checks: `profile_validation`, `profile_errors`, and `config_typos_reach_the_user_as_messages` mutate value types, not key spellings.

### 12. Medium — instruction format decoration escapes as raw `ValueError`

[agent-launch.py:1100](/private/tmp/fix-tree/launch/agent-launch.py:1100), [agent-launch.py:1330](/private/tmp/fix-tree/launch/agent-launch.py:1330), [agent-launch.py:6783](/private/tmp/fix-tree/launch/agent-launch.py:6783)

The validator checks field names but ignores format specs and conversions. Formatting then raises outside the CLI’s `LaunchError` boundary.

Commands:

```sh
probe() {
  PROBE_INSTRUCTIONS="$1" python3 -c '
import json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
c["capabilities"]["probe-kit"]={"command":"/bin/echo",
 "offers":[{"operation":"probe-review","adapter":"exec-stdio-v1",
            "hosts":["claude"]}]}
raw={"label":"Probe","description":"Probe","capability":"probe-kit",
 "operation":"probe-review","instructions":os.environ["PROBE_INSTRUCTIONS"],
 "output":"review-v1","perspectives":["a","b"],"trials":2,
 "order":"fixed","swap_augmentation":False,"aggregation":"union",
 "severity_emits":["high"],"severity_map":{"high":"high"}}
try:
 method=m["parse_review_method"]("probe",raw,"review_methods.probe")
 b=m["ReviewBinding"]("anthropic","claude","claude-opus-5","xhigh")
 row=m["_resolve_one"](method,b,b,c)
 print(json.dumps({"result":"built",
   "instruction":row.instruction.split(" [",1)[0]},sort_keys=True))
except Exception as exc:
 print(json.dumps({"result":"exception","type":type(exc).__name__,
   "message":str(exc),"is_launch_error":isinstance(exc,m["LaunchError"])},
   sort_keys=True))
 raise SystemExit(1)
'; echo "exit=$?"
}
probe "dispatch {command} on {model:bogus}" # mutation
probe "dispatch {command} on {model}"       # control
```

Outputs:

```text
mutation:
{"is_launch_error": false, "message": "Invalid format specifier 'bogus' for object of type 'str'", "result": "exception", "type": "ValueError"}
exit=1

control:
{"instruction": "probe: dispatch /bin/echo on claude-opus-5", "result": "built"}
exit=0
```

Fix: reject nonempty format specs and conversions in `validate_instruction_slots`; defensively translate formatting failures into `LaunchError`.

Missed check: `launcher_review_methods` tests only a flat unknown slot.

### 13. Medium — FRONTIER effort has two authorities that can disagree

[agent-launch.py:3247](/private/tmp/fix-tree/launch/agent-launch.py:3247), [agent-launch.py:3261](/private/tmp/fix-tree/launch/agent-launch.py:3261), [agent-launch.py:5068](/private/tmp/fix-tree/launch/agent-launch.py:5068), [agent-launch.py:5934](/private/tmp/fix-tree/launch/agent-launch.py:5934)

A tier override updates `plan["tiers"]["frontier"]["effort"]`; top-level `frontier_effort` separately controls the contract and argv. Both values remain live and can conflict.

Commands:

```sh
probe() {
  PROBE_TOP="$1" python3 -c '
import copy,json,os,pathlib,re,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
p=copy.deepcopy(c["presets"]["balanced"])
p["main_tier"]="frontier"
p["tier_overrides"]={"claude":{"frontier":{"effort":"high"}}}
if os.environ["PROBE_TOP"]=="1":
 p["frontier_effort"]="max"
else:
 p.pop("frontier_effort",None)
c["presets"]["probe"]=p
plan=m["build_plan"](c,"claude","probe")
contract=m["run_contract"](plan)
a=m["project_args"](plan,materialize_agents=False)
print(json.dumps({
 "stored_tier_effort":plan["tiers"]["frontier"]["effort"],
 "effective_frontier_effort":plan["frontier_effort"],
 "contract_main":re.search(r"main=frontier \(([^)]+)\)",contract).group(1),
 "argv_effort":a[a.index("--effort")+1]},sort_keys=True))
'; echo "exit=$?"
}
probe 1   # mutation
probe 0   # control
```

Outputs:

```text
mutation:
{"argv_effort": "max", "contract_main": "claude-fable-5/max", "effective_frontier_effort": "max", "stored_tier_effort": "high"}
exit=0

control:
{"argv_effort": "high", "contract_main": "claude-fable-5/high", "effective_frontier_effort": "high", "stored_tier_effort": "high"}
exit=0
```

Fix: normalize FRONTIER effort to one field, or reject profiles that author conflicting top-level and tier-override values.

Missed check: `same_family` mutates only top-level `frontier_effort`, so it cannot expose the conflict.

### 14. Low — `host_dispatch_command` promises an absolute path but returns a relative one

[agent-launch.py:1189](/private/tmp/fix-tree/launch/agent-launch.py:1189), [agent-launch.py:2183](/private/tmp/fix-tree/launch/agent-launch.py:2183)

The docstring promises an absolute command. `resolve_command` validates slash-containing paths but returns them unchanged, and the relative spelling enters the contract.

Commands:

```sh
probe() {
  PROBE_FORM="$1" CLAUDE_CONFIG_DIR=/definitely/missing python3 -c '
import json,os,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
value=(str(pathlib.Path("launch/agent-launch.py").resolve())
       if os.environ["PROBE_FORM"]=="absolute"
       else "./launch/agent-launch.py")
c["backends"]["claude"]["command"]=value
resolved=m["host_dispatch_command"]("claude",c)
contract=m["run_contract"](m["build_plan"](c,"codex","balanced"))
print(json.dumps({"configured":value,"returned":resolved,
 "is_absolute":pathlib.Path(resolved).is_absolute(),
 "named_in_contract":("dispatch "+resolved) in contract},sort_keys=True))
'; echo "exit=$?"
}
probe relative   # mutation
probe absolute   # control
```

Outputs:

```text
mutation:
{"configured": "./launch/agent-launch.py", "is_absolute": false, "named_in_contract": true, "returned": "./launch/agent-launch.py"}
exit=0

control:
{"configured": "/private/tmp/fix-tree/launch/agent-launch.py", "is_absolute": true, "named_in_contract": true, "returned": "/private/tmp/fix-tree/launch/agent-launch.py"}
exit=0
```

Fix: return `os.path.abspath(expanded)` for validated slash-containing commands.

Missed checks: `launcher_review_contract` and `backend_dispatch` use only absolute synthetic executables.

## Denominator and existing checks

`python3 gates/check_parity.py --list` listed 60 checks. I inspected the contract-relevant checks, including `launcher_review_report`, `launcher_review_contract`, `launcher_delegation_clause`, `launcher_review_methods`, `launcher_review_schema`, `backend_dispatch`, `profile_validation`, `review_matrix`, `agent_materialization`, `vanilla_mode`, `cross_family`, and `same_family`.

A direct matrix executed all 12 shipped host/preset pairs:

```text
codex:  balanced OK; deep-review OK; fast-batch OK; session-distill OK; solo OK; vanilla bare
claude: balanced OK; deep-review OK; fast-batch OK; session-distill OK; solo OK; vanilla bare
```

“OK” here means only that the configured main model/effort matched the base argv carrier before forwarded overrides. It is not a semantic clean bill of health.

I also executed:

- 16 legacy setup/family/host projections through `build_plan → run_contract → project_args`.
- 11 documented optional profile shapes, including omitted legacy provider fields, per-host `frontier_effort`, tier overrides, and single-host legacy/composable cases. All completed without a raw exception; the semantic defects above still remained.

The relevant fixture subset did not participate because the runner could not allocate its temporary directory:

```text
NOTE: partial run (14/60 checks) — the launcher fixture is order-dependent, so this does not stand in for a full gate run
FileNotFoundError: No usable temporary directory found ...
exit=1
```

I did not count that as a green run.

## Void readings

`install_hint` says it is empty when a route is already installed. Direct missing/installed calls behaved identically:

```sh
python3 -c '
import pathlib,runpy
m=runpy.run_path("launch/agent-launch.py")
missing={"capabilities":{"probe":{"command":"/not/here","install":"install-probe"}}}
installed={"capabilities":{"probe":{"command":"/bin/echo","install":"install-probe"}}}
print("missing="+repr(m["install_hint"](missing,["probe"])))
print("installed="+repr(m["install_hint"](installed,["probe"])))
'
```

```text
missing='; install: install-probe'
installed='; install: install-probe'
```

Because both behaved the same and live callers prefilter missing routes before invoking the helper, this is void as a runtime finding.

Not examined: actual host execution beyond dry-run/import paths, interactive editing and preset persistence, receipt production/adjudication, review subprocess execution, deployment/install behavior, catalog behavior beyond confirming the contract renderers do not source it, and the expressly excluded surfaces.
