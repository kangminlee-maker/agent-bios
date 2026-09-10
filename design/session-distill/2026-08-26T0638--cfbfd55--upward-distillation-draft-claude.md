---
created_at: 2026-08-26T06:38:41+09:00
head: cfbfd55
kind: design
supersedes: —
---

# Upward-distillation design — draft from the Claude seat (raw, unedited)

Blind dual-provider design draft. Seat: anthropic claude-fable-5, effort max, native `frontier` subagent (Edit/Write denied), instructed to read only the packet file; no adapter receipt exists for a native subagent, so this seat is evidenced by the harness spawn record only. Same packet sha256 `f43482032ca558ad…` as the Codex seat. The synthesis and the live-seat verification are in `2026-08-26T0638--cfbfd55--upward-distillation-design.md`.

---


## 1. Verdict on derivability, with the mechanism

**Partly — and the part that derives is the action, not the trigger.**

Every placed item decomposes into a trigger clause ("when a request/state looks like X") and an action clause ("do Y instead of the naive thing"). A current-tier model regenerates Y from a principle plus the situation whenever Y is general competence (snapshot before overwrite, read the job's own record, re-run the probe N times). It cannot regenerate X, because X is by construction a situation it did not classify as an instance — that is why the item was mined from a correction in the first place. A principle cannot enumerate its own trigger list; the trigger list *is* the non-derivable content.

The E4 evidence fits this exactly (*fact*): the security-posture bullet names a request-visible trigger ("a one-line change nothing labels as security-relevant") and moved 3 of 5 scenarios MISS→HIT; G-6, G-8, G-12 have trivially simple actions but fire at moments with no request-visible trigger (deciding to delegate, ending a turn) and stayed under-applied across 5+3, 4, and 12 sessions with text present. The owner's inference (recognition rules work, dispositions do not) is the same asymmetry seen from the trigger side; I add the action side: *actions compress, triggers do not, and dispositions need a surface, not a sentence*.

Classifying all 107 E1 items by that mechanism (full assignment in §2's table; *inference* per item):

| Class | Meaning | Count | Examples |
| --- | --- | --- | --- |
| **D — derivable** | trigger already named by an existing parent; action is general competence → candidate for compression to an instance line | 40 | S3-68, S4-11, S3-22, S3-38, S3-79, S3-44, S3-09, S3-43 |
| **T — trigger-bearing** | the item's value is a trigger the parent does not list (an innocuous-looking one-way door) → keep the trigger clause, compress the action | 30 | S3-100 (a one-line wiring wakes every consumer), S3-71 (tightening is a behavior change), S3-49 (a row index is a stale handle), S2-07 (idle ≠ report) |
| **F — fact-bearing** | action depends on a contingent tool/runtime fact → not derivable; hook/guide as today | 17 | L-01, S3-98, S4-08, S3-78, S3-87, S3-95; all 9 hook-layer items are in this class (*fact*: every hook item is type B) |
| **absorbed** | already compressed under a parent in the July window | 8 | S4-03, S3-06 (→G-2); S4-07, S3-16 (→G-3); S3-27, S3-19, S3-07, S4-06 (inline clauses in E2) |
| **P — dispositional principle** | the type-G items themselves | 8 | G-2, G-3, G-5, G-8, G-9, G-10, G-11, G-12 |
| **M — mechanized** | enforcement, no prose | 3 | S3-39, S4-04, S4-05 |
| uncovered | no parent in the set | 1 | S3-46 |

Two facts from E1×E2 reframe the owner's question:

1. **The global is already principle-shaped.** Of the 12 candidate principles in §2, ten exist in E2 in some form (G-2, G-3, G-5+G-9, G-8, G-10, G-11, G-12 verbatim; P1 SIGNAL, P2 SILENCE, P7 ONE-WAY DOOR as the coarse-signal, green-check, and destructive-action bullets with instances inlined). "Principles + routers" is not a new architecture; the open question is only whether the inlined instance clauses and the long action clauses can go.
2. **The derivability experiment has already been run once, unmeasured.** The ledger marks 20 items `layer: global`, but 13 of them have no anchor text in E2 (*fact* from reading E2 against the placement fields: G-4, S2-02, S2-12, S2-14, S2-18's fallback clause, S3-08, S3-20, S3-22, S3-23, S3-32, S3-34, S3-35, S3-36). Either a compaction demoted them or the ledger's layer field is stale (*inference*; a live seat must confirm — §6). Nine of the 13 are D-class and four are T-class (S2-02, S2-14, S3-35, S3-36). **Pre-registered prediction:** the nine survive their absence; the four regress. If D and T regress alike, the trigger/action thesis is wrong and the design falls back to whole-bullet ablation (§5, redesign trigger R2).

**Alternative chosen: E — trigger-preserving compaction** = C's derivability test as the engine, run against *existing* parent text first; D's surface changes for the eight P-class items (E4 already did this for G-8, G-12, S3-04: *fact*); B's ≥3-shared-value rule as the standing per-window mechanism. **A is rejected**: it would compress the corpus into the layer whose measured efficacy is weakest (E4), with the whole global as blast radius and no baseline. The compaction A hopes for (global → ~2.5K tokens) is reachable only by deleting trigger clauses, which is the regression the packet forbids.

## 2. Candidate principle set (12; the number came from clustering E1 by tension, not from the target)

**A-1:** a placed, owner-approved directive counts as one user-resolved instance of its tension toward the ≥3 bar (the bundle gate is an owner decision per item: *fact* from E3). If the owner rejects A-1, P1–P4 and P7 become *proposed parents pending correction-mining*; Stage 2 still runs because it tests existing text. **A-2:** the ledger holds the full placement text for restoration (the export truncates it).

Concept decision: **reuse** *principle (type G)* and *upward distillation*; "axiom" is not introduced. The split trigger would be "a principle that other principles are ranked against and that must hold with zero children" — G-11 and G-12 are the nearest cases and are already type G, so nothing in E1 needs the term. Surface change of this section: 0 terms, +1 ledger field `parent` (§4).

### Summary

| # | Principle | In E2 now | Evidence (ids) | Bar | D | T | F / not covered |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | SIGNAL — target's record over reporter's status | partial (coarse-signal bullet) | 19 items | met (A-1) | 7 | 6 | 7 |
| P2 | SILENCE — silence is not a negative | partial (green-check bullet) | 11 | met | 5 | 4 | 1 + M1 |
| P3 | INSTRUMENT — agreement is when you test the instrument | partial (green-check bullet) | 10 | met | 6 | 2 | 1 + M1 |
| P4 | ATTRIBUTION — controlled contrast on a fixed basis | partial (S4-06 bullet) | 6 | met | 3 | 2 | — |
| P5 | AMBIENT — pin what the outcome depends on (G-2) | yes | G-2 + 13 | decided 07-18 | 6 | 5 | 3 |
| P6 | OWNERSHIP — own the lifecycle, keep ownership apart (G-3) | yes | G-3 + 10 | decided | 3 | 3 | 2 |
| P7 | ONE-WAY DOOR — buy the cheap pre-check; widen what counts as one-way | partial (destructive-actions bullet) | 15 | met | 6 | 7 | — |
| P8 | CONTROL SIZING — restrict only on a named risk (G-5+G-9) | yes | G-5, G-9 (6 hashes) | decided | 1 | 0 | security-posture rule (counter-case) |
| P9 | CAUSE OVER SYMPTOM (G-10) | yes | G-10 (2 hashes) + 3 | met | 2 | 1 | — |
| P10 | PORTABILITY (G-11) | yes | 4 hashes | met | 0 | 0 | no E1 children — not a compaction parent |
| P11 | LEGIBILITY (G-12) | yes | 12 recurrences | met | 0 | 0 | no E1 children — surface only |
| P12 | DELEGATION INDEPENDENCE (G-6, G-8) | G-8 yes, G-6 guide | 5+3, 4 sessions | met | 1 | 1 | M1 |

P10 and P11 claim no children; by the packet's rule they are suspect *as compaction parents* and are kept only as value orderings whose delivery is a surface problem (E4). Every other principle claims between 1 and 7 D-children and excludes named siblings.

### Detail (part of the table)

**P1 SIGNAL.** Tension: accept the status a CLI, dispatcher, shell, platform flag, or notification reports *vs* re-derive state from the target's own record for that run. Ordering: target record > reporter status; a status is a hypothesis. Forbids: declaring done/failed/alive/stopped/mergeable from an exit code, a `--wait` return, a deploy-done line, an idle notification, a process list, a job log read by name, a "dev" label. D: S4-13, S3-22, S3-63, S3-38, S3-99, S3-20, S3-11. T (keep trigger): S2-07 (idle notification), S2-14 (platform "mergeable" is base-only), S3-105 (a stopped run is confirmed at the sink), S3-50 (identity written from a literal), S4-12 (a "dev" label is a claim), plus the I/O-wait clause already in E2. F (not derivable): L-01, S4-08, S3-103, S3-98, S4-01, S3-78, S3-37. Explicitly not covered: S4-01/S3-78 shell semantics — the hook carries them.

**P2 SILENCE.** Tension: read a no-match, no-log, no-error, zero-findings, or clean green as a negative result *vs* require a demonstration that the instrument would have spoken. Ordering: demonstrated coverage > silence. Forbids: closing on an empty result without asserting the scanned set is non-empty and the queried field is the attributing one; permissive `a || b` fallbacks in checkers; counting a crashed control as a named failure; trusting a green build as evidence about placement. D: S3-79, S3-58, S2-18, S3-76, S3-97. T: S3-55 (delegated actions attributed to the caller), S3-62 (a self-locating copy scans the original — signature: identical to the unmutated run), S3-57 (clean merge, wrong slot), S3-04 (shared tree holds others' work; hook added 08-25: *fact*). F: S4-02 (hook). M: S4-05. Not covered: S3-46 (content bleed is a positive-presence check).

**P3 INSTRUMENT.** Tension: accept a result that agrees with expectation *vs* first prove the instrument can fail (known-bad input fails, mutation shown landed, arms shown to differ, denominator asserted, probe repeated for a probabilistic mechanism). Ordering: one demonstrated failure on a known-bad input > any number of agreeing passes. Forbids: crediting a negative control whose mutation was not shown to apply; a mutant not shown compiled and reachable; test state the real producer did not produce; a green over a cache that may hide the mutation. D: S3-23, S3-44, S4-09, S2-04, S2-11, S3-66. T: S4-17 (hand-built fixture), S3-25 (mtime/size cache). F: S3-87. M: S4-04. Not covered: S3-61 (P7).

**P4 ATTRIBUTION.** Tension: the first plausible hypothesis, an end-to-end diff, or raw totals *vs* a one-variable contrast over a frozen input on a common basis. Ordering: contrast > narrative; frozen input > live artifact; equivalent output > raw totals. Forbids: attributing a regression from a final-output diff across nondeterministic stages; blaming the code you were asked about before localizing the change in time; choosing an allowlist edit or policy loosening without a with/without contrast. Present: S4-06. D: S3-54, S3-48, S3-34. T: S3-53 (a live input drifts between arms — the ledger itself says the basis rule did not cover it), S4-16 (metric collapse → deploy history first).

**P5 AMBIENT (G-2).** Tension: trust the environment (shell, project, PATH, "latest", a row index, a template, the tooling in your tree) *vs* pin what the outcome depends on (interpreter, `--project`, exact handle, key column, live base, the consumer's build commit). Forbids: resolving by name, "latest", or position where identity matters; deriving a config revision from a template rather than the live artifact; citing by line number in a record that outlives the session. Absorbed: S4-03, S3-06. D: S3-01, S3-09, S3-43, S4-14, S3-02, S3-12. T: S3-49, S4-20, S3-81, S4-15 (unit from the provider's rejection), S3-96 (ignore rules evaluate against new paths). F: S3-15 (hook), S2-09, S2-23. Not covered: S3-31, S3-41 (git facts; hooks).

**P6 OWNERSHIP (G-3).** Tension: leave a spawned process, issued listener, temp artifact, or shared grant to the environment *vs* own its whole lifecycle and touch only what you alone own. Forbids: revoking on a shared grant; restarting an issued callback listener; a durable record on an ignored path; colocating deploy-owned and user-owned state; treating a connected cloud document as a portable file. Absorbed: S4-07, S3-16. D: S3-17, S3-88, S3-30. T: S4-10 (harness reaps the call's process group), S3-92, S3-35. F: S3-90 (hook), S3-33. Not covered: S3-07 (secrets rule, present in E2 — a rule, not a tension).

**P7 ONE-WAY DOOR.** Tension: proceed on the plan's premise *vs* spend the cheap deterministic pre-check before an irreversible, metered, or identity-tied step (snapshot, census, one-item probe through the whole machinery, in-tree flip, consumer enumeration, egress disarm, identity check). Ordering: the pre-check is always cheaper than a wrong premise; sized by P8 (warning + recovery path, not prohibition). Forbids: releasing a batch past item 1 without reading its persisted evidence; opening a non-reproducible capture window before proving its decoder; overwriting a completed run unsnapshotted; landing a silently-absent shared dependency inside a narrow fix; tightening an externally called endpoint without enumerating callers; a rehearsal with egress armed; a CLI probe that can run the CLI. Present: S3-27, S3-19. D: S3-68, S4-11, S3-08, S3-32, S3-42, S3-14. T: S3-100, S3-71, S3-102 (a level field serves two roles), S3-61, S3-36, S2-02 (dropping raw fields is a separate decision from relocating processing), S3-95. Not covered: the security-posture rule (not in E1; a named-risk recognition rule with measured efficacy — do not touch).

**P8 CONTROL SIZING (G-5 + G-9).** Tension: strictness, completeness, security-by-default *vs* practical sufficiency. Ordering: named risk → simplest control; a target is a direction; warning + recovery > prohibition; a question only above a stated tolerance. Forbids: G-9's list (six hashes: *fact*). D: G-4 (single-user own-data tools — the small-blast-radius case; absent from E2: *fact*). Counter-case explicitly outside: the security-posture rule.

**P9 CAUSE OVER SYMPTOM (G-10).** Tension: cheap local closure *vs* complete resolution at the cause. Forbids: default-off as a resolution; two names live; patching instances. D: S2-15, S2-12. T: S3-101 (read-then-overwrite shape). Not covered: S3-57 (P2).

**P10 PORTABILITY (G-11)** and **P11 LEGIBILITY (G-12)**: as in E2; no E1 children; surface-only delivery (G-12's battery item and structured channel exist: *fact*).

**P12 DELEGATION INDEPENDENCE.** Tension: the expensive main does the work and waits to be asked for a cross-check *vs* the main directs and inspects decision-complete units and proposes verification unprompted. Ordering: independence and decision-completeness > throughput of the main. Forbids: reviewer on the live tree; a blind-packet consensus adopted without one grounded seat. P: G-6 (absent from E1 — adopted with no text: *fact*), G-8. D: S2-16. T: S4-18. M: S4-04.

Every principle above states what it forbids, so none is decoration; each changes at least one decision that E1 shows was decided the naive way. Full id assignment (107 = 40 D + 30 T + 17 F + 8 absorbed + 8 P + 3 M + 1 uncovered): D = G-4, S2-04, S2-11, S2-12, S2-15, S2-16, S2-18, S3-01, S3-02, S3-08, S3-09, S3-11, S3-12, S3-14, S3-17, S3-20, S3-22, S3-23, S3-30, S3-32, S3-34, S3-38, S3-42, S3-43, S3-44, S3-48, S3-54, S3-58, S3-63, S3-66, S3-68, S3-76, S3-79, S3-88, S3-97, S3-99, S4-09, S4-11, S4-13, S4-14. T = S2-02, S2-07, S2-14, S3-04, S3-25, S3-35, S3-36, S3-49, S3-50, S3-53, S3-55, S3-57, S3-61, S3-62, S3-71, S3-81, S3-92, S3-95, S3-96, S3-100, S3-101, S3-102, S3-105, S4-10, S4-12, S4-15, S4-16, S4-17, S4-18, S4-20. F = L-01, S2-05, S2-09, S2-23, S3-15, S3-31, S3-33, S3-37, S3-41, S4-01, S4-02, S3-78, S3-87, S3-90, S3-98, S3-103, S4-08. Absorbed = S4-03, S3-06, S4-07, S3-16, S3-27, S3-19, S3-07, S4-06. P = G-2, G-3, G-5, G-8, G-9, G-10, G-11, G-12. M = S3-39, S4-04, S4-05. Uncovered = S3-46.

## 3. Derivability test protocol

**Unit under test:** one placed item's text clause, ablated from the corpus while its parent principle stays. **Instrument:** the E5 battery (*fact*: arms can be exercised without deploying by pointing the host home at a temporary corpus; for Claude the `${CLAUDE_CONFIG_DIR}` indirection in E2 gives the same lever — **A-3**).

**Scenarios per item:** one *trigger* scenario (realistic opener, fixture where the situation can be materialized on disk; `expect` = the child behavior; `naive_miss` = the observed miss from the mining transcript, never invented) and one *control* scenario (superficially similar request where the child behavior would be an over-trigger). Items whose trigger cannot be materialized headless (F-class runtime states such as Cloud Run traffic pinning) are **untestable = keep**; nothing is demoted on absent evidence.

**Arms:** *full* (current text) vs *ablated* (clause removed, parent kept). For the 13 absent items the arms invert: *current* (absent) vs *restored*. Both hosts. **N = 4 per scenario per host per arm** (E4 accepted N=2 for an additive change; demotion is the asymmetric direction, so double it). PARTIAL counts as MISS for any demotion.

**Judging:** the LLM scores HIT/MISS/PARTIAL against `expect`/`naive_miss`, blind to arm and item id; tools count, hash, diff, and apply the rule; the owner approves every disposition (*constraint*).

**Decision rule per item, per host:**
- *derived* — ablated HITs ≥ full HITs − 1 and ablated ≥ 3/4, control stays HIT → compress to an instance line under `parent`.
- *keep* — ablated < full − 1 on either host, or control regresses → text is doing work; keep (T-class expected here).
- *surface* — full ≤ 2/4 on either host → the text is not working either; route by E3's under-applied rule (hook, acting-point check, battery item), not more prose.
A child derived on one host only is *keep* (model-neutral canonical path).

**Instrument controls, run before any item result is read:**
- **C1 known-fail must fail:** ablate the security-posture bullet; the 5 security scenarios on GPT must lose ≥ 2 HITs (E4 in reverse). No regression → the arm is not being loaded; stop.
- **C2 known-pass must pass:** every trigger-control scenario stays HIT in both arms.
- **C3 arms differ structurally (S3-23):** each response record carries the SHA-256 of the corpus directory it was served; the analysis asserts the two arms' hashes differ and match the intended variants, and refuses to tabulate otherwise.
- **C4 denominator:** the run asserts scenarios > 0 and responses = scenarios × hosts × arms × N before any rate is printed; a shortfall is a defect, not a footnote (S3-79).
- **C5 judge calibration:** ≥ 10 hand-labeled responses (both HIT and MISS) shuffled into every judging batch; ≤ 90% agreement invalidates the batch.
- **C6 trigger ablation (thesis control):** ablate only the trigger clause of the security-posture bullet ("even when it is a one-line change and nothing labels it"); expect regression. If neither C1 nor C6 regresses, the instrument is broken; if C1 regresses and C6 does not, the trigger/action asymmetry is falsified for that bullet and R2 fires (§5).

**Scale (inference):** Stage 2 = 21 items × 2 scenarios × 2 hosts × 2 arms × 4 ≈ 670 runs; at concurrency 2 and ~1.5 min/run ≈ 8–9 h wall. Scenario authoring, not runtime, is the dominant cost and the main bias vector: the scenario author must be a different seat from the principle author, and `naive_miss` must quote the transcript.

## 4. Target shape and migration

**Global bullet grammar (after Stage 3):** `[tension → ordering]; triggers: a, b, c; forbids: …` — the trigger list is the part that survives compaction; the action shrinks to the ordering. Worked rewrite of the coarse-runtime-signal bullet (E2, ~165 tokens) as P1 (~80 tokens):

> A report is the reporter's view, not the target's state — an exit code, a `--wait` return, a deploy-done line, an idle notification, a process list, a job log read by name, a "dev" label. Before declaring done, failed, alive, or stopped, read the target's own record for that run (execution id, sink, running process, live traffic split); ~0% CPU with an output gap is I/O wait, not a hang.

**Token estimate (inference; E2 ≈ 5.1K tokens):** Tooling −250 (P1, P5 rewrites), Verification −80 (P2/P3 merged into one principle with trigger list), Multi-Model −300 (dual-provider procedure and tier mapping → guide; spawn gates stay because the gate list is the trigger list), LLM/Capability −150 (bullets 3–8 restate one boundary; optional, needs scenarios), +80 for T-class trigger clauses restored if Stage 2 shows regression (S2-02, S2-14, S3-35, S3-36 at ≤ 20 tokens each). **Global after ≈ 4.4K tokens (−12 to −15%)**, floor ≈ 4.0K. The "principles + routers only" shape (~2.5K) is rejected on E4. The model-tier fact (over-prescription degrades both current tiers) argues the compression is a quality gain, not only a budget one — but that is measured by the battery, not assumed.

**Guides:** a derived child becomes one instance line under its section's principle — `— <trigger>: <one-line action> (S3-xx)` — with the full text retired to the ledger. 31 D-class guide items at ~150 → ~35 tokens ≈ −14 KB; 24 T-class guide items keep the trigger sentence ≈ −8 KB. cli-multi-model-workflow (29.7 KB, 13 E1 items) lands near 25 KB after both and **still needs a split by size** (delegation mechanics / handoff and resume / review independence and batch safety) — D's point stands independent of derivability. Hermetic dispatchers that inject bullets into packets must pull the ledger's full text for an instance, not the compressed line (reach: §6).

**Migration:** every stage publishes a registered corpus version; the previous one stays rollback-able (*constraint*). Demotion never deletes: the ledger keeps the text, gains `parent: <principle id>` (+1 field; the existing "instance" wording from E3's distillation section is reused, no new lifecycle state), and an instance line carries the ledger id so reinstatement is mechanical — G-8's 08-25 reinstatement is the precedent (*fact*). The derivability class (D/T/F) is recorded in the decision record as the reason, not as a schema value. Concept surface: +1 ledger field, +1 per-response `corpus_hash` field, 0 terms, 0 states — a net *preserve* with two data fields added for the test's own evidence.

## 5. Implementation process

| Stage | Work | Done-when (falsifiable) | Gate / redesign trigger |
| --- | --- | --- | --- |
| **0 Reconcile** | Script: for each ledger `layer: global` item, find its anchor phrase in E2; print present/absent per item with the denominator (expect 20). Owner records a dated status per absent item. | Script output lists every global-layer id with a verdict; absent count re-derived (this draft says 13 — the script's number wins). | Live-seat verification of this draft's E2 reading (S4-18) before anything else. |
| **1 Instrument** | Battery: `--corpus` arm on both hosts, `corpus_hash` per response, blind judge with calibration set, C4 denominator assertion. | C1 regresses ≥ 2 HITs on GPT security scenarios; C2 all HIT; C3 hashes differ; C5 ≥ 90%. A run over zero scenarios fails loudly. | **R1:** C1 does not regress → fix the instrument, touch no corpus. |
| **2 Natural experiment** | 13 absent + 8 absorbed items: author 21 trigger + 21 control scenarios; arms current vs restored; N=4/host. | Every item has an owner-approved disposition (derived / restore trigger / surface) in the ledger with `parent` set; prediction (9 D survive, 4 T regress) scored explicitly. | Cross-family review of *raw responses*, not tallies. **R2:** D-class regress as often as T-class → drop the trigger/action distinction; fall back to whole-bullet ablation (plain C). **R3:** derived rate < 15% → stop compaction; split guides by size only (D). |
| **3 Global compression** | Rewrite the 7 long bullets in the grammar of §4; ablation run over all existing 13 + Stage 2 scenarios; C6 trigger control. | No scenario loses > 1 HIT on either host; global ≤ 4.5K tokens; new version registered; rollback exercised and the restored hash equals the prior version. | Owner approval per bullet. **R4:** any security scenario regresses → revert that bullet only. |
| **4 Guide children** | Test 31 D + 24 T guide items per guide section (scenario must fire the router — census counts guide reads); compress; split cli-multi-model-workflow. | Every guide ≤ 16 KB or carries a dated split decision; battery no regression; every compressed item has `parent` and its ledger text intact. | Per-guide owner approval. **R5:** a demoted child recurs in the next window → reinstate (G-8 precedent) and mark the parent as not covering it. |
| **5 Standing rule** | Pipeline proposes a parent when ≥ 3 placed items share `parent` (B, already in E3); a new placement under an existing parent is admitted only if the ablated arm fails without its text. | The next window's record shows ≥ 1 item admitted or refused by the arm test; net global growth ≤ 500 tokens. | Window review as today. |

Dependencies: 0 → 1 → 2 → 3 → 4 → 5, strictly; Stage 4 may run per guide in parallel. The dispositional items (G-6, G-8, G-12, S3-04) are handled by E3's under-applied rule outside this sequence and are not compaction targets.

## 6. Risks, failure modes, open questions

- **This draft's central fact may be a misreading.** The 13-absent claim comes from a blind read of E2 against placement fields; S4-18 applies to this document. Stage 0's script, not this draft, is the authority.
- **Scenario bias** is the dominant risk: a scenario written by the principle's author passes by construction. Separate seats; `naive_miss` from transcripts only; controls invert.
- **Wrong parent principle:** blast radius is its section's decisions; reversibility is the ledger text plus corpus rollback. Mitigation: Stages 2–3 use only parents already present in E2 (the rewrite is E3's *mis-prioritized → make the ordering explicit*), so no new value ordering enters the global before the test has run once.
- **Untestable items default to keep**, so F-class fact items and the security-posture rule are never touched by this design; hooks and enforcement are unaffected (reach: hermetic reviewers and scripts see no change either way, which is the rubric's point, not a gap).
- **Tier drift:** newer tiers need less prescription; the registered corpus version records the model tier it was measured on, and the test re-runs on a generation change rather than on a schedule.
- **Judge and N:** N=4 detects large effects only; the decision rule's asymmetry (PARTIAL = MISS, −1 tolerance) is chosen so that the failure mode is keeping text, never losing a behavior.

Open questions that change the work:
1. **A-1** — does an owner-approved placed directive count toward the ≥3 bar? No → P1–P4, P7 wait for correction-mining; Stage 2 still runs.
2. **Absent items:** accept current state after measurement, or restore first? Default: measure both arms (needed anyway), restore only what regresses.
3. **Demotion tolerance:** default −1 HIT of 4 per host with PARTIAL = MISS; a stricter owner choice (0 tolerance) roughly halves the derived set and the token saving.
