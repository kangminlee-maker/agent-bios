# Team work-environment design — current entry

Updated 2026-09-20. This file is a navigation pointer, not another specification.

- **Latest handoff:** [2026-09-20 02:15 KST](2026-09-20T0215--edf15c5--handoff.md). Read it first when resuming: PR #4 is merged, P00 is accepted again under the 17:47 plan, P01 has a process design and its first probes, and the gate fix waits in PR #5. The [2026-09-19 handoff](2026-09-19T2243--6367ef2--claude-handoff.md) keeps the user decisions and lessons, but its state claims predate PR #3 and PR #4. The [2026-09-16 17:47 handoff](2026-09-16T1747--494f996--handoff.md) explains the successor validator and regression bundle.
- **Product inventory:** [Designed but unimplemented · 2026-09-19](2026-09-19T2228--6367ef2--unimplemented-scope-review.md). The Team, knowledge and memory product paths are absent. Its P00 statement is true of the 10:26 plan only.
- **Design SSOT:** [Consolidated target design · 2026-09-15 10:26 KST](2026-09-15T1026--35c75ca--consolidated-design-ssot.md)
- **Scope and application:** [Separate scope/role collections; repository-first Instructions/knowledge](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s05-scope-composition). Local content overrides need no Team vote; original source rights and historical records remain distinct.
- **Decision consumption:** [Question in the actual working CLI/app](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s06-consumer-interaction) · [Korean mechanism research](2026-09-15T1026--35c75ca--consumption-mechanism-review.md). An activated reader usage contract routes to one local owner; the working host asks and resumes. Native forms are preferred where qualified, with a verified conversation fallback or pending_user. Hooks are optional, and zero selected Instructions is valid.
- **Decision choice lifetime:** [User choice and keep/ask lifetime](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s05-decision-arbitration). Related participant changes invalidate the choice/mode; unrelated changes and same-use retries do not create repeated questions. Source browsing and compatible/empty results require no arbitration.
- **TUI first screen:** [Nine source positions and effective material](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s11-tui-entry) · [Korean wireframes](2026-09-15T1026--35c75ca--tui-entry-wireframes.md) · [Management projection](2026-09-15T1026--35c75ca--tui-entry-prototype.html) · [Scoped evidence](2026-09-15T1026--35c75ca--tui-entry-evidence.json). Studio inspects source records; it does not collect future decision-use consent. Design criteria stay out of product copy. Normal startup checks and dispatches through one named action; entry still infers no task and requires no goal form.
- **Storage, scope and intake:** [Source bundles and authoring homes](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s08-source-storage) · [Repository/Team ADR](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s04-scopes) · [Learning/distillation](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s06-intake)
- **Identity and local access:** [Account-free identity](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s07-identity) · [Lock, signout and offline use](2026-09-15T1026--35c75ca--consolidated-design-ssot.md#s07-local-access)
- **Development specification:** [Brownfield target and controlled cutover](2026-09-15T1026--35c75ca--development-spec.md). Backward compatibility is explicitly not required.
- **Implementation task graph:** [Unified build, verification and runner-qualification graph](2026-09-16T1747--494f996--development-plan.json). The 17:47 successor keeps the 10:26 nodes, catalog, SSOT and spec, and binds a new validator and regression helper.
- **Intermediate tests:** [Test families and phase scopes](2026-09-15T1026--35c75ca--test-catalog.json) · [Static plan checker](2026-09-16T1747--494f996--check-development-plan.py)
- **This revision's verification:** [Consumption correction, cross-review and scoped checks](2026-09-15T1026--35c75ca--consumption-verification.md). Author regressions passed; actual host interaction remains implementation qualification work.
- **Traceability:** [Design source inventory](2026-09-15T1026--35c75ca--ssot-sources.json) · [Selected brownfield code evidence](2026-09-15T1026--35c75ca--brownfield-evidence.json)
- **Prior engineering repair:** [Root-cause repair of XR01–XR03](2026-09-14T1933--35c75ca--repair-review.md). Planning/evidence-model fixes are verified; product backup and the actual R0 runner qualification remain scheduled work.
- **Bootstrap execution (P00):** [Re-run on main's merge commit · 2026-09-20](2026-09-20T0146--edf15c5--p00-rerun-record.md). Baseline `edf15c5`, reachable from `main`; a first attempt failed on a gate defect and is kept, the second passed, and the 17:47 evaluator accepts P00 and lists nothing as ready because only P01 can bind the other 24 profiles. The [2026-09-15 record](2026-09-15T1343--35c75ca--p00-baseline-record.md) is the accepted result under the 10:26 plan and reads `stale plan/node` under the current one. No product node is implemented.
- **Contract freeze (P01), in progress:** [Process design and first probes · 2026-09-20](2026-09-20T0210--edf15c5--p01-process-design.md). Nothing is frozen. Registry feasibility, the macOS signature and storage probes and the headless host probe are done; the host probe showed that a configured hook can answer a form with nobody present, so no host binding is qualified. R0 follows P01 and is needed only for unattended dispatch.
- **Live author gate:** [Current bundle gateway](../../gates/check-development-plan.py) runs the selected validator and [bound acceptance regressions](2026-09-16T1747--494f996--acceptance-tests.py) in default mode through the parity umbrella.
- **Historical finding record:** [18:19 cross-review](2026-09-14T1819--35c75ca--cross-document-review.md) · [original counterexamples](2026-09-14T1819--35c75ca--cross-review-evidence.json). The old reviewed bundle is preserved.
- **Prior-revision Korean map (15:04):** [Interactive map](2026-09-14T1504--35c75ca--design-map.html) · [fragment](2026-09-14T1504--35c75ca--design-map.fragment.html) · [original QA](2026-09-14T1504--35c75ca--ssot-consolidation-qa.md). This historical map is not a complete projection of current identity, storage, scope or intake rules.

Read the SSOT for current target-design rules. Earlier dated records remain
historical rationale, reviews and prototypes; their normative design role is
superseded by the SSOT. They retain their actual evidence and unresolved failures.
The visualization is a projection of the linked SSOT, never a separate authority.
The target design is not a statement that the Team/K/M system is implemented.
The engineering spec and graph derive implementation work from that design;
they do not redefine its business rules. All product and qualification nodes remain planned. The TUI entry is a scoped management mock. Actual consumer question/answer/resume routes remain P10/N23 qualification work; terminal behavior and first-exposure comprehension remain required P17/N26 evidence. The graph now consumes mandatory evidence; static/model checks do not count as real product or runner qualification.

The unversioned `check-development-plan.py` is retained only for the superseded
17:20 plan's recorded command and content binding. It is a historical validation
artifact; use the dated static checker linked above for the current plan. The
commit-time checker inventory validates this exact historical binding separately
from live gate reachability.

On a design change, publish a dated successor of the complete SSOT and update
this pointer and its projections together. Do not add competing current rules
in supplements. The product purpose stays canonical in root AGENTS.md; actual
runtime behavior and terminology remain owned by code and the operated lexicon.
