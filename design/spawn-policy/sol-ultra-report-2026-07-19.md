## 1. Spawn-point definitions (down-delegation and frontier up-delegation).

A spawn point is a conjunction of observable predicates, not a topic label. Before spawning, HELM should form a task card containing the objective, finite input scope, output contract, acceptance oracle, unresolved choices, blast radius, and:

- `E`: substantive work HELM would otherwise perform.
- `H`: work required to brief, verify, correct, and integrate the delegation.

### Down-delegation

Down-delegation is admissible only when all of these are true:

- **Input closure:** Required evidence lies within a finite named scope; no missing user intent or requirement must be inferred.
- **Decision locality:** No unresolved choice affects user-visible scope, architecture or public interfaces, security/privacy/data handling, irreversible external effects, or another work shard.
- **Cheap verification:** A predeclared test, checklist, schema, or short diff review can reject a materially wrong result without HELM repeating the work. If verification repeats the reasoning, `H ≈ E`, so the gate fails.
- **Reversibility:** The output is staged until HELM accepts it; the subagent cannot independently commit an external or irreversible action.
- **Positive leverage:** Initially require `E ≥ 2H`. This is a tunable starting threshold, not a permanent constant.

The acceptance oracle—not trust in the lower tier—is what makes substitution potentially quality-neutral.

**Use SWEEP** when every work unit applies one explicit rule to independent targets. The output must be mechanically replayable or carry source evidence, and ambiguity must be returned as an exception rather than resolved. Typical shapes are exact-match inventories, fixed-schema transformations, and closed rule-based checks.

**Use WORKHORSE** when local semantic judgment or implementation is necessary, but requirements, interfaces, invariants, and acceptance criteria are frozen. Suitable tasks include module-local implementation, test construction, and per-item judgments under a complete rubric. WORKHORSE may choose reversible local means, but not change the task contract.

**Keep the work in HELM** whenever the task requires discovering intent, reconciling competing goals, establishing architecture, coordinating coupled shards, or making a choice whose verification would require duplicating the original reasoning.

### Frontier up-delegation

A FRONTIER spawn requires all three conditions:

1. **Material stakes:** An error would change a user-facing verdict, establish an architecture or public interface, invalidate at least two downstream work units, cause major rework, or create security, privacy, data-loss, or irreversible-action risk.
2. **Residual epistemic risk:** At least one concrete signal exists: two viable alternatives remain; evidence or requirements conflict; a sensitivity check shows an unverified assumption can flip the decision; two attempts or hypotheses have failed; or a material claim lacks a mechanical oracle.
3. **Decision leverage:** Before spawning, HELM can name a finding that would change the selected option, constraint, implementation, test plan, release decision, or confidence band.

The question sent upward must be bounded. FRONTIER advises or reviews; HELM retains the final decision and integration responsibility.

To prevent anchoring, HELM privately records its current option and confidence but starts FRONTIER in fresh context. The first packet contains raw evidence, constraints, evaluation criteria, and neutrally ordered alternatives—not HELM’s preference, rationale, confidence, or draft verdict. For option selection, obtain the independent verdict before revealing HELM’s draft; for artifact review, provide the artifact but omit HELM’s diagnosis or claim that it is correct.

Afterward, HELM records a disposition connecting FRONTIER findings to a material change or evidence-backed uncertainty reduction. Agreement, summary, or unused output without such a connection is vacuous.

No predicate can guarantee improvement on an individual case. A FRONTIER trigger should become a standing gate only after its trigger cohort passes the causal superiority metric below.

## 2. Decision gates — a compact checkable list suitable for inlining into an always-loaded system contract, 10 lines or fewer.

1. HELM retains user intent, scope, cross-cutting tradeoffs, irreversible choices, integration, and the final answer.
2. Before spawning, record objective, finite inputs, output contract, acceptance oracle, unresolved choices, blast radius, `E` (HELM execution work), and `H` (briefing plus verification and integration).
3. Do not delegate down if input or user intent is missing, verification repeats the task, or an unresolved choice crosses a scope, interface, architecture, security/privacy/data, external-effect, or shard boundary.
4. Down-spawn only when the result is reversible and `E ≥ 2H`; adjust this threshold from measured outcomes.
5. Use SWEEP only when every independent unit follows one explicit rule and ambiguity is returned rather than resolved.
6. Otherwise use WORKHORSE only for bounded local implementation or judgment with frozen interfaces and a cheap exhaustive acceptance check.
7. Use FRONTIER only for a bounded question with material stakes, a named residual-risk signal, and a predeclared way its answer could change the result.
8. Before FRONTIER, privately record HELM’s current option, confidence band, and concrete change conditions.
9. Give FRONTIER fresh context containing evidence, constraints, neutral alternatives, and rubric—never HELM’s preference, rationale, confidence, or draft verdict before its independent verdict.
10. HELM verifies every down-result and records every FRONTIER disposition; no material change or evidence-backed uncertainty reduction means the spawn was vacuous.

## 3. Metric tables: metric | measures | failure detected | interpretation rule | computable from logs today (yes/no).

Measure separately by host, tier, trigger, and task-size or risk band. Aggregates can conceal a broken gate. Use randomized holdouts within the current boundary and a shadow sample from the immediately adjacent band. Predeclare sample size, non-inferiority margin, and evaluation rubric before moving a boundary.

**Leading metrics — decision-time mechanism**

| metric | measures | failure detected | interpretation rule | computable from logs today (yes/no) |
|---|---|---|---|---|
| Eligible-opportunity capture | Gate-positive candidates actually spawned, divided by all gate-positive candidates, by tier | Policy unavailable or ignored; wrapper failure; continued SWEEP starvation | Below 80%: repair availability or contract enforcement before retuning gates. 80–95%: audit documented skips. At least 95%: mechanism is operating. | **No.** Non-spawned candidates leave no event; requires candidate and skip records. |
| Valid-routing rate | Spawns satisfying every applicable predicate, including correct tier and recorded `E/H` or FRONTIER change condition | Tasks delegated despite missing oracle, excessive coupling, wrong tier, or absent decision leverage | Any hard-boundary violation pauses that route. Below 95%: enforce or clarify policy. 95–98%: do not widen. At least 98%: outcome metrics may govern boundaries. | **No.** Existing prompts allow partial audit, but task-card predicates and estimates are absent. |
| Blind-packet purity | Initial FRONTIER contexts containing no HELM preference, rationale, confidence, draft verdict, or asymmetric framing | Anchoring that turns apparent independent agreement into confirmation bias | 100% is required for inclusion in uplift analysis. 95–100%: exclude contaminated calls and repair packet construction. Below 95%: pause superiority claims. | **Yes.** Main and sidechain transcripts permit chronological semantic audit of textual leakage. |

**Lagging metrics — outcome and boundary calibration**

| metric | measures | failure detected | interpretation rule | computable from logs today (yes/no) |
|---|---|---|---|---|
| Down-tier quality retention | `p(material failure under HELM-only) − p(material failure under down-delegation)`, using equal fixed verification budgets and a later correction/reopen window | Lower-tier errors escape the oracle; the task boundary is not quality-neutral | Let `δ` be a predeclared maximum loss, initially 1 percentage point for material defects and zero for catastrophic defects. Lower 95% bound at least `−δ`: non-inferior. Interval crossing `−δ`: hold boundary and collect data. Upper bound below `−δ`, or any catastrophic escape: contract that trigger or route one tier upward. | **No.** Requires comparable randomized controls, task IDs, acceptance outcomes, and later defect linkage. |
| Net compute saving | `1 − delegated-path cost / HELM-only cost`, using model-weighted tokens and including briefing, verification, retries, and rework | Delegation overhead consumes the work supposedly displaced; tasks are below the economic spawn point | With initial benefit floor `β = 10%`: lower 95% bound at least `β` plus quality retention permits expansion by one size band. Positive but below `β`: keep boundary. Upper bound at most zero: raise `E/H` or stop delegating that class. | **No.** Actual path cost exists, but the HELM-only counterfactual requires holdouts or reliable matched controls. |
| FRONTIER causal net win | In randomized eligible cases, the rate at which the FRONTIER-assisted final result beats the preserved HELM baseline minus the rate at which it loses; use objective outcomes where possible and otherwise blinded rubric adjudication | FRONTIER adds no quality, introduces errors, or helps only because evaluation is anchored | Lower 95% bound above zero: strict uplift; retain and test the adjacent risk band. Interval includes zero: unproven, keep experimental and do not widen. Upper bound at most zero: suspend that trigger. | **No.** Requires baseline snapshots hidden from FRONTIER, random assignment, and independent outcome adjudication. |
| FRONTIER actionable yield | Valid FRONTIER spawns producing a traceable material change or new evidence/analysis that moves a predeclared uncertainty or confidence band | Ceremonial reviews, vague confirmations, unusable packets, and outputs ignored by HELM | After at least 30 valid calls per trigger: at least 80% is healthy; 50–80% requires tighter change conditions or packet scope; below 50% suspends that trigger. High yield alone does not prove quality—the net-win metric must also pass. | **No.** Diffs provide only a lower bound; reliable measurement needs explicit pre-spawn conditions and post-spawn dispositions. |

## 4. Top 3 risks or blind spots of this entire approach.

1. **Self-reported gates are gameable.** An agent can underestimate verification cost, declare ambiguity “local,” or choose an easy acceptance oracle. The metrics may then improve while difficult judgment silently moves downward.

2. **Causal proof will be sparse and expensive.** Frontier-worthy cases are selected precisely because they are unusual, while severe failures are rare and delayed. Without randomized holdouts and independent adjudication, observed comparisons will mostly measure task selection rather than tier value.

3. **Independence conflicts with context completeness.** HELM can anchor through evidence selection and option framing even when its conclusion is removed; stripping too much context produces context-starved reviews. Shared model-family blind spots, host differences, and model upgrades further make previously validated thresholds non-portable.
