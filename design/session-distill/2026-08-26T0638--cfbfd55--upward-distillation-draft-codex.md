---
created_at: 2026-08-26T06:38:41+09:00
head: cfbfd55
kind: design
supersedes: —
---

# Upward-distillation design — draft from the Codex seat (raw, unedited)

Blind dual-provider design draft. Seat: openai gpt-5.6-sol, effort max, hermetic profile (no AGENTS.md, no user config), sandbox read-only, codex-cli 0.146.0. Packet sha256 `f43482032ca558ad2d8ee565f8fef1002eba9118dbe7a0c875f4e38cfc234d1a`; result sha256 `d2667c3b136a4b838389ca8ce5caf1f01e6f36332cfe83d1f5db1e0891556dcf`; receipt dispatch_id `f475f2e6d10c4bb08505ffe060f0a727` (ReviewReceipt/v1); 60,859 tokens. The synthesis and the live-seat verification are in `2026-08-26T0638--cfbfd55--upward-distillation-design.md`.

---

# Verdict: partial derivability, with behavior-preserving upward distillation

*Inference* — The 107 placed learnings are not operationally derivable from principles as one homogeneous set. A meaningful subset can be regenerated when the situation supplies the relevant facts and exposes a recognizable trigger; tool semantics, detailed procedures, and rules that must fire at an unrecognized acting point cannot.

*Inference* — Use a staged hybrid of alternatives **B + C + D**: incremental upward distillation, item-level derivability pruning against existing text, and surface changes for under-applied behavior. Treat alternative A, a principle-first global, as a possible endpoint only after measured child-by-child success—not as the migration method.

*Assumption* — Existing deployed Type-G text is treated as curator-approved principle evidence unless E1 or E4 explicitly says it is incubating or under-applied.

*Assumption* — “Child” means one atomic behavioral obligation; bundled entries such as `S3-96` and `S3-105` must be split only where their obligations are genuinely separable.

*Assumption* — Token estimates use the packet’s byte/token ratio and must be replaced by actual counts before approval.

## 1. Derivability verdict and mechanism

*Fact* — E1 contains 37 domain procedures, 36 tool gotchas, 20 recognition principles, nine principles, three own-tooling defects, and two unproven items. Seventy are already guide-level, while only 20 are global.

*Fact* — E4 shows that logical entailment is not enough. `G-6`, `G-8`, and `G-12` remained under-applied despite principle text; `S3-04` recurred after guide placement. Conversely, the concrete security-weakening trigger materially improved GPT-5.6 battery behavior.

*Inference* — Operational derivability should therefore mean:

> With the child absent everywhere, the same canonical parent principle plus an unlabeled situation causes both hosts to perform every required child behavior at the correct moment, without unacceptable over-triggering.

The determining factors are trigger burden and fact burden:

| Situation | Operational treatment |
|---|---|
| The situation exposes all relevant facts and a request-visible trigger | Test principle derivation. Likely examples include pinning an active context (`S3-06`), an exact concurrent handle (`S3-09`), or separating deploy-owned and user-owned state (`S3-16`). |
| The behavior depends on an unstated external-tool fact | Not derivable from the principle. Retain guide/hook/gate knowledge such as Cloud Run traffic semantics (`L-01`), Git two-dot behavior (`S3-31`), pipefail/SIGPIPE behavior (`S3-78`), or provider wire units (`S4-15`). |
| The semantic rule is known, but the model does not experience the acting point as a trigger | Preserve one canonical statement and change the surface: structured ask, checklist, spawn gate, hook, or battery. This applies to `G-6`, `G-8`, `G-12`, and `S3-04`. |
| The violation is deterministically detectable or preventable | Keep it mechanized. Principles may explain it but must not replace enforcement for `S3-39`, `S4-04`, or `S4-05`. |
| The item is a multi-step domain method | Keep the procedure in its routed guide, even if a principle explains why it exists; examples include per-commit scratch-worktree verification (`S3-42`) and collector reconciliation (`S3-97`). |

*Inference* — A model passing a child in the no-principle ablation arm demonstrates model-native behavior, not derivation. That can justify de-prescription, but it needs model-version revalidation.

*Inference* — The concrete security-posture rule remains global during the first migration. Its trigger is precisely the kind that E4 shows can benefit from explicit wording, and its failure cost is too high to infer redundancy from logical coverage alone.

*Inference* — Reuse the existing terms **principle** and **upward distillation**. Do not introduce “axiom.” Concept surface decreases by removing duplicate directives; it does not gain a new abstraction. A future split would be justified only if a supposedly preferential principle proved exceptionless and deterministically enforceable—in which case it should become a contract or enforcement rule, not an “axiom.”

## 2. Candidate principle set

*Inference* — E1 supports ten non-decorative candidate tensions. Six consolidate existing Type-G text; four are provisional upward-distillation candidates. Fewer than ten merges materially different triggers—for example pre-action identity versus post-action evidence, or lateral blast radius versus temporal reversibility. More than ten leaves proposed parents with fewer than three plausible children.

`F` marks packet fact; `I` marks a proposed interpretation. Listed children are test candidates, not approved demotions.

| Principle and evidence | Both sides, preference ordering, and prohibition | Claimed derivable children | Explicitly not covered |
|---|---|---|---|
| **P1. Pin consequential identity and state**. **F:** existing `G-2`; E1 explicitly absorbs `S4-03` and `S3-06`. | Convenience of ambient/late-bound state **vs** stable identity. When the outcome depends on it, resolve and pin the exact shell, context, handle, target, version, or input. Forbids relying on “current,” “latest,” a remembered position, or an unresolved name. | `S3-01`, `S3-06`, `S3-09`, `S3-12`, `S3-49`, `S3-53`, `S4-12` | Exact tool facts: `L-01`, `S3-31`, `S3-78`, `S4-15` |
| **P2. Own the lifecycle and separate ownership**. **F:** existing `G-3`; E1 names `S4-07` and `S3-16` as instances. | Local convenience/colocation **vs** lifecycle integrity. Prefer full ownership from creation through durable storage and teardown, while separating differently owned state. Forbids orphaning owned resources or storing user state in overwrite-managed artifacts. | `S3-16`, `S3-17`, `S3-27`, `S4-07`, `S4-10` | Grant-wide revoke semantics (`S3-90`), OAuth callback details (`S3-92`), expiry semantics in `S3-105` |
| **P3. Proportion assurance to concrete risk and delivery value**. **F:** existing `G-4` and `G-9`; E4 identifies the explicit 12-round retrospective for `G-4`. | Exhaustive precision/assurance **vs** practical delivery and simplicity. Prefer the least complex evidence sufficient for the named risk; increase depth for stochastic, costly, or irreversible work. Forbids absolute targets, speculative hardening, and assurance whose cost exceeds its decision value. | `S2-04`, `S3-68`, `S4-11` | Exact negative-control construction (`S3-44`), mutation outcome taxonomy (`S4-09`), transport measurement details (`S4-15`) |
| **P4. Preserve intended utility; restrict only for named risk**. **F:** existing `G-5` and the restrictive-control portion of `G-9`. | Sharing, continuity, and captured information **vs** precautionary restriction. Intended utility wins absent a concrete risk; once a risk is named, use the narrowest sufficient control. Forbids treating hardening, deletion, masking, or access reduction as inherently harmless. | `S2-02`, `S3-36`, `S3-71` | The empirically effective security-weakening trigger; grant-wide behavior in `S3-90`; perimeter probe mechanics in `S3-66` |
| **P5. Resolve the cause across its whole affected surface**. **F:** existing `G-10`. | Cheap local closure **vs** complete causal repair. Prefer naming and removing the cause everywhere it propagates, even when the immediate delta grows. Forbids default-off concealment, partial renames, sibling omissions, or patching recurring symptoms. | `S2-12`, `S2-15`, `S3-48`, `S3-101`, `S4-14`, `S4-16` | Tool-specific recovery procedures such as `S3-63` or `S3-98`; those require facts beyond causal completeness |
| **P6. Read truth from the executing mechanism, consumer, or sink**. **I:** upward candidate; E1 supplies many instances but not their independent-session provenance. | Convenient labels, dispatcher status, or proxy observations **vs** authoritative execution evidence. Prefer evidence emitted by the resolved target, downstream consumer, enforcement point, or output sink. Forbids concluding from success messages, process names, log silence, or client-side acceptance alone. | `L-01`, `S3-04`, `S3-20`, `S3-22`, `S3-50`, `S3-55`, `S3-79`, `S3-99`, `S4-05`, `S4-08`, `S4-13` | Exact Git/shell semantics (`S3-31`, `S3-78`) and credential behavior (`S3-90`) |
| **P7. A green result counts only after the instrument proves sensitivity and coverage**. **I:** upward candidate; session provenance still required. | Fast/apparent green **vs** trustworthy measurement. Prefer proving the instrument scanned a non-empty subject, applied the contrast, traversed the intended branch, and failed for the named reason. Forbids permissive fallbacks, no-op mutants, crash-as-success, and unexamined aggregation loss. | `S2-18`, `S3-23`, `S3-44`, `S3-58`, `S3-62`, `S3-76`, `S4-09`, `S4-17` | Sampling depth (`S2-04`), subject attribution (`S3-46`), provider-unit measurement (`S4-15`) |
| **P8. Judge an action by its whole activation blast radius**. **I:** upward candidate; the export does not prove three independent user resolutions. | Small local edit **vs** all consumers and side effects it activates. Prefer enumerating readers, clients, destinations, and latent consumers before application. Forbids scoping a decision by line count or the one visible feature. | `S3-100`, `S3-102`, `S3-61`, `S4-20` | The hidden fact that revoke is grant-wide (`S3-90`), and the service-spec behavior in `S3-98` |
| **P9. Preserve recovery before crossing an irreproducible edge**. **I:** upward candidate; session-level evidence must be checked. | Immediate progress/in-place mutation **vs** recoverability of identity, data, and completed state. Prefer snapshots, downstream proof, staged activation, and partial-state enumeration before irreversible steps. Forbids overwriting the only good state, activating an unusable collection window, or blindly rerunning an unconfirmed apply. | `S3-08`, `S3-19`, `S3-27`, `S3-63`; the snapshot portion of `S3-105` only after a valid ledger split | The security-posture trigger; grant-wide revoke semantics (`S3-90`); storage-expiry details in `S3-105` |
| **P10. Prefer a model-neutral canonical carrier over host leverage**. **F:** existing `G-11`. | Host-specific leverage **vs** portability and one source of truth. Prefer a neutral guide/gate/enforcement carrier; use hooks as derived accelerators only when timely neutral delivery is unavailable. Forbids a Claude hook or skill as the sole home. | Carrier choice, not semantic content, for `S2-05`, `S3-15`, `S3-31`, `S3-41`, `S4-01`, `S4-02`, `S3-103`, `S3-90`, `S4-08` | None of those IDs’ tool facts; P10 derives their dual-carrier placement only |

*Fact* — `G-8` and `G-12` have strong recurrence evidence but E4 shows that their principle text did not reliably produce behavior. `G-6` has the same under-application pattern and is absent from the E1 export.

*Inference* — Those three are retained behavioral requirements, not compression parents: one concise canonical line may remain, but the effective carrier must be the spawn gate, fixed decision-ask shape, structured question channel, acting-point checklist, and battery. `S3-04` similarly keeps its model-neutral guide home plus the Claude hook accelerator.

## 3. Falsifiable derivability protocol

### Test unit and holdout

*Inference* — Atomize each candidate child into mandatory semantic obligations before testing. If only part of `S3-105` or `S3-96` is entailed, split the ledger entry under the existing cardinality rule; otherwise a PARTIAL result cannot authorize demotion.

*Inference* — For every child, author four positive situations and two controls:

- Two realistic near-domain situations.
- One transfer situation in a different domain.
- One adversarial situation that makes the convenient wrong action attractive.
- Two non-trigger controls where applying the child would be needless or harmful.

Supporting incidents used to formulate the principle, their wording, lesson IDs, and isomorphic examples are held out. In the parent-only arm, the child is removed from the global, guides, hook payload, and packet injection.

### Arms, hosts, and sample size

*Inference* — Run four fresh-session arms on both Claude and Codex:

1. **Registered corpus** at `cfbfd55`.
2. **Explicit-child ceiling**, placing the exact child at the tested acting surface.
3. **Parent-only candidate**.
4. **Ablation**, containing neither parent nor child.

Screen at `N=2`. A child eligible for demotion advances to confirmation at `N=5`: six scenarios × four arms × two hosts × five repetitions = **240 responses per child**. Interleave arms and record model, host, corpus hash, fixture hash, and raw response.

*Inference* — Run the existing 13-scenario battery at `N=5` per host against the registered and complete candidate corpora: **260 additional responses per candidate bundle**.

### Instrument controls

*Fact* — E5 already supplies `expect`, `naive_miss`, inverted trigger controls, fixtures, and semantic HIT/MISS/PARTIAL scoring.

*Inference* — Before accepting a campaign:

- Feed the semantic judge a known-good response matching `expect`; it must score HIT.
- Feed it a known-bad response matching `naive_miss`; it must score MISS.
- Run a harmless global-loading canary and an intentionally absent canary; the first must appear and the second must not.
- Assert the exact expected denominator, non-empty scenario set, unique result keys, and corpus/fixture hashes.
- Keep the security-hardening control: it must not trigger the weakening workflow.

Failure of any control invalidates the campaign, including results that otherwise agree with expectation.

### Scoring and pass rule

*Fact* — LLMs judge semantics; tools may only run, count, diff, hash, and serialize. Owner approval is mandatory.

*Inference* — A semantic judge blinded to arm and principle receives only the opener, `expect`, `naive_miss`, and response. A second LLM adjudicates PARTIAL or inconsistent labels. Tools calculate rates; neither judge promotes anything.

A child derives only when, on **each host**:

- The explicit-child ceiling reaches at least 19/20 positive HITs.
- Parent-only reaches at least 18/20 HITs, has at most one MISS, and is no more than one weighted result behind the registered arm, with HIT=1 and PARTIAL=0.5.
- At least 9/10 controls remain correct.
- For security, authority, or irreversible behavior: no positive MISS and no dangerous control over-trigger.
- The complete 13-scenario battery loses no more than one response in any scenario/host cell, loses no more than five weighted percentage points overall, and introduces no security/authority MISS.

Decision rule:

- **Evidence bar + parent-only pass + owner approval:** promote/retain the parent and compress the child to a guide instance.
- **Explicit child passes, parent fails:** keep the child explicit.
- **Both explicit child and parent fail:** classify as under-applied and change the surface; prose repetition is prohibited.
- **Ablation passes:** classify as model-native redundancy; demote no farther than a retrievable guide instance during the first cycle.
- **One host fails:** retain the canonical child; a host accelerator may supplement but never replace it.
- **Control over-trigger:** reject or split the principle before testing other children.

## 4. Target corpus shape and reversible migration

*Inference* — Preserve E2’s recognizable sections. Within each section, the target order is:

1. One 30–50-token principle naming the tension, ordering, and prohibition.
2. Only empirically irreducible recognition or acting-point rules.
3. One router to detailed procedures and tool facts.

The global does **not** become principles plus routers only. The security-weakening rule, one concise `G-8`/`G-12` carrier, and other high-materiality triggers remain until their own tests justify removal.

| Layer | Packet baseline | Target estimate |
|---|---:|---:|
| Always-loaded global | **Fact:** 20.3 KB, about 5.0K tokens | **Inference:** first migration 18–19 KB, about 4.4–4.7K; mature conditional target 16.5–18 KB, about 4.1–4.4K |
| Five flagged guides | **Fact:** 107.7 KB combined | **Inference:** 92–100 KB, about 22.5–24.5K tokens, distributed among routed chunks of 7–14 KB |
| Typical routed oversized guide | **Fact:** 16.9–29.7 KB | **Inference:** one small index plus one 7–14 KB subguide; no loaded guide above 16 KB |
| Per ordinary session | **Fact:** global is always paid | **Inference:** save roughly 300–900 tokens after staged migration |
| Per affected routed task | — | **Inference:** commonly save another 1–4K tokens by loading only the relevant split |

*Inference* — Split only when at least five items share a recognizable `use_when`, preserving E3’s new-guide bar:

- `cli-multi-model-workflow`: dispatch/review, unattended batches, and handoff/resume.
- `tooling-gotchas`: shell/Git, managed config/services, and process/artifact ownership.
- `verification-discipline`: case/evidence design and instrument-validity failures.
- `review-defect-criteria`: defect lenses and causal closure.
- `review-request`: packet construction and returned-verdict reconciliation.

If a proposed split cannot meet the routing test, compact it in place instead.

*Inference* — Migration is family-by-family. The registered `cfbfd55` corpus remains immutable and deployable. A canonical manifest records parent, child obligations, old-text hash, candidate text, layer, accelerators, evidence, and test receipt. Claude and Codex mirrors are generated from the same candidate; old prose remains recoverable through the registered version and ledger rather than a new “legacy” concept.

*Inference* — Any child needed by hermetic reviewers must remain in, or be injected into, their packet. Global and guide compaction cannot be credited as reaching them. Enforcement and gates remain code-owned.

## 5. Implementation process

| Stage | Dependencies and work | Review gate and falsifiable done-when |
|---|---|---|
| **0. Freeze baseline** | Register corpus, generated mirror, guide, hook, gate, scenario, and runner hashes; rerun the 13 scenarios at `N=5` on both hosts. | Done when all expected results exist, scorer/load controls pass, and rollback reproduces the registered hashes. |
| **1. Atomize and prove evidence** | Account for all 107 E1 entries; split only genuinely bundled obligations; map each to one canonical home and zero or one proposed parent. Tools count; LLMs cluster semantics. | Owner approves each principle’s ≥3 independent user-resolved instances or retrospective. Done when 107 originals reconcile exactly and provisional P6–P9 are either qualified or rejected. |
| **2. Qualify the instrument** | Add isolated candidate-global loading for both hosts, blinded scoring, arm manifests, denominator assertions, and holdout scenarios. | Done when known HIT/MISS, loading, control, and denominator tests all behave oppositely where required. Any failure blocks measurement. |
| **3. Pilot one low-risk family** | Test P1 first on `S3-06`, `S3-09`, and `S3-12`; do not include security or irreversible children. | Owner approves each disposition. Done when all 240-response child campaigns and the full battery satisfy the protocol, or the pilot is explicitly rejected. |
| **4. Repair under-applied surfaces** | Keep prose stable while testing the existing spawn gate for `G-6`/`G-8`, structured decision channel for `G-12`, and hook-plus-guide path for `S3-04`. | Done when each behavior passes both hosts at `N=5` without new prose repetition. Failure redesigns the surface, not wording density. |
| **5. Distill one family at a time** | Apply approved P2–P10 decisions; rewrite existing text before adding bullets; each new global bullet names its displaced text or why none exists. | Per-family owner approval, mirror parity, ≤500 net global tokens per round, and cumulative full-battery pass. |
| **6. Compact and split guides** | Replace proved children with concise instances; retain B/D facts and procedures; split only at validated routing boundaries. | Done when every guide is under 16 KB, known routing situations load the correct chunk on both hosts, non-applicable controls do not, and hermetic packet coverage is reconciled. |
| **7. Deploy and revalidate** | Deploy the approved registered candidate; retain one-command version rollback; add derivability decay checks to rolling-window review. | Done when deployed hashes match approval, both hosts pass a smoke battery, rollback is demonstrated, and the next mining window reports parent/child recurrence separately. |

*Inference* — Stop wholesale distillation and fall back to item-level C+D if more than 25% of tested children fail across the first two families, if either host consistently diverges, or if a parent needs more than two exception clauses or exceeds the 50-token global bar.

## 6. Risks, failure modes, and material owner choices

- *Fact* — E4 demonstrates the central risk: abstract text can coexist with repeated behavioral failure.  
  *Inference* — Mitigation: never demote from logical entailment or recitation; require parent-only behavior at the acting point.

- *Inference* — A wrong broad principle can bias more decisions than several wrong directives.  
  *Inference* — Mitigation: provenance gate, one-family rollout, controls, explicit prohibitions, and immediate version rollback.

- *Inference* — Semantic judges can reward paraphrase while missing the operational act.  
  *Inference* — Mitigation: score atomic observable obligations, blind the arm, adjudicate PARTIAL, and expose raw failures to the owner.

- *Fact* — Claude and GPT have different prescription failure modes, while canonical text must be shared.  
  *Inference* — Mitigation: require both-host passage; retain host hooks only as derived accelerators.

- *Inference* — Guide splitting can replace token bloat with router-recognition failure.  
  *Inference* — Mitigation: enforce the ≥5-item route bar and test positive and negative routing situations before deployment.

- *Fact* — Hermetic reviewers and scripts read no global prose.  
  *Inference* — Mitigation: require a consumer-coverage check for every demotion; use packet injection, gates, or enforcement where they execute.

- *Inference* — Compression can hide only part of a bundled learning.  
  *Inference* — Mitigation: full-child pass by default; ledger splitting only when obligations have distinct triggers and homes.

- *Inference* — A model-native ablation pass can decay after a tier change.  
  *Inference* — Mitigation: retain a guide instance and rerun the child’s small battery when model identity changes.

Two owner choices materially change attainable savings:

- *Inference* — Default: do not demote the empirically effective security-posture trigger or other irreversible/authority recognition rules in the first cycle, even after a clean derivability screen. Allowing their demotion increases savings but materially increases regression blast radius.
- *Inference* — Default: fund `N=5` confirmation only for proposed demotions. If the run budget cannot support that sample, stop after screening and make no corpus deletion; reduced measurement depth must reduce migration scope, not the evidence bar.
