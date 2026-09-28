---
created_at: 2026-09-14T18:19:51+09:00
head: 35c75ca
kind: review
status: three-open-cross-document-findings
subject_revision: 2026-09-14T1752--35c75ca
evidence: 2026-09-14T1819--35c75ca--cross-review-evidence.json
---

# Cross-review of design, development specification, execution plan and tests

## Verdict

The core source/storage/identity meanings do not have a demonstrated direct
contradiction in this review. The bundle does, however, have **three actionable
gaps between required behavior and execution/acceptance evidence**: one high
priority missing verification dependency and two consequential precondition/test
gaps. Do not certify the plan as ready for unattended end-to-end development.
The declared initial P00 baseline work remains valid; P01's intentional binding
freeze is not a defect or a reason to claim later implementation already exists.

The four current target documents were frozen by hash. Two fresh delegated
contexts reviewed contracts and execution semantics; the main context checked
the paired evidence and ran bounded counterexamples. This is not cross-provider
validation, a runtime security review or a formal proof of completeness.

| ID | Priority | Boundary | Required correction |
| --- | --- | --- | --- |
| XR01 | P1 | Required milestone tests → terminal acceptance | Consume mandatory milestone evidence or schedule equivalent integration nodes, including Team N15 |
| XR02 | P2 | Runner qualification → first unattended dispatch | Add an early qualification/preflight artifact; keep P17 as regression if useful |
| XR03 | P2 | Durable local state → recovery acceptance | Add explicit consistent backup/restore of unique drafts/outboxes/request state, not just restart/peer recovery |

The [evidence record](2026-09-14T1819--35c75ca--cross-review-evidence.json) contains
the exact source hashes and symbolic/CLI probe results. The original four
documents, checker and product runtime were not edited by this review. Findings
are open; the remedies below are not implementation or evidence of repair.

## XR01 — Required milestone evidence is not consumed by final acceptance

**P1 · Executable projection omits a required verification dependency.**

The [specification:367](2026-09-14T1752--35c75ca--development-spec.md:367)
assigns Team delivery to M2 and requires milestone profiles to run. But the
[scheduling rule:440](2026-09-14T1752--35c75ca--development-spec.md:440)
unlocks work only from accepted task predecessors; it defines no milestone
execution/result/invalidation dependency. [M2 in the plan:1345](2026-09-14T1752--35c75ca--development-plan.json:1345)
has its required code tasks, but no task consumes its accepted evidence.
[P17:1083](2026-09-14T1752--35c75ca--development-plan.json:1083)
depends on implementation tasks, P18 on P17, and [M4:1371](2026-09-14T1752--35c75ca--development-plan.json:1371)
requires only P17/P18 task acceptance.

The gap has a concrete affected test. Only P10/P11 task profiles select N15, and
their scopes are explicitly personal. [M2's profile:1293](2026-09-14T1752--35c75ca--test-catalog.json:1293)
contains the Team N15 branch. [P17's profile:1219](2026-09-14T1752--35c75ca--test-catalog.json:1219)
and [M4's profile:1343](2026-09-14T1752--35c75ca--test-catalog.json:1343)
omit N15, despite P10's completion prose deferring Team proof to M2/P17.
Other tests may exercise parts of Team behavior; that does not establish the
required joined Team delivery/recipient cases.

**Counterexample:** accept all tasks after their own scoped profiles pass.
Personal N15 has run, but no M2 result exists. P17/P18 and M4's declared task
prerequisites can be satisfied without an accepted Team N15 result. Correctly
implementing the prose would require inventing an additional acceptance rule
that the purported execution graph does not represent.

**Probe:** removing only M2 from a temporary deep copy of the plan still passes
the current checker, including its full CLI with `--check-inputs` (exit 0).
The [checker:131](2026-09-14T1752--35c75ca--check-development-plan.py:131)
validates the milestones present but does not require M2 or consume milestone
results. This is a plan-counterexample, not a product exploit or real execution.

**Minimum remedy:** make milestone runs accepted evidence nodes, or create
equivalent scheduled integration tasks. Final integration must consume required
M1/M2/M3 results bound to the actual integrated inputs and invalidate them when
affected code/contracts change. Ensure Team N15 is required at a consumed node.
Do not make the personal M1 path depend on Team providers.

**Closure tests:** all implementation tasks accepted but M2 absent, failed or
stale must block terminal qualification. Removing a required milestone/profile
must fail plan validation. Passing current M2 evidence must unblock only its
dependent acceptance conditions, with the personal path still independent.

## XR02 — The runner's pre-use qualification is scheduled after implementation

**P2 · Unscheduled prerequisite for the unattended mode.**

The [specification:432](2026-09-14T1752--35c75ca--development-spec.md:432)
requires N25 before a chosen runner is used unattended. Yet
[P01 is explicitly excluded:371](2026-09-14T1752--35c75ca--development-spec.md:371)
from runner qualification, and the sole task selecting
[N25:575](2026-09-14T1752--35c75ca--test-catalog.json:575)
is [P17:1099](2026-09-14T1752--35c75ca--development-plan.json:1099), after almost
all implementation tasks. The task readiness and required-evidence fields have
no separate accepted runner-qualification prerequisite.

**Counterexample:** choose unattended execution for the implementation DAG.
Following the only scheduled N25 owner qualifies the runner only after it has
run most of the work. Obeying the pre-use requirement instead leaves no earlier
scheduled task or declared external artifact that can satisfy it. Attended
coordinator-led execution remains possible; this is not a cycle preventing all
development and not a request to build a universal orchestration service.

**Minimum remedy:** add an author-side runner bootstrap/qualification step or
explicit accepted preflight artifact before the first unattended dispatch. Use
a small synthetic development graph to test task IDs, restart, stale evidence,
file ownership and interrupted integration without requiring the future product.
Bind its runner/configuration fingerprint into readiness; invalidate it when
relevant runner behavior changes. A later P17 regression can remain.

**Closure tests:** absent/stale qualification refuses unattended dispatch;
valid qualification allows eligible work; attended execution has an explicit
mode and does not claim unattended assurance. No provider/model diversity is
asserted merely because the runner launched another worker.

## XR03 — Unique local-state backup restoration lacks a named acceptance case

**P2 · Required recovery behavior is not projected into a sufficient test.**

[SSOT:934](2026-09-14T1752--35c75ca--consolidated-design-ssot.md:934)
makes the SQLite state non-disposable. [SSOT:977](2026-09-14T1752--35c75ca--consolidated-design-ssot.md:977)
and [specification:134](2026-09-14T1752--35c75ca--development-spec.md:134)
require local drafts, outbox, authority sequencing and request/receipt state to
have consistent backup/recovery, separately from semantic peer synchronization.

[P03's completion criteria:300](2026-09-14T1752--35c75ca--development-plan.json:300)
and [N05:174](2026-09-14T1752--35c75ca--test-catalog.json:174)
cover durable boundaries and restart against a surviving store.
[N14:354](2026-09-14T1752--35c75ca--test-catalog.json:354)
reconstructs permitted peer inventory and rejects false authority/replay.
Those are necessary, but no named positive case restores a consistent local
backup after database loss, including private unique work and operation mapping.
Selected-data cutover exports are not this ongoing operational backup contract.

**Counterexample:** an implementation passes process crash/restart and peer
source reconstruction, but backs up only portable accepted material. A private
candidate, an undispatched outbox request and an uncertain request's identity
are lost with the local database. Accepted documents can be restored while the
unique work and same-request recovery path cannot. The current named tests need
not expose this failure.

**Minimum remedy:** give P03/N05 an explicit supported local backup/restore
deliverable and case. P01 still selects the actual platform, backup/protection
mechanism and durability settings. Restore a consistent backup and its required
objects after loss of the local state; verify candidate/draft, outbox request,
receipt/control associations and unknown-operation identity. Source files alone
must not manufacture committed state or another active finalizer.

**Closure tests:** a valid backup restores its declared scope exactly; missing
members, inconsistent DB/object snapshots and invalid control/time state fail
with qualified recovery. Work newer than the available backup remains outside
that backup's demonstrated coverage, not silently recovered or discarded as if
known absent. Peer integration may follow in P09/P17 without a new global service.

## Agreements and intentional deferrals

- Repository ADR and Team ADR, one canonical source home, applicability versus
  ownership, and source-qualified reader union agree across the reviewed sites.
- Supplied/added knowledge provenance and typed learning/distillation candidates
  do not imply Team acceptance or automatic Instructions delivery.
- Local signout is a durable barrier for session-derived operations; already
  dispatched requests and independently authorized finalizers retain their own
  outcomes/lifecycle. The named owner and access tests preserve that distinction.
- Backward compatibility is expressly waived; selected data/current source work
  and a quiesced final cutover still require explicit disposition.
- P00 complete baseline, P01 codec/schema/credential/bridge/case binding, external
  provider evidence and actual human usability are intentional future work. Their
  absence today is not counted as a contradiction.
- P16's candidate-retention tests can use frozen contract fixtures without a
  P19 runtime dependency. A separate Team UI wiring task is not proven necessary
  if the declared capability-driven shell can provide it. Neither suspicion is
  elevated without evidence.
- A real starter package is assigned to P04; its concrete content/evidence paths
  belong in P01's explicitly planned inventory/ownership freeze.

## Disposition and limits

The existing plan checker, its 19 negative controls, purpose gate and decision
ledger check passed at review start. The missing-M2 probe demonstrates why those
results cannot certify execution completeness. No full product suite, real
provider, live extractor, database recovery or human usability test was run.

The recommended next change is a narrowly scoped successor of the engineering
bundle: encode mandatory evidence dependencies, qualify the runner before
unattended use, and add the local-state backup case. Preserve source/authority
semantics and the user's no-compatibility direction. Re-review the changed
dependencies and add failing controls before closing XR01–XR03. This report and
its proposed remedies do not close them.
