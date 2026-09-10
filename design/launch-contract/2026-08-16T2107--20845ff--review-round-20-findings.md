---
created_at: 2026-08-16T21:07:00+09:00
head: 20845ff
kind: review
---

# Round 20 — cross-family review of the launcher after rounds 18–19 (raw findings)

Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`, packet on stdin (this session's `r20b-packet.md`: launcher only, host CLIs not to be invoked — the first round-20 dispatch was cut off by the content filter while probing `codex features list`); 438,986 tokens. Eight findings admitted (4 High, 3 Medium, 1 Medium-low); corpus-state and the wizard trial path again unreached (read-only sandbox, no writable scratch). Verbatim below.

Reviewed `review-round-20` at `20845ff128e39f066013eea9cdb670d52c1988f0`. Eight findings survived 11 discriminating mutation/control pairs. All commands ran from `/tmp/fix-tree`; no files changed and no host CLI was invoked.

I inspected all 14 named launcher functions, exercised the save renderer, composable schema, receipt verifier/folder, forwarding, summary, custom loop, and fallback routes. I ran `check_parity.py --list` and read the relevant checks; I did not run the write-heavy fixture suite.

## Findings

### 1. High — direct receipt verification accepts bundles missing both identity anchors

[agent-launch.py:1881](/private/tmp/fix-tree/launch/agent-launch.py:1881), [agent-launch.py:1893](/private/tmp/fix-tree/launch/agent-launch.py:1893), [agent-launch.py:1963](/private/tmp/fix-tree/launch/agent-launch.py:1963), [agent-launch.py:2243](/private/tmp/fix-tree/launch/agent-launch.py:2243)

What it says: a receipt must prove a fresh dispatch that consumed the declared packet. `fold_receipts_command` calls `main_dispatch_id` mandatory because otherwise the same-context check cannot fire.

What it does: `verify_review_receipts` validates only the bundle schema and `receipts` list. With no `main_dispatch_id`, the equality at line 1886 can never match. If both bundle and receipt omit `packet_sha256`, `None == None` passes the packet check. `verify_receipts_command` passes the bundle directly to this function.

Mutation — missing main dispatch ID:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe","OK","perspective_floor","","model","high","openai","exec","",c); report=RR(row,(),"perspective_floor"); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"main","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; bundle={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","receipts":[receipt]}; verified,verdicts=m["verify_review_receipts"](report,bundle,{"probe":c}); print(m["render_receipt_verdicts"](verified,verdicts))'
```

```text
Review achievement (achievement=complete [1/1 evidenced], achieved_grade=perspective_floor, availability=projected — launch-time projection, unchanged by verification)
  probe: ACHIEVED/perspective_floor — verified
```

Control — same bundle with the main ID:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe","OK","perspective_floor","","model","high","openai","exec","",c); report=RR(row,(),"perspective_floor"); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"main","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; bundle={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]}; verified,verdicts=m["verify_review_receipts"](report,bundle,{"probe":c}); print(m["render_receipt_verdicts"](verified,verdicts))'
```

```text
Review achievement (achievement=none [0/1 evidenced], achieved_grade=UNKNOWN_UNTIL_RECEIPTS, availability=projected — launch-time projection, unchanged by verification)
  probe: PROPOSED — was produced in the main session's own context, which is not a review
```

The packet twin is also open. Omitting `packet_sha256` from both records produced `ACHIEVED ... verified`; adding only the bundle hash produced:

```text
probe: PROPOSED — hashes a different packet than the one the plan declared
```

Proposed fix: validate a closed bundle schema before examining receipts. Require non-empty `main_dispatch_id` and `packet_sha256`, and require every receipt to carry its packet hash.

Missed check: [`launcher_receipts`](/private/tmp/fix-tree/gates/check_parity.py:3340). Its bundle helper always supplies both fields; it tests present-but-equal main IDs and one-sided packet mismatches, never deleted anchors.

### 2. High — folding validates pass identity and payload only according to position/count

[agent-launch.py:2178](/private/tmp/fix-tree/launch/agent-launch.py:2178), [agent-launch.py:2189](/private/tmp/fix-tree/launch/agent-launch.py:2189), [agent-launch.py:2191](/private/tmp/fix-tree/launch/agent-launch.py:2191), [agent-launch.py:2221](/private/tmp/fix-tree/launch/agent-launch.py:2221)

What it says: every pass’s dispatch identity is judged at fold time, and `passes` evidences the individual process results.

What it does:

- A singleton group returns before any dispatch-ID check.
- For multiple receipts, only the first receipt becomes the adjudicated record. Later results are copied into `passes` if merely truthy; `EMPTY_SHA256` is truthy and later receipts do not independently pass `_receipt_reason`.

Singleton mutation/control:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); base={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; main=base|{"dispatch_id":"main"}; child=base|{"dispatch_id":"child"}; one=m["_merge_method_passes"]("probe",[main],"main"); print("one=RETURNED dispatch=%s" % one["dispatch_id"]);
try: m["_merge_method_passes"]("probe",[main,child],"main")
except m["LaunchError"] as exc: print("two=REFUSED %s" % exc)'
```

```text
one=RETURNED dispatch=main
two=REFUSED a receipt for 'probe' was produced in the main session's own context ('main'), which is not a review pass
```

The later verifier can reject the emitted singleton bundle, but the claimed fold-time refusal did not happen.

Pass-payload mutation — good receipt first, empty receipt second:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("panel","OK","perspective_floor","","model","high","openai","exec","",c); report=RR(row,(),"perspective_floor"); base={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0}; good=base|{"dispatch_id":"child-1","result_sha256":"good-result"}; empty=base|{"dispatch_id":"child-2","result_sha256":m["EMPTY_SHA256"]}; merged=m["_merge_method_passes"]("panel",[good,empty],"main"); verified,verdicts=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"panel":c}); print("top=%s passes=%r" % (merged["result_sha256"],merged["passes"])); print(m["render_receipt_verdicts"](verified,verdicts))'
```

```text
top=good-result passes=['e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'good-result']
Review achievement (achievement=complete [1/1 evidenced], ...)
  panel: ACHIEVED/perspective_floor — verified
```

Control — exact same receipts reversed:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; c={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("panel","OK","perspective_floor","","model","high","openai","exec","",c); report=RR(row,(),"perspective_floor"); base={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","packet_sha256":"packet","provider":"openai","model":"model","effort":"high","exit_status":0}; good=base|{"dispatch_id":"child-1","result_sha256":"good-result"}; empty=base|{"dispatch_id":"child-2","result_sha256":m["EMPTY_SHA256"]}; merged=m["_merge_method_passes"]("panel",[empty,good],"main"); verified,verdicts=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[merged]},{"panel":c}); print("top=%s passes=%r" % (merged["result_sha256"],merged["passes"])); print(m["render_receipt_verdicts"](verified,verdicts))'
```

```text
top=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 passes=['e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'good-result']
Review achievement (achievement=none [0/1 evidenced], ...)
  panel: PROPOSED — records an empty result, so nothing was actually reviewed
```

Proposed fix: validate every raw receipt before the singleton return or merge. Apply dispatch, result, evidence, seed, and swap requirements per pass; then construct the folded representation.

Missed check: [`launcher_receipt_fold`](/private/tmp/fix-tree/gates/check_parity.py:3741). It tests only two-receipt identity failures and clean, non-empty payloads. [`launcher_receipts`](/private/tmp/fix-tree/gates/check_parity.py:3340) tests an empty top-level receipt, not an empty later pass.

### 3. High — `controls: null` bypasses the recorded-controls drift check

[agent-launch.py:1823](/private/tmp/fix-tree/launch/agent-launch.py:1823), [agent-launch.py:1983](/private/tmp/fix-tree/launch/agent-launch.py:1983)

What it says: every plan row carries the controls declared at launch; a row without that snapshot is refused, and the snapshot is held against the current registry.

What it does: `_row_from_v1` checks only that the key exists. `controls: null` becomes `None`, and line 1989 deliberately skips comparison for `None`. A former two-pass plan can therefore be verified under a current one-pass registry.

Mutation:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; current={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe","OK","perspective_floor","","model","high","openai","exec","",None); report=m["review_plan_from_v1"](m["review_plan_v1"](RR(row,(),"perspective_floor"))); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0}; verified,verdicts=m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":current}); print("parsed_controls=%r" % report.base.controls); print(m["render_receipt_verdicts"](verified,verdicts))'
```

```text
parsed_controls=None
Review achievement (achievement=complete [1/1 evidenced], ...)
  probe: ACHIEVED/perspective_floor — verified
```

Control — retain the recorded two-pass snapshot:

```sh
python3 -c 'import runpy; m=runpy.run_path("launch/agent-launch.py"); R=m["ReviewMethodReport"]; RR=m["ReviewReport"]; old={"trials":2,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; current={"trials":1,"order":"fixed","swap_augmentation":False,"aggregation":"union"}; row=R("probe","OK","perspective_floor","","model","high","openai","exec","",old); report=m["review_plan_from_v1"](m["review_plan_v1"](RR(row,(),"perspective_floor"))); receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"probe","dispatch_id":"child","packet_sha256":"packet","result_sha256":"result","provider":"openai","model":"model","effort":"high","exit_status":0};
try: m["verify_review_receipts"](report,{"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":"packet","main_dispatch_id":"main","receipts":[receipt]},{"probe":current})
except m["LaunchError"] as exc: print("REFUSED: %s" % exc)'
```

```text
REFUSED: cannot adjudicate 'probe': the plan recorded controls {'trials': 2, ...} at launch and the registry now declares {'trials': 1, ...} — the descriptor changed since; re-launch or verify against the registry of the time
```

Proposed fix: require `controls` to be a correctly shaped table on every non-dropped row; allow `None` only where the row status makes controls irrelevant. Compare selected rows unconditionally.

Missed check: [`launcher_receipts`](/private/tmp/fix-tree/gates/check_parity.py:3340) removes the key but never tests the key present with `null`.

### 4. High — TOML whitespace bypasses the forwarded-override collision guard

[agent-launch.py:6534](/private/tmp/fix-tree/launch/agent-launch.py:6534), [agent-launch.py:6682](/private/tmp/fix-tree/launch/agent-launch.py:6682), [agent-launch.py:6718](/private/tmp/fix-tree/launch/agent-launch.py:6718), [agent-launch.py:7240](/private/tmp/fix-tree/launch/agent-launch.py:7240)

What it says: every forwarded option that overrides a projected value is refused, ensuring the contract describes the actual argv.

What it does: `config_pairs` compares the raw text before `=`. Whitespace that is insignificant to TOML becomes part of the key used by `overlaps`, so the override is appended last.

Mutation:

```sh
python3 launch/agent-launch.py --config launch/agent-launch.toml --no-tui --preset balanced --yes --dry-run codex -- '--config=model_reasoning_effort = "low"'
```

Exit `0`. Relevant output:

```text
Overrides      forwarded backend args appended last; a projected option cannot be overridden
```

The argv contains the projected pair `-c`, `model_reasoning_effort="xhigh"` and ends with:

```text
--config=model_reasoning_effort = "low"
```

Control:

```sh
python3 launch/agent-launch.py --config launch/agent-launch.toml --no-tui --preset balanced --yes --dry-run codex -- '--config=model_reasoning_effort="low"'
```

Exit `2`:

```text
agent-launch: forwarded argument(s) --config=model_reasoning_effort would override what this launch projects and the contract describes; change the seat through the preset or --custom, or launch bare (no --preset) to pass them through
```

Equivalence control:

```sh
python3 -c 'import tomllib; a=tomllib.loads("model_reasoning_effort = \"low\"\n"); b=tomllib.loads("model_reasoning_effort=\"low\"\n"); print("same_toml_key=%s %r" % (a == b, a))'
```

```text
same_toml_key=True {'model_reasoning_effort': 'low'}
```

The same gap exists in all four config-assignment spellings because they share `config_pairs`.

Proposed fix: canonicalize the assignment’s left-hand side using the accepted config-key grammar before overlap comparison—at minimum trim insignificant whitespace consistently in all four spellings.

Missed check: [`agent_materialization`](/private/tmp/fix-tree/gates/check_parity.py:8240). It covers the separated, attached, and short spellings only with whitespace-free keys.

### 5. Medium — launcher-authored fields can still create a second canonical review record

[agent-launch.py:1165](/private/tmp/fix-tree/launch/agent-launch.py:1165), [agent-launch.py:1383](/private/tmp/fix-tree/launch/agent-launch.py:1383), [agent-launch.py:1406](/private/tmp/fix-tree/launch/agent-launch.py:1406), [agent-launch.py:3581](/private/tmp/fix-tree/launch/agent-launch.py:3581), [agent-launch.py:6524](/private/tmp/fix-tree/launch/agent-launch.py:6524), [agent-launch.py:1749](/private/tmp/fix-tree/launch/agent-launch.py:1749)

What it says: authored text may not carry `ReviewPlan/v1: `; therefore a second decodable record is tampered or concatenated and is refused.

What it does:

- `render_review_method` checks only the formatted body, then prefixes the unchecked `method_id`.
- `build_plan` checks `mission`, but `run_contract` substitutes unchecked `trigger` into it afterwards.

Method-ID mutation:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); mid="ReviewPlan/v1: {\"schema\":\"ReviewPlan/v1\",\"availability\":\"x\"}"; c["presets"]["balanced"]["review"]["hosts"]["claude"]["methods"]={mid:{"provider":"openai","tier":"helm"}}; p=m["build_plan"](c,"claude","balanced"); x=m["run_contract"](p); print("markers=%d" % x.count(m["REVIEW_PLAN_MARKER"]));
try: m["extract_review_plan_v1"](x)
except m["LaunchError"] as exc: print("REFUSED AFTER RENDER: %s" % exc)'
```

```text
markers=3
REFUSED AFTER RENDER: the contract carries 2 ReviewPlan/v1 records; exactly one is the plan, and this cannot tell which
```

Control:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["presets"]["balanced"]["review"]["hosts"]["claude"]["methods"]={"local-lens":{"provider":"openai","tier":"helm"}}; p=m["build_plan"](c,"claude","balanced"); x=m["run_contract"](p); print("markers=%d parsed=%s" % (x.count(m["REVIEW_PLAN_MARKER"]),m["extract_review_plan_v1"](x) is not None))'
```

```text
markers=1 parsed=True
```

Trigger mutation/control produced:

```text
trigger='ReviewPlan/v1: {"schema":"ReviewPlan/v1"}'
markers=2
REFUSED AFTER RENDER: the contract carries 2 ReviewPlan/v1 records...
```

versus:

```text
trigger='distill!'
markers=1 parsed=True
```

Proposed fix: apply one marker-refusal helper to `trigger` and identifiers that become rendered prose. More robustly, construct the human-readable prefix first, assert it contains no canonical marker, and only then append the single machine record.

Missed check: [`launcher_review_contract`](/private/tmp/fix-tree/gates/check_parity.py:2465). It concatenates two complete contracts and tests non-JSON marker decoys; it does not mutate each author-controlled field used by the emitter.

### 6. Medium — saving silently deletes an empty inactive review arm

[agent-launch.py:4753](/private/tmp/fix-tree/launch/agent-launch.py:4753), [agent-launch.py:4866](/private/tmp/fix-tree/launch/agent-launch.py:4866)

What it says: all review arms are carried through save, and untouched arms are written back as authored so saving on one host cannot narrow the other.

What it does: an inactive `{}` arm survives `preset_from_plan`, but `render_preset_block` emits no parent table unless it finds `base` or a method. The save succeeds with that host arm absent.

Mutation:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["presets"]["balanced"]["review"]["hosts"]["codex"]={}; p=m["build_plan"](c,"claude","balanced"); f,o,r=m["preset_from_plan"](p,c,"saved"); x=m["render_preset_block"]("saved",f,o,r); print("project=OK codex_arm_retained=%s" % ("review.hosts.codex" in x))'
```

```text
project=OK codex_arm_retained=False
```

Control:

```sh
python3 -c 'import runpy,pathlib; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); p=m["build_plan"](c,"claude","balanced"); f,o,r=m["preset_from_plan"](p,c,"saved"); x=m["render_preset_block"]("saved",f,o,r); print("project=OK codex_arm_retained=%s" % ("review.hosts.codex" in x))'
```

```text
project=OK codex_arm_retained=True
```

Proposed fix: emit an explicit parent host-arm table even when empty, or refuse a base-less arm with `LaunchError`. Do not silently omit it.

Missed check: [`launcher_review_save`](/private/tmp/fix-tree/gates/check_parity.py:4850). Its inactive-arm cases cover scalar/nested shape failures but not an empty or base-less arm.

### 7. Medium — “closed” host keys use a different host domain from the CLI

[agent-launch.py:3488](/private/tmp/fix-tree/launch/agent-launch.py:3488), [agent-launch.py:3491](/private/tmp/fix-tree/launch/agent-launch.py:3491), [agent-launch.py:7017](/private/tmp/fix-tree/launch/agent-launch.py:7017)

What it says: `codxe` can never become active, so host keys in `tier_overrides` are closed and such a typo is refused.

What it does: `build_plan` defines valid override hosts as every key in configurable `config["hosts"]`; argument parsing independently allows only `codex` and `claude`. Adding a complete `codxe` host table makes its override valid but unreachable and inert.

Mutation:

```sh
python3 -c 'import runpy,pathlib,copy; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); c["hosts"]["codxe"]=copy.deepcopy(c["hosts"]["codex"]); p=copy.deepcopy(c["presets"]["solo"]); p["tier_overrides"]={"codxe":{"workhorse":{"model":"typo-model"}}}; c["presets"]["probe"]=p; plan=m["build_plan"](c,"codex","probe"); print("build=accepted override_hosts=%r active_workhorse=%s" % (sorted(c["presets"]["probe"]["tier_overrides"]), plan["tiers"]["workhorse"]["model"]));
try: m["parse_args"](["codxe"])
except SystemExit as exc: print("select_host_status=%s" % exc.code)'
```

Relevant output:

```text
build=accepted override_hosts=['codxe'] active_workhorse=gpt-5.6-terra
argument host: invalid choice: 'codxe' (choose from codex, claude)
select_host_status=2
```

Control — same override without adding the fake host table:

```sh
python3 -c 'import runpy,pathlib,copy; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); p=copy.deepcopy(c["presets"]["solo"]); p["tier_overrides"]={"codxe":{"workhorse":{"model":"typo-model"}}}; c["presets"]["probe"]=p;
try: m["build_plan"](c,"codex","probe")
except m["LaunchError"] as exc: print("REFUSED: %s" % exc)'
```

```text
REFUSED: unknown host(s) in probe.tier_overrides: codxe; configured hosts are claude, codex
```

Proposed fix: define the launchable host set once and reuse it for argparse choices and all host-keyed preset maps.

Missed check: [`profile_errors`](/private/tmp/fix-tree/gates/check_parity.py:7624). It tests `codxe` only while the typo is absent from `config["hosts"]`.

### 8. Medium-low — delegation-off dry-run still advertises configured child bindings

[agent-launch.py:6455](/private/tmp/fix-tree/launch/agent-launch.py:6455), [agent-launch.py:6849](/private/tmp/fix-tree/launch/agent-launch.py:6849), [agent-launch.py:6893](/private/tmp/fix-tree/launch/agent-launch.py:6893)

What it says: the delegation-off contract correctly says child tiers are inactive and no child binding is projected.

What it does: `print_summary` always lists every tier and unconditionally prints `base main + native child model/effort configured`, even when argv contains no child binding.

Mutation — `solo`, delegation off:

```sh
python3 -c 'import runpy,pathlib,io; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); p=m["build_plan"](c,"codex","solo"); a=m["project_args"](p,materialize_agents=False); out=io.StringIO(); m["print_summary"](p,"codex",a,out); print(next(x.strip() for x in out.getvalue().splitlines() if "Tier authority" in x)); print("child_bindings=%s contract_says_none=%s" % (any(x.startswith("agents.") for x in a),"no child binding is" in m["run_contract"](p)))'
```

```text
Tier authority base main + native child model/effort configured
child_bindings=False contract_says_none=True
```

Control — `balanced`, delegation on:

```sh
python3 -c 'import runpy,pathlib,io; m=runpy.run_path("launch/agent-launch.py"); c=m["load_config"](pathlib.Path("launch/agent-launch.toml")); p=m["build_plan"](c,"codex","balanced"); a=m["project_args"](p,materialize_agents=False); out=io.StringIO(); m["print_summary"](p,"codex",a,out); print(next(x.strip() for x in out.getvalue().splitlines() if "Tier authority" in x)); print("child_bindings=%s contract_says_none=%s" % (any(x.startswith("agents.") for x in a),"no child binding is" in m["run_contract"](p)))'
```

```text
Tier authority base main + native child model/effort configured
child_bindings=True contract_says_none=False
```

Proposed fix: derive summary tier rows and authority wording from the same delegation branch used by `run_contract` and `project_args`.

Missed check: [`launcher_delegation_clause`](/private/tmp/fix-tree/gates/check_parity.py:3228). It compares contract and argv but never inspects `print_summary`.

## Void readings

- `--custom` legacy lowering held. The single-host mutation produced:

  ```text
  effective=same requested=cross saved=cross
  ```

  The two-host control produced:

  ```text
  effective=cross requested=cross saved=cross
  ```

  Reselecting the review no longer makes the fallback permanent.

- Cross/same fallback prose held across both delegation states:

  ```text
  family=cross delegation=False child_fallback=False no_child=True
  family=cross delegation=True  child_fallback=True  no_child=False
  family=same  delegation=False child_fallback=False no_child=True
  family=same  delegation=True  child_fallback=True  no_child=False
  ```

- The explicitly repaired marker doors themselves held. A literal instruction marker and a literal mission marker both returned named refusals:

  ```text
  template=REFUSED probe: contains 'ReviewPlan/v1: '...
  mission=REFUSED presets.solo.mission contains 'ReviewPlan/v1: '...
  ```

  The finding is confined to fields that bypass those doors.

Not examined: `compose/corpus-state.py`; the wizard trial-load path; persistent on-disk save/reload beyond the deterministic pre-write renderer; full TUI operation; actual backend dispatch; host CLIs; the explicitly excluded permission, credential, and access-control surfaces; the full write-heavy parity fixture suite.
