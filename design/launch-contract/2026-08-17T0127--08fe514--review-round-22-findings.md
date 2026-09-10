---
created_at: 2026-08-17T01:27:00+09:00
head: 08fe514
kind: review
---

# Round 22 — cross-family review of the round-21 repairs (raw findings)

Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`, packet on stdin (this session's `r22-packet.md`: the round-21 repairs in `f2513a8`, host CLIs not to be invoked); 459,548 tokens. Ten findings admitted (3 High, 7 Medium); the reviewer stopped itself when one delegated lens crossed the excluded surface and discarded that probe. corpus-state and the wizard trial path again unreached. Verbatim below.

Review ended when one delegated lens crossed the excluded surface. I stopped it immediately and discarded that probe and all conclusions from it. The ten findings below were independently reproduced within scope before the stop. No host CLI was invoked and no files were changed.

## Denominator

- 20 launcher `--dry-run` executions: all 12 shipped host/preset cells, two bare cells, four Custom cells, and two forwarded-argument cells.
- 23 direct contract projections, including every shipped cell and all 11 allowed execution-value spellings.
- Receipt review covered all 15 functions in `agent-launch.py:1763–2454`, four record shapes containing 33 field positions, and 16 independent Python probes.
- I additionally ran 26 paired Python probes over Custom selection, setup summaries, preset projection/serialization, ReviewPlan parsing, receipt folding, verification, and verdict rendering.
- I read the 62 names returned by `gates/check_parity.py --list` and inspected the relevant fixtures. I did not run the write-using parity suite in this read-only review.

## Findings

### 1. High — null plan seat fields let a seatless receipt earn `complete`

[agent-launch.py:1832](/private/tmp/fix-tree/launch/agent-launch.py:1832), [agent-launch.py:1865](/private/tmp/fix-tree/launch/agent-launch.py:1865), [agent-launch.py:1984](/private/tmp/fix-tree/launch/agent-launch.py:1984)

What it says: `ReviewPlan/v1` is the typed inverse of the generated plan, wrong shapes are named, and a receipt is credited only on the exact projected provider/model/effort seat.

What it does: `_row_from_v1` accepts `provider=model=effort=None`. A receipt omitting those fields also reads as three `None` values, so all three equality checks pass and the method becomes `complete`.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row={"method_id":"probe","status":m["STATUS_OK"],"grade":"perspective_floor","detail":"","model":None,"effort":None,"provider":None,"mechanism":"exec","instruction":"","controls":C};report=m["review_plan_from_v1"]({"schema":m["REVIEW_PLAN_SCHEMA"],"availability":"projected","best_grade":"perspective_floor","achieved_grade":m["ACHIEVED_UNKNOWN"],"base":row,"methods":[]});receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","exit_status":0};v,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":C});print("plan_seat=%r receipt_has_seat=%s achievement=%s reason=%s"%((report.base.provider,report.base.model,report.base.effort),any(x in receipt for x in ("provider","model","effort")),v.achievement,vs[0].reason))'
```

```text
exit 0
plan_seat=(None, None, None) receipt_has_seat=False achievement=complete reason=verified
```

Control — same receipt against a correctly typed plan row:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row={"method_id":"probe","status":m["STATUS_OK"],"grade":"perspective_floor","detail":"","model":"model","effort":"high","provider":"openai","mechanism":"exec","instruction":"","controls":C};report=m["review_plan_from_v1"]({"schema":m["REVIEW_PLAN_SCHEMA"],"availability":"projected","best_grade":"perspective_floor","achieved_grade":m["ACHIEVED_UNKNOWN"],"base":row,"methods":[]});receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","exit_status":0};v,vs=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":C});print("plan_seat=%r receipt_has_seat=%s achievement=%s reason=%s"%((report.base.provider,report.base.model,report.base.effort),any(x in receipt for x in ("provider","model","effort")),v.achievement,vs[0].reason))'
```

```text
exit 0
plan_seat=('openai', 'model', 'high') receipt_has_seat=False achievement=none reason=reports provider=None where the plan projected 'openai'
```

Proposed fix: make `_row_from_v1` a complete structural door. Every selectable row needs a non-empty string `method_id`, provider, model, effort, mechanism, and the closed status/grade shapes; nullable seat fields remain valid only on dropped rows.

Missed check: `launcher_receipts`. Its malformed-plan cases mutate whole row containers and `controls`, never individual identity fields.

### 2. High — folded control evidence depends on which receipt is first

[agent-launch.py:2320](/private/tmp/fix-tree/launch/agent-launch.py:2320), [agent-launch.py:2376](/private/tmp/fix-tree/launch/agent-launch.py:2376), [agent-launch.py:2405](/private/tmp/fix-tree/launch/agent-launch.py:2405)

What it says: every pass is judged before folding because anything inherited from a later pass otherwise disappears; the existing check also states that reversing the same receipts must not change the outcome.

What it does: the fold compares provider, model, effort, packet, and evidence-field presence, but copies `ordering_seed` and `swap_group` solely from `group[0]`. Reversing an identical pair changes `complete` into `none`.

Mutation — marked pass first:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":2,"order":"randomized","swap_augmentation":True,"aggregation":"union"};R=m["ReviewMethodReport"]("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",C);base={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0};marked=base|{"dispatch_id":"child-1","result_sha256":"one","ordering_seed":"seed","swap_group":"swap"};plain=base|{"dispatch_id":"child-2","result_sha256":"two"};merged=m["_merge_method_passes"]("probe",[marked,plain],"main");v,vs=m["verify_review_receipts"](m["ReviewReport"](R,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"probe":C});print("order=marked-first merged_seed=%r merged_swap=%r achievement=%s"%(merged.get("ordering_seed"),merged.get("swap_group"),v.achievement));print(m["render_receipt_verdicts"](v,vs))'
```

```text
exit 0
order=marked-first merged_seed='seed' merged_swap='swap' achievement=complete
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  probe: ACHIEVED/perspective_floor — verified
```

Control — exact same receipts reversed:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":2,"order":"randomized","swap_augmentation":True,"aggregation":"union"};R=m["ReviewMethodReport"]("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",C);base={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0};marked=base|{"dispatch_id":"child-1","result_sha256":"one","ordering_seed":"seed","swap_group":"swap"};plain=base|{"dispatch_id":"child-2","result_sha256":"two"};merged=m["_merge_method_passes"]("probe",[plain,marked],"main");v,vs=m["verify_review_receipts"](m["ReviewReport"](R,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"probe":C});print("order=plain-first merged_seed=%r merged_swap=%r achievement=%s"%(merged.get("ordering_seed"),merged.get("swap_group"),v.achievement));print(m["render_receipt_verdicts"](v,vs))'
```

```text
exit 0
order=plain-first merged_seed=None merged_swap=None achievement=none
Review achievement (achievement=none [0/1 evidenced], achieved_grade=UNKNOWN_UNTIL_RECEIPTS, availability=projected — launch-time projection, unchanged by verification)
  probe: PROPOSED — omits the ordering seed its randomized order requires, so the panel controls are unproven
```

Proposed fix: compare `ordering_seed` and `swap_group` presence/value across the raw group before copying. If every pass omits a field, let descriptor-aware adjudication decide as it does today. That preserves decisions D-20260816-c0067f and D-20260816-0ed011.

Missed check: `launcher_receipt_fold`. Its order-invariance assertion covers empty results only.

### 3. High — JSON `false` is credited as integer exit status zero

[agent-launch.py:1933](/private/tmp/fix-tree/launch/agent-launch.py:1933), [agent-launch.py:1971](/private/tmp/fix-tree/launch/agent-launch.py:1971), [agent-launch.py:2271](/private/tmp/fix-tree/launch/agent-launch.py:2271)

What it says: the producer requires and stores an integer exit status; every raw receipt passes through the shared structural validator.

What it does: verification checks only `value != 0`. In Python, `False == 0`, so a JSON boolean earns `complete`.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};R=m["ReviewMethodReport"]("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",C);receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":False};v,vs=m["verify_review_receipts"](m["ReviewReport"](R,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":C});print("exit_status=%r type=%s achievement=%s reason=%s"%(receipt["exit_status"],type(receipt["exit_status"]).__name__,v.achievement,vs[0].reason))'
```

```text
exit 0
exit_status=False type=bool achievement=complete reason=verified
```

Control — the adjacent Boolean value does not obtain false credit:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy;m=runpy.run_path("launch/agent-launch.py");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};R=m["ReviewMethodReport"]("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",C);receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":True};v,vs=m["verify_review_receipts"](m["ReviewReport"](R,(),"perspective_floor"),{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":C});print("exit_status=%r type=%s achievement=%s reason=%s"%(receipt["exit_status"],type(receipt["exit_status"]).__name__,v.achievement,vs[0].reason))'
```

```text
exit 0
exit_status=True type=bool achievement=none reason=records a failed dispatch (exit True)
```

Proposed fix: shared receipt validation should require `type(exit_status) is int`; retain nonzero integers on the existing failed-dispatch path.

Missed checks: `launcher_receipts` tests integer `3`; `launcher_receipt_fold` fixtures use integer `0`. Neither tests Boolean JSON values.

### 4. Medium — `--custom` is discarded when no preset is named

[agent-launch.py:6424](/private/tmp/fix-tree/launch/agent-launch.py:6424), [agent-launch.py:7330](/private/tmp/fix-tree/launch/agent-launch.py:7330)

What it says: `--custom` means “open customization after preset selection.”

What it does: `selected_custom` initially receives the flag, then the picker’s Boolean overwrites it. Selecting ordinary `balanced` therefore skips customization entirely.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");g=m["select_plan"].__globals__;calls=[];g["pick_mode_and_preset"]=lambda *a,**k:("balanced",False,"builder");g["customize"]=lambda *a,**k:calls.append(a[0]["preset"]);args=m["parse_args"](["--custom","codex"]);plan=m["select_plan"](m["load_config"](pathlib.Path("launch/agent-launch.toml")),args.host,args.preset,args.custom);print("parsed_custom=%s picked_preset=%s label=%r customize_calls=%d"%(args.custom,plan["preset"],plan["label"],len(calls)))'
```

```text
exit 0
parsed_custom=True picked_preset=balanced label='Balanced' customize_calls=0
```

Control — name the same preset explicitly:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");g=m["select_plan"].__globals__;calls=[];g["pick_mode_and_preset"]=lambda *a,**k:("balanced",False,"builder");g["customize"]=lambda *a,**k:calls.append(a[0]["preset"]);args=m["parse_args"](["--preset","balanced","--custom","codex"]);plan=m["select_plan"](m["load_config"](pathlib.Path("launch/agent-launch.toml")),args.host,args.preset,args.custom);print("parsed_custom=%s picked_preset=%s label=%r customize_calls=%d"%(args.custom,plan["preset"],plan["label"],len(calls)))'
```

```text
exit 0
parsed_custom=True picked_preset=balanced label='Custom (Balanced)' customize_calls=1
```

Proposed fix: combine the two sources: `selected_custom = custom_requested or picker_custom`.

Missed check: `launcher_module_api` drives picker-selected Custom and explicit-preset Custom separately, never `custom_requested=True` plus picker-selected ordinary preset.

### 5. Medium — Builder → Custom can inherit the routed distill mission

[agent-launch.py:6360](/private/tmp/fix-tree/launch/agent-launch.py:6360), [agent-launch.py:6433](/private/tmp/fix-tree/launch/agent-launch.py:6433)

What it says: “Custom always starts from the builder default.” The arbitrary-preset fallback exists only to keep Custom usable in a stripped profile.

What it does: if the only preset is `session-distill`, Builder → Custom uses it as the baseline and retains `mode=distill`, its mission, and `distill!` trigger.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]={"session-distill":c["presets"]["session-distill"]};g=m["select_plan"].__globals__;answers=iter([m["DEFAULT_PRESET_MODE"],m["CUSTOM_PRESET"]]);g["choose"]=lambda *a,**k:next(answers);g["customize"]=lambda *a,**k:None;g["load_corpus_status"]=lambda:{"domains":{}};p=m["select_plan"](c,"codex",None,False);print("available=session-distill selected=%s label=%r mode=%s mission=%s trigger=%r"%(p["preset"],p["label"],p["mode"],bool(p.get("mission")),p.get("trigger")))'
```

```text
exit 0
available=session-distill selected=session-distill label='Custom (Session distill)' mode=distill mission=True trigger='distill!'
```

Control — same stripped profile shape with only Vanilla:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]={"vanilla":c["presets"]["vanilla"]};g=m["select_plan"].__globals__;answers=iter([m["DEFAULT_PRESET_MODE"],m["CUSTOM_PRESET"]]);g["choose"]=lambda *a,**k:next(answers);g["customize"]=lambda *a,**k:None;g["load_corpus_status"]=lambda:{"domains":{}};p=m["select_plan"](c,"codex",None,False);print("available=vanilla selected=%s label=%r mode=%s mission=%s trigger=%r"%(p["preset"],p["label"],p["mode"],bool(p.get("mission")),p.get("trigger")))'
```

```text
exit 0
available=vanilla selected=vanilla label='Custom (Vanilla)' mode=builder mission=False trigger=None
```

Proposed fix: never use a routed preset as Custom’s arbitrary fallback. Synthesize a builder baseline or refuse by name when no non-routed baseline exists.

Missed check: `launcher_module_api` covers the no-builder fallback only with Vanilla, not a routed preset.

### 6. Medium — Save As changes shipped `deep-review` on the inactive host

[agent-launch.toml:216](/private/tmp/fix-tree/launch/agent-launch.toml:216), [agent-launch.py:3732](/private/tmp/fix-tree/launch/agent-launch.py:3732), [agent-launch.py:3824](/private/tmp/fix-tree/launch/agent-launch.py:3824), [agent-launch.py:5024](/private/tmp/fix-tree/launch/agent-launch.py:5024)

What it says: `frontier_effort` supports a host map, and Save As writes every inactive host back as authored.

What it does: the plan carries raw `tier_overrides`, but not the raw host-map `frontier_effort`. Saving shipped `deep-review` from Claude changes the inactive Codex effort from `ultra` to its `max` default.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib,copy,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));src=m["build_plan"](c,"codex","deep-review");active=m["build_plan"](c,"claude","deep-review");f,o,r=m["preset_from_plan"](active,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];c2=copy.deepcopy(c);c2["presets"]["saved"]=saved;got=m["build_plan"](c2,"codex","saved");print("authoring=shipped-frontier-map source_codex=%s saved_codex=%s saved_frontier_effort=%r saved_overrides=%r"%(m["tier_effort"](src,"frontier"),m["tier_effort"](got,"frontier"),saved.get("frontier_effort"),saved.get("tier_overrides")))'
```

```text
exit 0
authoring=shipped-frontier-map source_codex=ultra saved_codex=max saved_frontier_effort=None saved_overrides=None
```

Control — same values authored through the supported `tier_overrides` home:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib,copy,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));p=c["presets"]["deep-review"];v=p.pop("frontier_effort");p["tier_overrides"]={h:{"frontier":{"effort":e}} for h,e in v.items()};src=m["build_plan"](c,"codex","deep-review");active=m["build_plan"](c,"claude","deep-review");f,o,r=m["preset_from_plan"](active,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];c2=copy.deepcopy(c);c2["presets"]["saved"]=saved;got=m["build_plan"](c2,"codex","saved");print("authoring=equivalent-tier-overrides source_codex=%s saved_codex=%s saved_frontier_effort=%r saved_overrides=%r"%(m["tier_effort"](src,"frontier"),m["tier_effort"](got,"frontier"),saved.get("frontier_effort"),saved.get("tier_overrides")))'
```

```text
exit 0
authoring=equivalent-tier-overrides source_codex=ultra saved_codex=ultra saved_frontier_effort=None saved_overrides={'codex': {'frontier': {'effort': 'ultra'}}}
```

Proposed fix: carry the raw `frontier_effort` authoring value in the plan and either re-emit it or losslessly normalize every host entry into `tier_overrides.<host>.frontier.effort`.

Missed check: `preset_save_round_trips` exercises `deep-review` on both hosts but compares only the same host that performed the save.

### 7. Medium — a display sentinel can erase a selected method from coverage

[agent-launch.py:815](/private/tmp/fix-tree/launch/agent-launch.py:815), [agent-launch.py:2048](/private/tmp/fix-tree/launch/agent-launch.py:2048), [agent-launch.py:2116](/private/tmp/fix-tree/launch/agent-launch.py:2116)

What it says: every nonempty optional method ID except reserved `panel` is supported; verification returns one verdict per selected method plus diagnostics for foreign receipts.

What it does: malformed receipts use the display label `<unnamed>`, and that label is also the dictionary key. A valid selected method actually named `<unnamed>` is replaced by the malformed receipt’s foreign verdict, reducing coverage from `0/1` to `0/0`.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));auth=m["parse_review_block"]({"base":{"provider":"anthropic","tier":"frontier"},"methods":{"<unnamed>":{"provider":"openai","tier":"frontier"}}},c,"probe");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row=m["ReviewMethodReport"]("<unnamed>",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",C);report=m["ReviewReport"](row,(),"perspective_floor");bundle={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":["not-a-table"]};v,vs=m["verify_review_receipts"](report,bundle,{"<unnamed>":C});print("authored_ids=%r selected_rows=1 verdicts=%d"%(list(auth.methods),len(vs)));print(m["render_receipt_verdicts"](v,vs))'
```

```text
exit 0
authored_ids=['<unnamed>'] selected_rows=1 verdicts=1
Review achievement (achievement=none [0/0 evidenced], achieved_grade=UNKNOWN_UNTIL_RECEIPTS, availability=projected — launch-time projection, unchanged by verification)
  <unnamed>: PROPOSED — not a table
```

Control — ordinary supported method ID:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));auth=m["parse_review_block"]({"base":{"provider":"anthropic","tier":"frontier"},"methods":{"probe":{"provider":"openai","tier":"frontier"}}},c,"probe");C={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"};row=m["ReviewMethodReport"]("probe",m["STATUS_OK"],"perspective_floor","","model","high","openai","exec","",C);report=m["ReviewReport"](row,(),"perspective_floor");bundle={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":["not-a-table"]};v,vs=m["verify_review_receipts"](report,bundle,{"probe":C});print("authored_ids=%r selected_rows=1 verdicts=%d"%(list(auth.methods),len(vs)));print(m["render_receipt_verdicts"](v,vs))'
```

```text
exit 0
authored_ids=['probe'] selected_rows=1 verdicts=2
Review achievement (achievement=none [0/1 evidenced], achieved_grade=UNKNOWN_UNTIL_RECEIPTS, availability=projected — launch-time projection, unchanged by verification)
  <unnamed>: PROPOSED — not a table
  probe: PROPOSED — no receipt was supplied
```

Proposed fix: keep selected verdicts in a method-identity map and foreign diagnostics in a separate ordered collection keyed by input index or dispatch ID. Rendered labels must not serve as identity.

Missed check: `launcher_receipts` tests one foreign receipt but never collides its label with a selected method ID.

### 8. Medium — the setup panel still presents inactive child bindings as current

[agent-launch.py:3017](/private/tmp/fix-tree/launch/agent-launch.py:3017), [agent-launch.py:3041](/private/tmp/fix-tree/launch/agent-launch.py:3041), [agent-launch.py:7104](/private/tmp/fix-tree/launch/agent-launch.py:7104)

What it says: the setup panel is the “Current setup,” and its own line says delegation is off.

What it does: `setup_summary_lines` unconditionally prints every tier binding, while argv projects no child bindings. The round-20 fix covered `print_summary` but not this TUI/custom twin.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");g=m["select_plan"].__globals__;g["customize"]=lambda *a,**k:None;c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));p=m["select_plan"](c,"codex","solo",True);lines=m["setup_summary_lines"](p);argv=m["project_args"](p,False);children=[t.upper() for t in m["TIER_ORDER"] if t!=p["main_tier"] and any(x.startswith(f"{t.upper():<10} ") for x in lines)];print("preset=%s delegation=%s setup_child_rows=%r argv_has_child_bindings=%s"%(p["preset"],p["delegation"],children,any(x.startswith("agents.") for x in argv)))'
```

```text
exit 0
preset=solo delegation=False setup_child_rows=['FRONTIER', 'WORKHORSE', 'SWEEP'] argv_has_child_bindings=False
```

Control:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib;m=runpy.run_path("launch/agent-launch.py");g=m["select_plan"].__globals__;g["customize"]=lambda *a,**k:None;c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));p=m["select_plan"](c,"codex","balanced",True);lines=m["setup_summary_lines"](p);argv=m["project_args"](p,False);children=[t.upper() for t in m["TIER_ORDER"] if t!=p["main_tier"] and any(x.startswith(f"{t.upper():<10} ") for x in lines)];print("preset=%s delegation=%s setup_child_rows=%r argv_has_child_bindings=%s"%(p["preset"],p["delegation"],children,any(x.startswith("agents.") for x in argv)))'
```

```text
exit 0
preset=balanced delegation=True setup_child_rows=['FRONTIER', 'WORKHORSE', 'SWEEP'] argv_has_child_bindings=True
```

Proposed fix: make `setup_summary_lines` use the same delegation branch as `print_summary`: emit one explicit inactive-child line, or omit child rows with an inactivity qualifier.

Missed check: `launcher_delegation_clause` asserts `print_summary`, not `setup_summary_lines`; `launcher_module_api` inspects the setup panel only for the main-tier label.

### 9. Medium — malformed inactive tier overrides are silently deleted on Save As

[agent-launch.py:3824](/private/tmp/fix-tree/launch/agent-launch.py:3824), [agent-launch.py:5045](/private/tmp/fix-tree/launch/agent-launch.py:5045)

What it says: the raw inactive-host overrides are carried so “every other host is written back as authored.”

What it does: an inactive-host scalar is accepted by the active-host plan but filtered out with `isinstance(block, dict)` during save. No refusal fires; the host disappears.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["solo"]["tier_overrides"]={"codex":{"workhorse":{"effort":"low"}},"claude":"not-a-table"};p=m["build_plan"](c,"codex","solo");f,o,r=m["preset_from_plan"](p,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];print("inactive_source=%r saved_hosts=%r"%(p["tier_overrides"]["claude"],sorted(saved.get("tier_overrides",{}))))'
```

```text
exit 0
inactive_source='not-a-table' saved_hosts=['codex']
```

Control — valid inactive-host table:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));c["presets"]["solo"]["tier_overrides"]={"codex":{"workhorse":{"effort":"low"}},"claude":{"workhorse":{"effort":"high"}}};p=m["build_plan"](c,"codex","solo");f,o,r=m["preset_from_plan"](p,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"];print("inactive_source=%r saved_hosts=%r"%(p["tier_overrides"]["claude"],sorted(saved.get("tier_overrides",{}))))'
```

```text
exit 0
inactive_source={'workhorse': {'effort': 'high'}} saved_hosts=['claude', 'codex']
```

A nested scalar reaches the adjacent serializer as raw `AttributeError` at line 5081, so neither inactive shape has the review-arm serializer’s named error boundary.

Proposed fix: stop filtering inactive blocks. Validate host, tier, and binding tables during serialization and raise `LaunchError` naming the exact inactive entry.

Missed check: `preset_save` tests only structurally valid inactive overrides.

### 10. Medium — “verbatim” inactive review arms lose top-level fields

[agent-launch.py:843](/private/tmp/fix-tree/launch/agent-launch.py:843), [agent-launch.py:4969](/private/tmp/fix-tree/launch/agent-launch.py:4969), [agent-launch.py:5087](/private/tmp/fix-tree/launch/agent-launch.py:5087)

What it says: inactive review arms are raw so Save writes them back “verbatim,” with no reserialization drift.

What it does: `review_block_from_plan` carries the raw arm, but `render_preset_block` serializes only `base` and `methods`. Any other top-level field silently vanishes.

Mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));arm=c["presets"]["balanced"]["review"]["hosts"]["codex"];arm["future_metadata"]="keep-me";p=m["build_plan"](c,"claude","balanced");f,o,r=m["preset_from_plan"](p,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"]["review"]["hosts"]["codex"];print("source_metadata=%r saved_metadata=%r saved_base=%r"%(arm["future_metadata"],saved.get("future_metadata"),saved.get("base")))'
```

```text
exit 0
source_metadata='keep-me' saved_metadata=None saved_base={'provider': 'anthropic', 'tier': 'helm'}
```

Control — the currently recognized arm shape round-trips:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import runpy,pathlib,tomllib;m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));arm=c["presets"]["balanced"]["review"]["hosts"]["codex"];p=m["build_plan"](c,"claude","balanced");f,o,r=m["preset_from_plan"](p,c,"saved");saved=tomllib.loads(m["render_preset_block"]("saved",f,o,r))["presets"]["saved"]["review"]["hosts"]["codex"];print("source_base=%r saved_base=%r exact_supported_shape=%s"%(arm.get("base"),saved.get("base"),arm==saved))'
```

```text
exit 0
source_base={'provider': 'anthropic', 'tier': 'helm'} saved_base={'provider': 'anthropic', 'tier': 'helm'} exact_supported_shape=True
```

Proposed fix: serialize untouched inactive arms generically and recursively, or refuse unsupported keys by name. The current combination—promising verbatim preservation while silently projecting only known keys—is the unsafe middle.

Missed check: `launcher_review_save` covers scalar/table shapes and empty arms, but no extra raw top-level field.

## Void readings

- Execution-clause drift did not reproduce. Across all 11 allowed execution values, the value rendered by `execution_clause` matched the value consumed by `project_args`; zero mismatches. Representative outputs:

```text
value=auto clause_mentions=True argv_value=auto
value=plan clause_mentions=True argv_value=plan
```

- The repaired `no_review_route` twin held for both family values:

```text
family=cross effective=[] contract_no_route=True summary_has_review_on=False
family=same effective=[] contract_no_route=True summary_has_review_on=False
```

- I did not count all-pass seed/swap omission at fold time. That is the behavior explicitly retained by D-20260816-c0067f and D-20260816-0ed011. Finding 2 is narrower: a mixed group changes meaning solely when its input order changes.

## Not examined:

`compose/corpus-state.py`; the wizard trial-load path; actual Textual screen rendering beyond its pure setup-summary producer; real `save_preset` disk replacement/locking; filesystem-backed `--emit-receipt` and `--fold-receipts`; the full parity suite; host CLI interpretation or execution; credentials; and any access-control conclusion. The out-of-scope delegated probe was discarded.
