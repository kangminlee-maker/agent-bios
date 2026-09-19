---
created_at: 2026-09-19T22:28:25+09:00
head: 6367ef2
kind: review
status: current-code-inventory-not-product-runtime-qualification
design_ssot: 2026-09-15T1026--35c75ca--consolidated-design-ssot.md
---

# Designed but unimplemented — current scope inventory

The product purpose remains efficient, continuous work through selected shared
environments. This review distinguishes the existing Instructions foundation from
the new Team/knowledge/memory capabilities. It changes no business design contract.
The 1026 SSOT remains authoritative; the inventory below is a dated projection.

## Current implementation boundary

At HEAD `6367ef2`, the Team design has landed in the repository. `workenv/` and
`gates/workenv/` do not exist. All 40 distinct planned `workenv/` ownership paths
and the N01–N28 target suite paths are absent. Existing Instructions catalog,
store, setup, editing UI, native session and app-context delivery remain implemented
in `compose/` and `launch/`. This is source inspection, not a new certification
of installed/runtime behavior.

The external P00 run was reevaluated read-only with the selected 1026 evaluator:
`accepted_nodes=["P00"]`, `ready=[]`, both mode-specific eligible sets empty,
`terminal_accepted=false`. It contains only the P00 record, binding and baseline
subject. P00's baseline manifest, result artifact and B01–B05 test logs exist and
match their recorded hashes. Those results establish the captured starting point,
not target-product completion. The dated plan's `planned` statuses alone are not
used to infer completion or noncompletion.

Execution source:
`/Users/kangmin/.local/share/agent-bios-workbench/p00-baseline-20260915/evidence/run.json`.
The current checkout is newer than that captured baseline. P01 must preserve and
reconcile its declared baseline/evidence rather than silently relabel old test
results as tests of today's tree. Foreign untracked `output/` and `research/fde-ui/`
were left untouched and excluded from this initiative's inventory.

## Pending capability map

| User-facing group | Designed scope still requiring implementation | Existing boundary | Design / work owners |
| --- | --- | --- | --- |
| Domain knowledge | Coherent documents/tables/models/questions, applicability and source editions, at least one real reviewed package, addition/extension and onto 8+1 review integration | `compose/domains.json` classifies Instructions; it is not this knowledge database | S03, S11; P04/P15 |
| Decision and work records | Repository/personal/Team decision ownership, stated reasons/alternatives/premises, immutable correction/replacement events and parallel workstreams | Author-side `decisions/` and native session logs are not the deployed multi-scope memory product. The cross-tool progress writer/schema/capture/sharing contract is still open | S04, S14; P05 |
| Learning and session distillation | Exact-source typed candidates, permitted destinations, review/acceptance and later consumption without silently turning K/M into Instructions | Existing learning mainly feeds Instructions; heavy session-distill is author-side | S06 intake; P19/P15 |
| Environment composition | Nine scope/role positions, separate originals/effective view, repository > personal > Team for I/K, selected editions and publication/adoption | Existing Instructions selection/snapshots provide a base; the I/K/M composition contract is new | S05; P06/P08 |
| Working CLI/app consumption | Bounded role readers, actual-host conflict question, keep/ask with related-change invalidation, true answer evidence, same-use recovery and child/compaction reach | Existing Instructions delivery/hook carriers are not a decision broker. Questions belong to actual use, never mandatory Studio management | S06; P06/P10 |
| Integrated Studio | Revised entry, all-role authoring and comparison, ontology/forms/questions, search/derivatives/bulk/retention/recovery and equivalent TUI/GUI operations | Instructions UI exists; integrated screens are design/mock projections. Final GUI packaging is not frozen | S11; P11/P15/P16/P17 |
| Team lifecycle and governance | Creation/read/update/retirement, members/devices/ownership, scoped grants, review/publication/adoption, unavailable finalizer and uncertain outcomes | No implemented Team provider. Governance does not require Team permission for independent local content overrides | S07/S09; P07/P08/P14 |
| Identity, auth and local access | Account-free personal start, stable person/Team/device identity, optional Google/Slack/OIDC, lock/signout and permitted explicit offline reentry | Native task IDs and Instructions Off are not this identity/access lifecycle | S07; P02/P13 |
| Storage, exchange and recovery | Owned versioned sources, durable local state, P2P/package exchange, optional recommended GitHub, intermittent connectivity, custody, backup/recovery and stale-copy handling | Existing Instructions transactions are a base, not Team replication or complete backup/recovery | S08; P03/P09/P12/P16 |

## Implementation order, not a progress percentage

1. **P00 accepted:** captured baseline and classified existing behavior.
2. **P01 next dependency step:** freeze actual schemas/APIs/storage/credential/
   signature/host bindings and executable case bindings. No current ready result
   is claimed before the missing execution bindings/evidence are supplied.
3. **M1 personal path:** P02/P03 → P04/P05 → P06 → P10/P11, then actual verification.
   No Team, SSO or GitHub prerequisite.
4. **M2 Team path:** P07 → P08 → P09 plus P10/P11 integration. Shares the local
   foundations and can partly proceed in parallel with personal work.
5. **M3 full operations:** P12–P16 and P19 deliver optional carriers/auth, lifecycle,
   authoring/search/intake and complete operational clients.
6. **M4 qualified cutover readiness:** P18 candidate package plus M1/M2/M3 evidence
   precede P17 joined/adversarial/actual-host/usability qualification; M4 follows.
   It is not automatic release/publication authorization.

**Conditional branch:** R0 depends on P01 and qualifies the selected actual runner
before unattended dispatch. Coordinator-mode product work need not wait for R0.
The old handoff's claim that P01 and R0 are both eligible is not the current
evaluator result and does not override that dependency. The live pointer is corrected;
the historical handoff remains unchanged.

## Open design, deliberate exclusions and unproven behavior

- P01 must still bind concrete implementation contracts; the SSOT is not a frozen
  wire schema. Cross-tool progress capture and final GUI packaging remain open.
- Actual host question/answer paths, offline failure/recovery, Korean terminal/IME,
  accessibility and first-exposure comprehension still need their planned tests.
- Mandatory cloud accounts, global blockchain consensus, old-interface compatibility,
  universal semantic conflict resolution and hooks that claim to intercept all model
  reasoning are deliberately excluded. P2P, Team CRUD and complete Studio are included.
- Existing baseline tests, design evaluator controls and browser mock checks do not
  establish product implementation. Do not compute effort completion from node count.

## Visualization and scoped checks

The conversation projection is `unbuilt-work-environment.html` in this task's
visualization directory. It uses three branches and nine selectable capability
groups, with current foundations, pending work and phase references. Its first
render selects actual-host consumption to preserve the latest user correction.

Headless browser checks exercised all nine selections, one selected control at a
time, and responsive layouts at 736/360/320 outer pixels (704/328/288 inner pixels).
No horizontal overflow or page errors were observed. Wide light/dark screenshots
were captured, and the wide light screenshot was inspected. This validates the
explanatory visual only; no product API, host account, repository service or team
state was changed. The full product gate suite was not rerun for this inventory.

Sources: [CURRENT](CURRENT.md), [SSOT](2026-09-15T1026--35c75ca--consolidated-design-ssot.md),
[development plan](2026-09-15T1026--35c75ca--development-plan.json),
[P00 record](2026-09-15T1343--35c75ca--p00-baseline-record.md),
[historical handoff](2026-09-15T1629--bb7b212--handoff.md), and actual current source
paths named above. Independent source/contract and execution-evidence reviews
agreed on the boundary; no external platform research was needed for this inventory.
