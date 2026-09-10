---
created_at: 2026-08-18T03:06:00+09:00
head: f50767c
kind: review
---

# Spec round 6 — the code held against the fourth revision (raw findings)

Sixth round under the spec instrument, against `…T0235--3328cb8--review-evidence-invariants.md`.
Reviewer: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort=ultra`; 258,689
tokens. TWO violations (13 → 6 → 6 → 3 → 1 → 2; both twins of round-5 shapes: the child
agent-template projection as L7's remaining uncontracted argv, and the singleton fold
omitting its pass set under F3); round-5 closure and both amendments held; no spec defects.
Verbatim below.

Reviewed clean `review-round-20` at `f50767c`. Two invariant violations survived independent challenge: one High L7 and one Medium F3. The round-5 closure held; no specification defects were confirmed.

## Findings

### High — L7: child-template projection changes argv under a byte-identical contract

Files/functions: [codex_agent_configs](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:7790), [run_contract](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:8017), [project_args](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:8480).

Changing one canonical plan input changes the child description and digest-derived config path passed to the backend, but the contract only records the child’s model/effort.

Mutation:

```sh
python3 -c $'import copy,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
a=copy.deepcopy(c);b=copy.deepcopy(c)
b["hosts"]["codex"]["agent_templates"]["sweep"]="codex/agents/frontier.toml"
pa=m["build_plan"](a,"codex","balanced");pb=m["build_plan"](b,"codex","balanced")
aa=m["project_args"](pa,materialize_agents=False);ab=m["project_args"](pb,materialize_agents=False)
only=lambda xs:[x for x in xs if x.startswith("agents.sweep.")]
print("contracts_equal="+str(m["run_contract"](pa)==m["run_contract"](pb))+" argv_differ="+str(aa!=ab))
print("a="+repr(only(aa)));print("b="+repr(only(ab)))'
```

Output:

```text
contracts_equal=True argv_differ=True
a=['agents.sweep.description="Cheap read-heavy scans, candidate finding, mechanical checks, and closed-form summaries."', 'agents.sweep.config_file="/Users/kangmin/.cache/agent-launch/codex-agents/7220d4cb9eec4821012a/sweep.toml"']
b=['agents.sweep.description="Bounded hardest decisions, first-of-kind design, triage, and final verdicts."', 'agents.sweep.config_file="/Users/kangmin/.cache/agent-launch/codex-agents/f0145feda407671dd3ba/sweep.toml"']
```

Nearest control—different path spelling, same template content:

```sh
python3 -c $'import copy,pathlib,runpy
m=runpy.run_path("launch/agent-launch.py");c=m["load_config"](pathlib.Path("launch/agent-launch.toml"))
a=copy.deepcopy(c);b=copy.deepcopy(c)
b["hosts"]["codex"]["agent_templates"]["sweep"]="codex/agents/sweep.toml"
pa=m["build_plan"](a,"codex","balanced");pb=m["build_plan"](b,"codex","balanced")
aa=m["project_args"](pa,materialize_agents=False);ab=m["project_args"](pb,materialize_agents=False)
only=lambda xs:[x for x in xs if x.startswith("agents.sweep.")]
print("contracts_equal="+str(m["run_contract"](pa)==m["run_contract"](pb))+" argv_differ="+str(aa!=ab))
print("a="+repr(only(aa)));print("b="+repr(only(ab)))'
```

Output:

```text
contracts_equal=True argv_differ=False
a=['agents.sweep.description="Cheap read-heavy scans, candidate finding, mechanical checks, and closed-form summaries."', 'agents.sweep.config_file="/Users/kangmin/.cache/agent-launch/codex-agents/7220d4cb9eec4821012a/sweep.toml"']
b=['agents.sweep.description="Cheap read-heavy scans, candidate finding, mechanical checks, and closed-form summaries."', 'agents.sweep.config_file="/Users/kangmin/.cache/agent-launch/codex-agents/7220d4cb9eec4821012a/sweep.toml"']
```

Proposed fix: derive one pure child-registration projection—tier, description, and config identity/content digest—and make contract rendering, materialization, and argv consume that projection.

Missed check: [launcher_review_contract](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:2519) now reconciles MCP registration changes but never varies child templates. [agent_materialization](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:11192) exercises the adjacent projection without comparing it to the contract.

### Medium — F3: a singleton fold omits its pass set

File/function: [_merge_method_passes](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:3124), specifically the early return at [line 3209](/Users/kangmin/Documents/agent-bios-fix-tree/launch/agent-launch.py:3209).

The probe supplies the non-empty main-dispatch anchor used by the public fold path. A valid singleton is returned unchanged, so its folded record lacks the required `passes` set.

Mutation:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");H=lambda b:hashlib.sha256(b).hexdigest();D=H(b"packet")
r={"schema":"ReviewReceipt/v1","method_id":"panel","dispatch_id":"one","packet_sha256":D,"result_sha256":H(b"one"),"provider":"p","model":"m","effort":"e","exit_status":0}
z=m["_merge_method_passes"]("panel",[r],"main")
print("has_passes="+str("passes" in z)+"; passes="+repr(z.get("passes")))'
```

Output:

```text
has_passes=False; passes=None
```

Nearest control—two valid passes:

```sh
python3 -c $'import hashlib,runpy
m=runpy.run_path("launch/agent-launch.py");H=lambda b:hashlib.sha256(b).hexdigest();D=H(b"packet")
def r(i,b):return {"schema":"ReviewReceipt/v1","method_id":"panel","dispatch_id":i,"packet_sha256":D,"result_sha256":H(b),"provider":"p","model":"m","effort":"e","exit_status":0}
z=m["_merge_method_passes"]("panel",[r("one",b"one"),r("two",b"two")],"main")
print("has_passes="+str("passes" in z)+"; passes="+repr(z.get("passes")))'
```

Output:

```text
has_passes=True; passes=['3fc4ccfe745870e2c0d99f71f30ff0656c8dedd41cc1d7d3d376b0dbe685e2f3', '7692c3ad3540bb803c020b3aee66cd8887123234ea0c6e7143c0add73ff431ed']
```

Proposed fix: remove the singleton early return and let the common merge path assign `passes` after raw-pass validation. For one receipt it naturally becomes a one-element set.

Missed check: [launcher_receipt_fold](/Users/kangmin/Documents/agent-bios-fix-tree/gates/check_parity.py:5655) explicitly accepts a clean singleton “unchanged” and checks only its dispatch ID and primary digest. It should require `passes == [result_sha256]`.

## Round-5 closure and amendments

- MCP capability rename: `contracts_equal=False argv_differ=True`; registered name changed `ultracode → alias`.
- Command-change control: `contracts_equal=False argv_differ=True`; command changed to `/bin/echo`.
- D4 held: packet-less verification remained complete with `packet_binding=none`; matching supplied bytes rendered `packet_binding=bytes`; wrong bytes and a different embedded plan were refused.
- S4/S6 held: the routed setup was refused at save, while a non-routed setup reached the save projection.
- The remaining L7 argv inputs were probed; the child-template projection above was the only additional byte-identical-contract twin found.

## Spec defects

None confirmed. F3’s one-trial `passes` blind spot is a code/enforcement failure, not a contradiction or waiver of F3.

## Void readings

L5’s explicitly disclosed, unenforced grade derivation produced the same acceptance behavior:

```text
mutation: parsed grade=perspective_floor best=perspective_floor
control:  parsed grade=provider_difference best=provider_difference
```

Both parsed, and verification labels the grade `grade_derivation=claimed`; this was dropped as a finding.

## Denominator

- Probed: all 33 invariants — L1–L8, D1–D8, F1–F4, V1–V7, S1–S6.
- Read only: none.
- D8 and S5 used bounded failure injection and post-failure residue checks, as the specification permits.
- Both configured dry-runs passed with `--config launch/agent-launch.toml`.
- Full parity was not run because its fixtures write temporary artifacts; the relevant checks were inspected.
- Worktree remained clean at `f50767c`.

## Not examined

- Adapter honesty, semantic aggregation quality, and review quality.
- Q1–Q9 as defects.
- Host CLI execution.
- Real concurrent filesystem interleavings.
- Runtime outside the named subsystem.
