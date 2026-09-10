---
created_at: 2026-08-17T03:39:00+09:00
head: b7c482f
kind: review
---

# Round 23 — cross-family review of the round-22 repairs (raw findings)

Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`, packet on stdin (this session's `r23-packet.md`: the round-22 repairs in `cf0b2ad`, host CLIs not to be invoked); 429,021 tokens. Five Medium findings, no High; three candidates void (one confirms the round-22 `--custom` fix reaches the customization path). corpus-state and the wizard trial path again unreached. Verbatim below.

Five Medium findings met the discriminating-control bar. No High finding survived adjudication.

## Findings

### 1. Medium — non-HELM mains advertise an unprojected HELM binding

File: [launch/agent-launch.py:6915](/private/tmp/fix-tree/launch/agent-launch.py:6915), [launch/agent-launch.py:6696](/private/tmp/fix-tree/launch/agent-launch.py:6696), [launch/agent-launch.py:7307](/private/tmp/fix-tree/launch/agent-launch.py:7307)

What it says: the contract enumerates the projected tier bindings, then says main and native-child defaults are projected. The summary repeats every enumerated tier. Separately, `SPAWNABLE_TIERS` states that HELM is never a child.

What it does: with the shipped `fast-batch` preset, WORKHORSE is main and the only children are FRONTIER, WORKHORSE, and SWEEP. HELM nevertheless appears as an active binding in the contract and both summaries.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import pathlib,runpy;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));p=m["build_plan"](c,"codex","fast-batch");a=m["project_args"](p,False);children=sorted({x.split(".",2)[1] for x in a if x.startswith("agents.")});advertised=sorted(p["tiers"]);used=sorted(set(children)|{p["main_tier"]});print("main=%s advertised=%r child_configs=%r unused=%r"%(p["main_tier"],advertised,children,sorted(set(advertised)-set(used))));print("contract_helm=%s"%("helm=" in m["run_contract"](p)))'
```

```text
main=workhorse advertised=['frontier', 'helm', 'sweep', 'workhorse'] child_configs=['frontier', 'sweep', 'workhorse'] unused=['helm']
contract_helm=True
```

Nearest control, where HELM really is the main:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import pathlib,runpy;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));p=m["build_plan"](c,"codex","balanced");a=m["project_args"](p,False);children=sorted({x.split(".",2)[1] for x in a if x.startswith("agents.")});advertised=sorted(p["tiers"]);used=sorted(set(children)|{p["main_tier"]});print("main=%s advertised=%r child_configs=%r unused=%r"%(p["main_tier"],advertised,children,sorted(set(advertised)-set(used))));print("contract_helm=%s"%("helm=" in m["run_contract"](p)))'
```

```text
main=helm advertised=['frontier', 'helm', 'sweep', 'workhorse'] child_configs=['frontier', 'sweep', 'workhorse'] unused=[]
contract_helm=True
```

Proposed fix: derive one ordered active-tier set from `main_tier ∪ SPAWNABLE_TIERS`. Use it in `run_contract`, both summaries, and child projection; render anything outside it as inactive.

Missed check: [`backend_dispatch`](/private/tmp/fix-tree/gates/check_parity.py:8268) already has a FRONTIER-main dry-run fixture, but asserts only the main binding rather than reconciling every advertised tier against argv.

### 2. Medium — a forged ReviewPlan availability is rendered as launch-time fact

File: [launch/agent-launch.py:1832](/private/tmp/fix-tree/launch/agent-launch.py:1832), [launch/agent-launch.py:2217](/private/tmp/fix-tree/launch/agent-launch.py:2217), [launch/agent-launch.py:2227](/private/tmp/fix-tree/launch/agent-launch.py:2227)

What it says: `review_plan_from_v1` is the typed inverse of the generated plan; `availability` is specifically the launch-time projection and remains unchanged during verification.

What it does: row fields are now structurally validated, but the plan header is copied unchecked. A forged availability survives successful verification and is explicitly labelled “launch-time projection.”

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");row=m["ReviewMethodReport"](method_id="m",status="OK",grade="perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls={"trials":1});r=m["ReviewReport"](row,(),"perspective_floor");d=m["review_plan_v1"](r);d["availability"]="forged-reachable";p=m["review_plan_from_v1"](d);b={"schema":"ReviewReceipts/v1","main_dispatch_id":"main","packet_sha256":"a"*64,"receipts":[{"schema":"ReviewReceipt/v1","method_id":"m","dispatch_id":"child","packet_sha256":"a"*64,"result_sha256":"b"*64,"provider":"openai","model":"model-x","effort":"high","exit_status":0}]};v,vs=m["verify_review_receipts"](p,b,{"m":{"trials":1}});print(m["render_receipt_verdicts"](v,vs).splitlines()[0])'
```

```text
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=forged-reachable — launch-time projection, unchanged by verification)
```

Control:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");row=m["ReviewMethodReport"](method_id="m",status="OK",grade="perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls={"trials":1});r=m["ReviewReport"](row,(),"perspective_floor");d=m["review_plan_v1"](r);p=m["review_plan_from_v1"](d);b={"schema":"ReviewReceipts/v1","main_dispatch_id":"main","packet_sha256":"a"*64,"receipts":[{"schema":"ReviewReceipt/v1","method_id":"m","dispatch_id":"child","packet_sha256":"a"*64,"result_sha256":"b"*64,"provider":"openai","model":"model-x","effort":"high","exit_status":0}]};v,vs=m["verify_review_receipts"](p,b,{"m":{"trials":1}});print(m["render_receipt_verdicts"](v,vs).splitlines()[0])'
```

```text
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
```

Proposed fix: validate the whole header before constructing `ReviewReport`: canonical availability, known `best_grade`, and the permitted launch-time `achieved_grade`. Refuse wrong types and unknown enum values by field name.

Missed check: [`launcher_receipts`](/private/tmp/fix-tree/gates/check_parity.py:3578) mutates row fields but not these top-level plan fields.

### 3. Medium — fields named `*_sha256` accept arbitrary strings and earn `complete`

File: [launch/agent-launch.py:1968](/private/tmp/fix-tree/launch/agent-launch.py:1968), [launch/agent-launch.py:1997](/private/tmp/fix-tree/launch/agent-launch.py:1997), [launch/agent-launch.py:2300](/private/tmp/fix-tree/launch/agent-launch.py:2300)

What it says: the receipt writer owns the hashes and computes them with SHA-256; the bundle independently hashes the packet.

What it does: the verifier checks only non-emptiness and packet-string equality. Paired non-hash packet strings and non-hash result strings are credited.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":1};R=m["ReviewMethodReport"](method_id="m",status="OK",grade="perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=C);report=m["ReviewReport"](R,(),"perspective_floor");
for field in ("packet_sha256","result_sha256"):
 p="a"*64;r="b"*64
 if field=="packet_sha256":p="not-a-sha256"
 else:r="not-a-sha256"
 receipt={"schema":"ReviewReceipt/v1","method_id":"m","dispatch_id":"child","packet_sha256":p,"result_sha256":r,"provider":"openai","model":"model-x","effort":"high","exit_status":0};bundle={"schema":"ReviewReceipts/v1","main_dispatch_id":"main","packet_sha256":p,"receipts":[receipt]};v,vs=m["verify_review_receipts"](report,bundle,{"m":C});print(f"{field}=nonhex achievement={v.achievement} accepted={vs[0].accepted} reason={vs[0].reason}")'
```

```text
packet_sha256=nonhex achievement=complete accepted=True reason=verified
result_sha256=nonhex achievement=complete accepted=True reason=verified
```

Nearest handled malformed controls:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":1};R=m["ReviewMethodReport"](method_id="m",status="OK",grade="perspective_floor",model="model-x",effort="high",provider="openai",mechanism="native",controls=C);report=m["ReviewReport"](R,(),"perspective_floor");
for field in ("packet_sha256","result_sha256"):
 p="a"*64;r="b"*64
 if field=="packet_sha256":p=""
 else:r=""
 receipt={"schema":"ReviewReceipt/v1","method_id":"m","dispatch_id":"child","packet_sha256":p,"result_sha256":r,"provider":"openai","model":"model-x","effort":"high","exit_status":0};bundle={"schema":"ReviewReceipts/v1","main_dispatch_id":"main","packet_sha256":p,"receipts":[receipt]}
 try:v,vs=m["verify_review_receipts"](report,bundle,{"m":C});print(f"{field}=empty achievement={v.achievement} accepted={vs[0].accepted} reason={vs[0].reason}")
 except m["LaunchError"] as e:print(f"{field}=empty LaunchError={e}")'
```

```text
packet_sha256=empty LaunchError=ReviewReceipts/v1 carries no packet_sha256, so the packet check cannot fire against any receipt in it
result_sha256=empty achievement=none accepted=False reason=records an empty result, so nothing was actually reviewed
```

Proposed fix: require canonical lowercase 64-character SHA-256 hex for bundle and receipt packet hashes, result hashes, and pass entries before equality/count checks. Preserve the separate semantic refusal for the hash of an empty result.

Missed checks: [`launcher_receipts`](/private/tmp/fix-tree/gates/check_parity.py:3578) and [`launcher_receipt_fold`](/private/tmp/fix-tree/gates/check_parity.py:4242) use placeholders such as `"packet"` and `"one"`, so neither asks whether the purported hashes are hashes.

### 4. Medium — Save silently erases malformed inactive `frontier_effort`

File: [launch/agent-launch.py:5163](/private/tmp/fix-tree/launch/agent-launch.py:5163)

What it says: raw scalar-or-host-map authoring is carried because inactive-host intent must survive Save As, then normalized into `tier_overrides`.

What it does: a malformed inactive entry is silently skipped at lines 5172–5173. Saving a Claude-valid plan with `codex = false` drops that value and reloads Codex at its default effort.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import pathlib,runpy,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["balanced"]["frontier_effort"]={"claude":"max","codex":False};p=m["build_plan"](c,"claude","balanced");f,o,r=m["preset_from_plan"](p,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];saved_config={**c,"presets":{**c["presets"],"saved":saved}};print("source_inactive=%r saved_override=%r"%(p["frontier_effort_authored"]["codex"],saved.get("tier_overrides",{}).get("codex",{}).get("frontier")));print("saved_codex_effort=%s"%m["tier_effort"](m["build_plan"](saved_config,"codex","saved"),"frontier"))'
```

```text
source_inactive=False saved_override=None
saved_codex_effort=max
```

Control:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import pathlib,runpy,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["balanced"]["frontier_effort"]={"claude":"max","codex":"ultra"};p=m["build_plan"](c,"claude","balanced");f,o,r=m["preset_from_plan"](p,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];saved_config={**c,"presets":{**c["presets"],"saved":saved}};print("source_inactive=%r saved_override=%r"%(p["frontier_effort_authored"]["codex"],saved.get("tier_overrides",{}).get("codex",{}).get("frontier")));print("saved_codex_effort=%s"%m["tier_effort"](m["build_plan"](saved_config,"codex","saved"),"frontier"))'
```

```text
source_inactive='ultra' saved_override={'effort': 'ultra'}
saved_codex_effort=ultra
```

Proposed fix: validate every host-map entry during plan construction, or at minimum replace the save-path `continue` with a named `LaunchError`. Never turn malformed authoring into host defaults.

Missed check: [`preset_save`](/private/tmp/fix-tree/gates/check_parity.py:10121) covers malformed inactive `tier_overrides`, but not the raw inactive `frontier_effort` map.

### 5. Medium — the generic review-arm writer refuses TOML integers as unrepresentable

File: [launch/agent-launch.py:5200](/private/tmp/fix-tree/launch/agent-launch.py:5200), [launch/agent-launch.py:5208](/private/tmp/fix-tree/launch/agent-launch.py:5208), [launch/agent-launch.py:5225](/private/tmp/fix-tree/launch/agent-launch.py:5225)

What it says: inactive arms are serialized generically and recursively; `_arm_scalar` promises refusal only for values having no TOML spelling.

What it does: `_toml_scalar` supports only strings and booleans. An integer accepted by TOML and carried in an inactive arm is falsely described as having no writable form.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import pathlib,runpy;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["deep-review"]["review"]["hosts"]["codex"]["limit"]=7;p=m["build_plan"](c,"claude","deep-review");f,o,r=m["preset_from_plan"](p,c,"copy");
try: m["render_preset_block"]("copy",f,o,r);print("render=ok")
except m["LaunchError"] as e: print(f"render=LaunchError: {e}")'
```

```text
render=LaunchError: preset 'copy': review.hosts.codex.limit holds int, which has no form this writes back. Fix that entry in the launch profile and save again.
```

Control:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import pathlib,runpy;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["deep-review"]["review"]["hosts"]["codex"]["limit"]=True;p=m["build_plan"](c,"claude","deep-review");f,o,r=m["preset_from_plan"](p,c,"copy");s=m["render_preset_block"]("copy",f,o,r);print("render=ok line="+[x for x in s.splitlines() if x.startswith("limit =")][0])'
```

```text
render=ok line=limit = true
```

Proposed fix: give untouched-arm values a real TOML-value serializer covering the types `tomllib` can produce—integers, floats, arrays and date/time values as well as strings and booleans. Retain named refusal only for genuinely unrepresentable values.

Missed check: [`launcher_review_save`](/private/tmp/fix-tree/gates/check_parity.py:5529) exercises unknown scalar and recursive fields only with strings.

## Void readings

- `result_sha256` absent from `passes`: direct verification returned `complete`, but the nearest valid control also returned `complete`. Under the requested evidence rule, this is void rather than a finding.

```text
mutation: result_in_passes=False distinct=2 achievement=complete reason=verified
control:  result_in_passes=True  distinct=2 achievement=complete reason=verified
```

- Different non-empty `ordering_seed` and `swap_group` values versus identical values both produced:

```text
folded=ok passes=2 seed_present=True swap_present=True
```

This is also the behaviour explicitly retained by D-20260816-c0067f, D-20260816-0ed011, and D-20260817-3d6a6e, so it is not a finding.

- The `--custom` twin did not reproduce. With an ordinary picker result:

```text
custom_requested=True customize_calls=1 label='Custom (Balanced)'
```

The no-flag control produced:

```text
custom_requested=False customize_calls=0 label='Balanced'
```

The round-22 OR fix therefore reaches the customization path.

## Denominator

Executed:

- All 12 shipped host/preset cells through `build_plan`, `project_args(False)`, `setup_summary_lines`, and `print_summary`: 12 plans, 10 projected contracts, 12 setup summaries, 12 launch summaries.
- Direct `--dry-run` for Codex `fast-batch` and `balanced`; neither invoked the backend.
- 19 receipt/schema field families: 15 ReviewPlan mutations and 24 receipt mutations with controls.
- Save projection for both inactive-host FRONTIER cases and top-level/recursive inactive review-arm values.
- The 62 registered `check_parity.py` check names and the relevant fixtures.
- Branch/HEAD remained `review-round-20` / `b7c482f145aa5f5f2598f45333c2d07276c548f6`; the worktree remained clean.

Not examined: `compose/corpus-state.py`, the wizard trial path, actual host CLI execution, access-control surfaces, writable on-disk `save_preset`, filesystem-backed receipt emission/folding or the file-based `--verify-receipts` command, the full write-using parity suite, and unscripted TUI interaction.
