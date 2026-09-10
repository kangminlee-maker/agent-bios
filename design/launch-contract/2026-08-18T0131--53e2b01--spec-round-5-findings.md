---
created_at: 2026-08-18T01:31:00+09:00
head: 53e2b01
kind: review
---

# Spec round 5 — the code held against the third revision (raw findings)

Fifth round under the spec instrument, against `…T2310--11ed16b--review-evidence-invariants.md`.
Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`; 276,354
tokens. ONE code violation (13 → 6 → 6 → 3 → 1; L7: an MCP capability rename changes argv
with a byte-identical contract) and two specification defects (D4 self-contradiction on
packet binding vs disclosure; S4 universal saveability vs S6); all three round-4 closures
replayed and held. Verbatim below.

Reviewed clean branch `review-round-20` at `53e2b01`. Result: one code violation and two specification defects. All three round‑4 closures held.

## Findings

### High — L7: MCP registration identity changes argv but not the contract

File/functions: [run_contract](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:8017), [review_mcp_servers](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:8235), `project_args`.

A selected MCP capability’s name becomes the backend’s server namespace, but neither the human contract nor `ReviewPlan/v1` records it. Renaming only the capability therefore produces different argv and a byte-identical contract—the exact L7 violation.

Mutation:

```sh
python3 -c $'import copy,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
a=copy.deepcopy(c);a["capabilities"]["ultracode"]["offers"][0]["adapter"]="mcp-stdio-v1"
b=copy.deepcopy(a);b["capabilities"]["alias"]=copy.deepcopy(b["capabilities"]["ultracode"]);b["review_methods"]["ultracode"]["capability"]="alias"
pa=m["build_plan"](a,"codex","deep-review");pb=m["build_plan"](b,"codex","deep-review")
aa=m["project_args"](pa,materialize_agents=False);ab=m["project_args"](pb,materialize_agents=False)
print("contracts_equal="+str(m["run_contract"](pa)==m["run_contract"](pb))+" argv_differ="+str(aa!=ab))
print("a="+repr([x for x in aa if "mcp_servers." in x]))
print("b="+repr([x for x in ab if "mcp_servers." in x]))'
```

```text
contracts_equal=True argv_differ=True
a=['mcp_servers.ultracode.enabled=true', 'mcp_servers.ultracode.command="/Users/kangmin/.local/bin/claude"', 'mcp_servers.ultracode.args=["mcp"]']
b=['mcp_servers.alias.enabled=true', 'mcp_servers.alias.command="/Users/kangmin/.local/bin/claude"', 'mcp_servers.alias.args=["mcp"]']
```

Nearest control—same capability identity, changed resolved command:

```sh
python3 -c $'import copy,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
a=copy.deepcopy(c);a["capabilities"]["ultracode"]["offers"][0]["adapter"]="mcp-stdio-v1"
b=copy.deepcopy(a);b["capabilities"]["ultracode"]["command"]="/bin/echo"
pa=m["build_plan"](a,"codex","deep-review");pb=m["build_plan"](b,"codex","deep-review")
aa=m["project_args"](pa,materialize_agents=False);ab=m["project_args"](pb,materialize_agents=False)
print("contracts_equal="+str(m["run_contract"](pa)==m["run_contract"](pb))+" argv_differ="+str(aa!=ab))
print("a="+repr([x for x in aa if "mcp_servers." in x]))
print("b="+repr([x for x in ab if "mcp_servers." in x]))'
```

```text
contracts_equal=False argv_differ=True
a=['mcp_servers.ultracode.enabled=true', 'mcp_servers.ultracode.command="/Users/kangmin/.local/bin/claude"', 'mcp_servers.ultracode.args=["mcp"]']
b=['mcp_servers.ultracode.enabled=true', 'mcp_servers.ultracode.command="/bin/echo"', 'mcp_servers.ultracode.args=["mcp"]']
```

Proposed fix: concept-surface preserving. Compute the ordered MCP registration projection once and make both `run_contract` and backend argv consume that exact `(name, command, args)` value. Do not independently reconstruct the names.

Missed check: [launcher_review_contract](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:2519) varies method removal, effort, and command, but keeps the capability identity fixed. Add same-command/capability-rename twins for both hosts.

## Round-4 closure replay

| Closure | Mutation now | Control now | Twins reached |
|---|---|---|---|
| L2/L3/V2 evidence grammar | Named `LaunchError` for `evidence=('',)` | `achievement=complete`, `verified` | Both parsers, both adjudication sides, `None`, empty names, and non-map outer declarations |
| F2 marker presence | Empty-present versus omitted seed refused on “present at all” | Both omitted accepted | Both orders, `swap_group`, reportedness door, uniform-falsey control |
| V2/V7 controls registry | `required_controls=None` refused by named `LaunchError` | Valid map completes | List-shaped controls registry and analogous malformed evidence registry |

The four `evidence_snapshot_reason` readers are covered: `parse_capability_offers`, `_row_from_v1`, the in-process plan row, and the current evidence declaration.

## Spec defects

### High — D4 contradicts itself about packet binding

[D4](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T2310--11ed16b--review-evidence-invariants.md:154) says the anchor “must be bound to real bytes” and verification “must receive” the packet, then explicitly permits no packet with disclosure. Its checklist separately calls a digest bound to no bytes a violation.

Mutation—canonical verification without a packet:

```sh
python3 -c $'import contextlib,hashlib,io,json,pathlib,re,runpy,types
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));q=m["build_plan"](c,"codex","balanced")["review_report"];row=q.base
h=lambda x:hashlib.sha256(x.encode()).hexdigest();contract=json.dumps(m["review_plan_v1"](q));packet_text=m["REVIEW_PLAN_MARKER"]+contract;packet=h(packet_text);passes=[h(str(i)) for i in range(3)]
receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":packet,"result_sha256":passes[0],"provider":row.provider,"model":row.model,"effort":row.effort,"exit_status":0,"passes":passes,"ordering_seed":"seed","swap_group":"arm"}
bundle={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":packet,"main_dispatch_id":"main","receipts":[receipt]};texts={"plan":contract,"bundle":json.dumps(bundle),"packet":packet_text}
class P:
 def __init__(self,value):self.value=str(value)
 def expanduser(self):return self
 def read_text(self,encoding="utf-8"):return texts[self.value]
 def __str__(self):return self.value
g=m["verify_receipts_command"].__globals__;g["pathlib"]=types.SimpleNamespace(Path=P);g["load_config"]=lambda _:c;g["open"]=lambda path,mode="rb":io.BytesIO(packet_text.encode())
s=io.StringIO()
with contextlib.redirect_stdout(s):status=m["verify_receipts_command"]("plan","bundle","config",None)
output=s.getvalue();achievement=re.search(r"achievement=([^ ]+)",output).group(1);line=[x.strip() for x in output.splitlines() if x.strip().startswith("packet_binding=")][0]
print("exit="+str(status)+" achievement="+achievement);print(line)'
```

```text
exit=0 achievement=complete
packet_binding=none — no packet artifact was supplied, so packet_sha256 was compared between the bundle and its own receipts and is bound to no bytes
```

Control—with an independently read packet:

```sh
# Same probe setup as above; final call changes from packet_path=None to packet_path="packet".
python3 -c $'import contextlib,hashlib,io,json,pathlib,re,runpy,types
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"));q=m["build_plan"](c,"codex","balanced")["review_report"];row=q.base
h=lambda x:hashlib.sha256(x.encode()).hexdigest();contract=json.dumps(m["review_plan_v1"](q));packet_text=m["REVIEW_PLAN_MARKER"]+contract;packet=h(packet_text);passes=[h(str(i)) for i in range(3)]
receipt={"schema":m["RECEIPT_SCHEMA"],"method_id":"panel","dispatch_id":"child","packet_sha256":packet,"result_sha256":passes[0],"provider":row.provider,"model":row.model,"effort":row.effort,"exit_status":0,"passes":passes,"ordering_seed":"seed","swap_group":"arm"}
bundle={"schema":m["RECEIPT_BUNDLE_SCHEMA"],"packet_sha256":packet,"main_dispatch_id":"main","receipts":[receipt]};texts={"plan":contract,"bundle":json.dumps(bundle),"packet":packet_text}
class P:
 def __init__(self,value):self.value=str(value)
 def expanduser(self):return self
 def read_text(self,encoding="utf-8"):return texts[self.value]
 def __str__(self):return self.value
g=m["verify_receipts_command"].__globals__;g["pathlib"]=types.SimpleNamespace(Path=P);g["load_config"]=lambda _:c;g["open"]=lambda path,mode="rb":io.BytesIO(packet_text.encode())
s=io.StringIO()
with contextlib.redirect_stdout(s):status=m["verify_receipts_command"]("plan","bundle","config","packet")
output=s.getvalue();achievement=re.search(r"achievement=([^ ]+)",output).group(1);line=[x.strip() for x in output.splitlines() if x.strip().startswith("packet_binding=")][0]
print("exit="+str(status)+" achievement="+achievement);print(line)'
```

```text
exit=0 achievement=complete
packet_binding=bytes — packet_sha256 was recomputed from a packet artifact read by this process
```

Minimal specification fix: choose one falsifiable rule. The concept-preserving default matching current behavior is: byte binding is established only when `--packet` is supplied; without it, artifact-internal ACHIEVED is permitted but must disclose `packet_binding=none`. Amend the checklist accordingly. If “must” is intended literally, missing `--packet` must instead force PROPOSED/nonzero.

Missed check: `launcher_receipts` checks the no-packet disclosure but not its exit/achievement policy, so it cannot decide between the two readings.

### Medium — S4’s universal saveability contradicts S6

[S4](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T2310--11ed16b--review-evidence-invariants.md:258) says every accepted profile remains saveable. [S6](/Users/kangmin/Documents/agent-bios-fix-tree/design/launch-contract/2026-08-17T2310--11ed16b--review-evidence-invariants.md:276) requires mission/trigger and routed plans to be refused.

Mutation:

```sh
python3 -c $'import runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](m["pathlib"].Path("launch/agent-launch.toml"));p=m["build_plan"](c,"codex","session-distill")
class Reached(Exception):pass
m["save_preset"].__globals__["preset_from_plan"]=lambda *a: (_ for _ in ()).throw(Reached("passed S6"))
try:m["save_preset"](p,c,m["pathlib"].Path("unused.toml"),"specprobe")
except Exception as x:print("plan=accepted save="+type(x).__name__+":"+str(x))'
```

```text
plan=accepted save=LaunchError:this setup carries a mission and a trigger, which a saved preset cannot reproduce — saving it would create an entry that looks the same and starts an ordinary session. Launch it from its own menu entry instead.
```

Control:

```sh
python3 -c $'import runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](m["pathlib"].Path("launch/agent-launch.toml"));p=m["build_plan"](c,"codex","solo")
class Reached(Exception):pass
m["save_preset"].__globals__["preset_from_plan"]=lambda *a: (_ for _ in ()).throw(Reached("passed S6"))
try:m["save_preset"](p,c,m["pathlib"].Path("unused.toml"),"specprobe")
except Exception as x:print("plan=accepted save="+type(x).__name__+":"+str(x))'
```

```text
plan=accepted save=Reached:passed S6
```

Minimal specification fix: make S4 say, “Except for S6’s routed-content refusals, every non-routed profile the launcher accepts remains saveable; any other refusal names the genuinely unwritable entry.” Change the checklist to “a non-routed launchable profile refused.”

The runtime is internally consistent: [save_preset](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:6473) and `preset_save_round_trips` deliberately enforce S6. The defect is in the specification.

## Void readings

None. A malformed hand-built `ReviewMethodReport` serializer probe was excluded as outside the specified resolved-report producer boundary; the canonical parser refused it by name.

## Denominator

- Probed: all 33 invariants—L1–L8, D1–D8, F1–F4, V1–V7, S1–S6.
- Read only: none.
- Both configured `codex` and `claude` dry-runs exited 0.
- Relevant `gates/check_parity.py` checks were inspected; the full parity umbrella was not run.
- Worktree remained clean at `53e2b01`.

## Not examined

- The specification’s explicitly excluded honesty, semantic-aggregation, and review-quality claims.
- Q1–Q9 as defects.
- Host CLI execution.
- Access-control surfaces or runtime outside the named subsystem.
- Real concurrent filesystem interleavings; D8/S5 used bounded failure-injection and post-failure-residue probes.
