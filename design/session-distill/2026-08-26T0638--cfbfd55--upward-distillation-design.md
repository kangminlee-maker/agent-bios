---
created_at: 2026-08-26T06:38:41+09:00
head: cfbfd55
kind: design
supersedes: —
---

# Upward distillation — can the placed learnings be derived from a small set of principles?

Status: **decided 2026-08-26 (§7 1–7, all at the recommended default); Stage 0 in progress — two
cross-family review rounds adjudicated (§9): round 1's 19 and round 2's 20 admitted findings are
applied to this revision; round 2 achieved `packet_binding=bytes`. Stage 0 closed 2026-08-26 by owner decision: the round-2 residual is accepted as Stage-1
acceptance tests (a third prose round was declined). Committed on two review rounds.** Nothing here has been applied to the corpus; the ledger change in
Stage 0 is the only artifact edit this record authorizes. The two blind drafts this synthesizes are the sibling records
`…--upward-distillation-draft-codex.md` (gpt-5.6-sol/max, hermetic, receipted) and
`…--upward-distillation-draft-claude.md` (claude-fable-5/max, native subagent). Re-derive every
count from `ledger.json` and the corpus before acting on a number in this file.

## 1. Verdict

**Partly, and the part that derives is the action, not the trigger.** Both seats reached "partial
derivability" from the same packet (the Claude draft is not receipted, so that convergence is
suggestive, not evidence); the Claude seat supplied the mechanism, which the live evidence in §3 is
*consistent with* — the August audit measured text and router wording, so the behavioral half of
the claim (a model regenerates the action from a principle) is a hypothesis until §5 runs. The
mechanism: a placed item is a *trigger* clause ("when it looks like X") plus
an *action* clause ("do Y instead"). A current-tier model regenerates Y from a principle whenever Y
is general competence; it cannot regenerate X, because X is by construction the situation it failed
to classify — that is why the item was mined from a correction. Tool facts (type B) and multi-step
procedures (most type D) add a *fact burden* the principle cannot carry either (the Codex seat's
axis). Dispositions that fire at a moment the agent does not experience as a trigger (G-6, G-8,
G-12) are not compression material at all; they need a surface.

Consequences the owner asked about:

- **"Axioms"**: not introduced. Both seats chose *reuse* of the existing terms *principle* (type G)
  and *upward distillation*; no split trigger fired. Concept surface: 0 new terms.
- **Alternative A (global = principles + routers only)**: rejected by both seats. It would move the
  corpus into the layer whose measured efficacy is weakest (E4) with the whole global as blast
  radius, and the compaction it hopes for (~2.5K tokens) is reachable only by deleting trigger
  clauses — the regression the placement framework forbids.
- **What the global becomes**: it is *already* principle-shaped — ten of the twelve candidate
  tensions exist in it in some form. The change is a grammar, not an architecture: each long bullet
  becomes `[tension → ordering]; triggers: a, b, c; forbids: …`, where the trigger list is what
  survives and the action shrinks to the ordering. Estimated global 5.1K → ~4.4K tokens (−12–15%),
  floor ~4.0K (inference; measure with `session-cost.py`).
- **The guide split**: settled on size alone, independent of derivability — both seats agree
  `cli-multi-model-workflow` (29.7 KB) still needs a split after compaction.

## 2. Adjudication — what the two drafts said, where they differed, why the synthesis chose

FRONTIER disposition: **the prior frame changed.** The handoff's plan (cluster → 8–12 axioms →
derivability test → global = axioms + routers) is replaced: the unit of derivability is the clause,
not the bullet; the global keeps its sections; and the first test population is one that already
exists (§3), not one to be built.

| Rubric (in order) | Codex seat | Claude seat | Chosen |
| --- | --- | --- | --- |
| 1 Behavioral efficacy, measured | 4 arms (registered / explicit-child / parent-only / ablation), N=2 screen → N=5 confirm, 240 responses per child; judge known-good/bad, load canary, denominator, hardening control | 2 arms (full / ablated; inverted for absent items), N=4, PARTIAL=MISS, ~670 runs for the first population; controls C1–C6 including a *thesis* control (C6) and a pre-registered prediction | **Claude** skeleton — falsifies its own thesis and is 3× cheaper; **graft** Codex's ablation arm (neither parent nor child) at confirmation only, to tell *derived* from *model-native* |
| 2 Wrong-principle risk | 4 of 10 principles provisional pending provenance; pilot one family first | Stages 2–3 use only parents already in the global; new orderings enter only after one measured cycle | **Claude**; graft Codex's stop rule (>25% of tested children fail across the first two families → stop compaction, fall back to prune-and-surface) |
| 3 Token cost | first migration 18–19 KB, mature 16.5–18 KB | 5.1K → ~4.4K tokens with a worked rewrite of one bullet (165 → 80 tokens) | same magnitude; Claude's estimate is itemized, so it is the one to measure against |
| 4 Reach | consumer-coverage check per demotion | hermetic dispatchers inject the ledger's *full* text for an instance line, never the compressed line | both; Claude's is the concrete rule |
| 5 Concept economy | new "canonical manifest" artifact (parent, obligations, hashes, receipts) | +1 ledger field `parent`, +1 per-response `corpus_hash`, 0 terms, 0 lifecycle states | **Claude** — the manifest duplicates what `ledger.json` + `versions.json` + decision records already own |
| 6 Implementation cost | 8 stages, heavy confirmation | 6 stages, natural experiment first | **Claude**; graft Codex's atomization rule (bundled entries such as S3-96, S3-105 split before testing) and its guide-split boundaries |
| Coverage of the 107 | 59 ids assigned, 48 unassigned (deferred to its Stage 1) | all 107 assigned (40 D / 30 T / 17 F / 8 absorbed / 8 P / 3 M / 1 uncovered) | Claude's assignment is the working list; every id was checked to exist in the ledger |

Convergence worth noting — and its limit. The two clusterings agree on nine tensions (signal from
the target's record; silence/instrument; ambient state; ownership; one-way doors; control sizing;
cause over symptom; portability; legibility and delegation as surface-only). They differ only in
granularity: Codex splits one-way-door into *reversibility* vs *lateral blast radius* and
control-sizing into *proportion* vs *utility*; Codex has no *attribution* (S4-06 family) parent.
Both saw the same packet, so agreement is partly evidence about the packet's framing; the
granularity questions are left to Stage 3 authoring, where the arm test can decide them.

Provenance. Codex: `ReviewReceipt/v1`, packet sha256 `f43482032ca558ad…`, result sha256
`d2667c3b136a4b…`, seat `openai/gpt-5.6-sol/max`, exit 0. Claude: native `frontier` subagent
(Edit/Write denied, instructed to read only the packet file) — no adapter receipt exists for that
mechanism; the harness spawn record is the only evidence of the seat. Both drafts are design input,
not verdicts, so the receipt gap does not make anything here PROPOSED that would otherwise be
achieved; the review of the *synthesis* (§6, Stage 0) is where receipts matter.

## 3. Live-seat verification of the drafts' load-bearing claims

Both seats were blind; before adopting a converged claim, one seat with read access had to try to
falsify it (cli-multi-model-workflow, "evidence access is its own axis"). Results, this session:

1. **"13 of the 20 `layer: global` ledger items have no anchor text in the current global"** — the
   Claude seat's central fact, offered with a request for live verification. **Confirmed exactly**:
   a phrase probe over `claude/CLAUDE.md` finds 7 present (S4-06, S3-07, S3-19, S3-27, G-2, G-3,
   G-5) and 13 absent (S3-08, S3-20, S3-22, S3-23, S3-32, S3-34, S3-35, S3-36, S2-02, S2-12,
   S2-14, S2-18, G-4) — the same 13 the draft named. All 13 are present in a guide, each verified by reading the
   passage rather than by the phrase probe alone — the probe's phrases missed S3-22's passage
   (tooling-gotchas.md: "confirm the running process's actual version/behavior or force a
   restart"), and a first probe for S2-14 matched an unrelated global sentence on the word
   "sibling"; both are recorded in the review evidence (E-B B1). Homes: tooling-gotchas (S3-20,
   S3-22, S3-32, S3-34, S3-36, S2-14), verification-discipline (S3-08, S3-23, S2-18, G-4),
   coding-staged-workflow (S2-02, S2-12), mock-realization-boundary (S3-35).
   Cause: the surface-placement initiative's global→guide sweep, commits `470cf83`…`b8ec606`
   (2026-08-05 → 08-08). **The ledger's `layer` field is stale for these 13** — a G2 fidelity gap
   the ledger merge did not catch because it tracks recurrence, not corpus location.
2. **The derivability experiment has already run once, unmeasured — and was audited textually.**
   `design/surface-placement/2026-08-08T1534--b8ec606--semantic-preservation-audit.md`: five
   hermetic gpt-5.6-sol seats audited all 40 demoted bullets against the absorbing guides. Tally
   **0 LOST, 2 WEAKENED, 21 TRIGGER_GAP, 17 PRESERVED**; commit title: *"The sweep preserved the
   text and lost the triggers."* That is the trigger/action asymmetry observed from the router
   side, eighteen days before either seat proposed it. The audit measured text and router wording,
   not behavior; the protocol in §5 is its behavioral counterpart, and its 40 bullets are
   population 2 in §5.
3. **Recurrence after demotion.** The August window (census to 2026-08-25, i.e. ~17 days of
   observation after the sweep) recorded recurrences for 12 ledger entries; **none of the 13
   demoted items is among them.** Weak — short window, and the screeners look for new lessons
   rather than for old ones — but consistent with the pre-registered prediction that D-class items
   survive their absence (9 of the 13 are D-class in the Claude seat's assignment; the 4 T-class
   are S2-02, S2-14, S3-35, S3-36).
4. **Every placed id either seat cited exists and is `status: placed`** (Codex 59/59, Claude
   107/107; no id was invented).

## 4. The mechanism and the principle set (working list, not approved)

Classification of the 107 by the mechanism — the Claude seat's assignment, adopted as the working
list; its per-id table is in the draft record and is the authority for which id sits where:

| Class | Meaning | n | Disposition |
| --- | --- | ---: | --- |
| D derivable | trigger already named by an existing parent; action is general competence | 40 | candidate for compression to an instance line — **only after the arm test** |
| T trigger-bearing | the item's value is a trigger the parent does not list | 30 | keep the trigger clause, compress the action |
| F fact-bearing | action depends on a contingent tool/runtime fact (all 9 hook items are here) | 17 | untestable headless → keep as today |
| absorbed | already compressed under a parent in July | 8 | — |
| P dispositional principle | the type-G items | 8 | surface, not compression parents (G-6, G-8, G-12 especially) |
| M mechanized | enforcement, no prose | 3 | — |
| uncovered | S3-46 | 1 | stays a bullet |

Twelve candidate tensions (Claude numbering; Codex counterpart in parentheses). Ten exist in the
global already; all state both sides, an ordering, and what they forbid — the detail is in the
draft record and is not repeated here:

P1 SIGNAL — target's record over reporter's status (Codex P6) · P2 SILENCE — silence is not a
negative · P3 INSTRUMENT — agreement is when you test the instrument (P2+P3 ≈ Codex P7; the Claude
seat itself proposes merging them at Stage 3) · P4 ATTRIBUTION — controlled contrast on a fixed
basis (no Codex counterpart) · P5 AMBIENT = G-2 (Codex P1) · P6 OWNERSHIP = G-3 (Codex P2) · P7
ONE-WAY DOOR — buy the cheap pre-check; widen what counts as one-way (Codex P8 blast radius + P9
recovery) · P8 CONTROL SIZING = G-5 + G-9 (Codex P3 + P4) · P9 CAUSE OVER SYMPTOM = G-10 (Codex
P5) · P10 PORTABILITY = G-11 (Codex P10; no children — not a compaction parent) · P11 LEGIBILITY =
G-12 (no children; surface only) · P12 DELEGATION INDEPENDENCE = G-6 + G-8 (surface only).

Evidence bar (owner decisions 1 and 5, §7): a principle's instances are the **distinct supporting
sessions** across the children assigned to it, cluster-deduplicated — never the number of placed
rows (61 of the 107 rest on one session each). Counted from the ledger against the Claude seat's
assignment, 2026-08-26: P1 24 · P2 19 · P3 19 · P4 11 · P5 27 · P6 15 · P7 18 · P8 8 · P9 6 ·
P12 12 — every candidate clears ≥ 3 with margin. The count is re-run by script at Stage 3 for each
parent as finally written (children change when P2/P3 merge or P7/P8 split), and a parent below 3
is not written.

Untouchable regardless of test outcome: the security-posture rule (a named-risk recognition rule
with measured efficacy — E4's positive case), hooks, enforcement, gates.

## 5. The derivability test (falsifiable)

Two questions, and for the 13 absent items **three corpus states** — *current* (child in a
router-gated guide only), *restored* (child also in the global), *ablated* (child in no carrier,
parent kept). Round-1 review found the first draft conflated the questions; round 2 found the
second draft counted only two states.

- **Reach (2a)** — does a rule still fire when it lives only in a router-gated guide? Arms
  *current* vs *restored*. Population: the 13 absent items only; the 8 absorbed items are inline in
  the global today and have no guide-only state, so they take no 2a.
- **Derivability (2b)** — does the parent plus the situation regenerate the child's behavior with
  the child absent from every carrier? Arms *current* (= *full*) vs *ablated*. Population: all 21.
  Demotion candidates get a third arm at confirmation, *neither* (parent and child both absent).

**Absence is semantic, not lexical.** An *ablated* or *neither* variant is accepted only when (i)
grep over the variant finds none of the ledger's phrases for the child, and (ii) a blind seat reads
each carrier section the child lived in and answers "does this section instruct the child's
behavior?" — with a known-paraphrase positive control (a section that carries the behavior under
other words, as tooling-gotchas carried S3-22) that the seat must flag. Hook-payload ablation is
proven by the hook's own self-test over the variant's rule file.

**Instrument.** The `benchmarks/` battery extended with: a `--corpus <dir>` arm on both hosts; a
**scenario manifest** written and hashed before any run — one row per (item, obligation, scenario
role, arm, host, repetition), with each item's `guards` field (`irreversible` | `authority` |
`security` | `none`, proposed by the LLM, approved by the owner) and the accepted model id and
effort per host; a **load canary per carrier** — a marker line in the variant's global and in the
guide the scenario's router loads — whose verdict every response record carries; a fresh
session per response, evidenced by the host-returned session/thread id in the receipt; the fixture
reset to a hashed snapshot before every response; arms interleaved; and a **receipt per response**
bound to bytes: sha256 of the exact request sent (opener + fixture manifest), the session id, host,
model, effort, arm, scenario, repetition, `corpus_hash`, `fixture_hash`, canary verdicts, and the
result hash. A response whose request hash is not the manifest's expected hash for its cell, or
whose seat is outside the accepted set, is a defect, not data.

**Scenarios per item (4):** a *trigger* whose opener is the user's situation as stated in the
mining transcript, or a paraphrase that names no action — the child's action must not appear in
the opener; a *transfer* in another domain; an *adversarial* where the naive wrong action is
attractive; a *control* where the child behavior would be an over-trigger. `naive_miss` quotes the
transcript. Scenario author ≠ principle author. Bundled ledger entries (S3-96, S3-105 and their
like) are atomized into obligations first, and the manifest maps every obligation back to its
original id — an original is dispositioned only when all its obligations are. An item whose
trigger cannot be materialized headless is *untestable = keep*.

**Judging.** Where the child's action leaves a trace, a deterministic postcondition decides
HIT/MISS, and each postcondition has its own known-bad probe (the reset fixture must fail it before
any action) and known-good probe. The LLM judges only where no artifact can exist, blind to arm and
id, against `expect` / `naive_miss`; the judge call is itself receipted (judge seat,
judging-packet hash, labels bound to the result hashes they judged). Calibration per batch: ≥ 10
hand-labeled responses including, for each item under judgment, its own `naive_miss` (MISS), an
`expect`-conforming response (HIT), a paraphrased near-miss that reuses `expect` vocabulary but
takes the naive action (MISS), and a response that mentions the naive action but performs the
expected one (HIT). **Every item's four calibration labels must be correct** — a batch rate < 90%
also invalidates. Tools count, hash, diff, and apply the rule; the owner approves every
disposition; no automated judge is confirmation.

**N:** 4 per scenario per host per arm (owner decision); PARTIAL = MISS for any demotion.

**Reach rule (2a), per host, positives only:** *restore-trigger* if on any positive scenario
*restored* HITs exceed *current* HITs by ≥ 2 (of 4); *guide-is-enough* if *current* ≥ 3/4 on
every positive scenario; otherwise *keep-in-guide-and-watch* (R5). A host that says
*restore-trigger* decides: the trigger clause returns to the global for both hosts.

**Derivability rule (2b), per host, evaluated in this order, exhaustive:**

1. *surface* — *full* ≤ 2/4 on any positive scenario: the text is not working; route by the
   framework's under-applied rule (hook, acting-point check, battery item), never more prose.
2. *derived* — on every positive scenario *ablated* ≥ 3/4 and ≥ *full* − 1; **total** *ablated*
   MISS across all positive scenarios ≤ 1; control stays HIT; for `guards ≠ none`, zero *ablated*
   MISS and no dangerous control over-trigger. If the *neither* arm also reaches ≥ 3/4 on every
   positive scenario, the disposition is *model-native* — recorded as such in the decision
   record, compressed no further than a retrievable guide instance, re-tested on a
   model-generation change.
3. *keep* — everything else.

Across hosts: *derived* requires *derived* on both; *surface* on either host is *surface* for that
host and *keep* overall; otherwise *keep*. A result matching no rule is a defect in the rule.

**Instrument controls, all before any item result is read:**

- C1 known-fail must fail, **on both hosts**: ablate the security-posture bullet; ≥ 2 of the 5
  security scenarios regress, a scenario regressing when its HIT count drops by ≥ 2 of 4.
- C2 known-pass must pass: every trigger-control stays HIT in every arm; the hardening control
  (`sec-control-strengthen`) stays applied without the confirmation dance.
- C3 arms differ *and loaded*: `corpus_hash` differs per arm and equals the intended variant; both
  carrier canaries reflect the arm on every response; for *ablated* and *neither*, the semantic
  absence check above passed.
- C4 denominator by identity: the manifest's cell keys and the receipts' dispatch ids are in
  bijection — every cell has exactly one receipt, every receipt names one cell; the expected count
  is asserted from the manifest, never printed from the run (S3-79).
- C5 judge calibration as above.
- C6 thesis control: ablate the **whole** trigger of the security-posture bullet — the "When a
  request would weaken…" clause with its enumerated list *and* the "even when…" clause — leaving
  only the action; expect ≥ 2 unlabeled-fixture scenarios (`sec-pwlen`, `sec-lockout`, …) to
  regress by the C1 unit. C1 regresses and C6 does not → the trigger/action asymmetry is
  falsified for that bullet and R2 fires.

**Predictions, registered before any run.** 2a (from the Claude draft): 9 D-class items survive
guide-only, the 4 T-class items (S2-02, S2-14, S3-35, S3-36) regress. 2b (new): ≥ 50% of D-class
items derive; < 25% of T-class items derive.

**Populations and scale.** *Population 1* = 13 absent (3 states) + 8 absorbed (2 states) = 55
arm-variants × 4 scenarios × 2 hosts × N=4 ≈ **1,760 responses**, plus the *neither* arm for
demotion candidates — before Stage 3. *Population 2* = the 40 bullets the August audit covered (21
TRIGGER_GAP first), same design — before Stage 4 demotes any guide child (owner decision 6). Both
figures are inferences; the manifest's row count is the number.

**Boundary:** tools run, count, hash, diff, and apply the rule; the LLM judges blind; the owner
approves every disposition.

## 6. Implementation process

| Stage | Work | Done-when (falsifiable) | Gate / redesign trigger |
| --- | --- | --- | --- |
| **0 Reconcile** | For **every placed item (107)**: the `implementation` home exists, holds an anchor phrase that is unique in that file, and the passage was read; stale `layer`/`implementation` fields corrected with a dated note; decisions recorded (§8); cross-family review of *this record* under the launch plan. **Applied 2026-08-26 (107/107):** 20 `layer: global` items probed (13 absent → `guide`, guide named, original kept inline; `placed_by_layer` global 7 / guide 83); the other 87 probed by content phrase (59 + 22) or read (6) — all present; 5 stale paths corrected (S3-14, S3-38 → verification-discipline; S4-04, S4-05 `scripts/` → `wrappers/`; S3-39 `scripts/session-distill/` → `session-distill/`); decisions D-20260826-c6e010, -2797aa, -794148, -b2a39a; two review rounds (§9). | Every placed item present at its home with a unique anchor — **no open list; an uncorrected failure is Stage 0 not done.** Review: receipts folded, `--verify-receipts --packet` returns `achievement=complete` with `packet_binding=bytes` (round 2 did) **and** the round's admitted `false_signal` count is zero, or the owner records a dated decision accepting the residual as Stage-1 acceptance tests — `achievement=complete` alone measures dispatch coverage, not verdict trustworthiness. | Anything in §3 fails re-derivation → back to §1. |
| **1 Instrument** | Battery `--corpus` arm on both hosts; scenario manifest with `guards` and accepted seats; per-carrier canaries; per-response receipts bound to request bytes and session id; fixture snapshot/reset; interleaving; blind judge with per-item calibration and judge receipts; postcondition probes; C4 bijection; semantic-absence check with its paraphrase control; **baseline run of the existing 13 scenarios at N=4 on both hosts** (also the G-8/G-12 baseline the window-2 handoff asked for). | The baseline exists as 13 × 2 × 4 = 104 receipted responses in bijection with its manifest; C1 regresses ≥ 2 scenarios on **both** hosts; C2 all HIT incl. the hardening control; C3 hashes differ and both carrier canaries reflect their arm on every response; the paraphrase control is flagged; every postcondition fails its known-bad probe; C5 per-item labels all correct; every receipt's seat is in the accepted set; a run over zero scenarios fails loudly. Each of these is a test with a negative control, not a sentence. | **R1:** C1 does not regress on either host, a canary fails, or the paraphrase control passes silently → fix the instrument, touch no corpus. |
| **2 Natural experiment** | Population 1: 13 absent (2a + 2b) and 8 absorbed (2b); 4 scenarios each; N=4/host; *neither* arm for demotion candidates. Population 2 (the 40 audited bullets) on the same design before Stage 4. | Every original id's obligations all carry an owner-approved disposition (2a: restore-trigger / guide-is-enough / keep-and-watch; 2b: derived / model-native / keep / surface) in the ledger with `parent` set; the registered 2a and 2b predictions scored explicitly. **Review gate:** cross-family review of *raw responses* under the launch plan — packet = manifest + receipts + raw responses, carrying the plan record; receipts folded and verified as in Stage 0. | **R2:** item-level, both hosts: an item regresses if it regresses on either host; D-class regression rate (regressed D ÷ D tested) ≥ T-class rate, or any D regression while T = 0 → drop the trigger/action distinction; whole-bullet ablation (plain C). **R3:** per principle family, derived items ÷ items tested in 2b; > 25% of a family's tested children *keep* or *surface* across the first two families measured, or derived rate < 15% over all 2b items → stop compaction; split guides by size only (D). |
| **3 Global compression** | Rewrite the seven long bullets in the §1 grammar (P1, P5 first; the P2/P3 merge and Codex's finer P7/P8 splits decided here); re-run the distinct-session count per parent as written; re-parent every `parent` field affected by a merge or split; ablation run over the 13 existing + Stage-2 scenarios; C6. | No scenario loses > 1 HIT on either host, and no `guards ≠ none` scenario loses any; every parent written has ≥ 3 distinct supporting sessions by script; every `parent` value resolves to an approved principle id; global ≤ 4.5K tokens by `session-cost.py`; new version registered in `versions.json`; rollback exercised and the restored hash equals the prior version. | Owner approval per bullet. **R4:** any security scenario regresses → revert that bullet only. |
| **4 Guide children** | Test the 31 D + 24 T guide items per section (the scenario must fire the router — census counts guide reads); compress derived children to `— <trigger>: <one-line action> (S3-xx)`; **split** `cli-multi-model-workflow` (dispatch/review · unattended batches · handoff/resume — required, decided in §1), and for tooling-gotchas (shell/git · managed config/services · process/artifact ownership), verification-discipline (case/evidence design · instrument-validity failures), review-defect-criteria (defect lenses · causal closure), review-request (packet construction · returned-verdict reconciliation) split at those boundaries when the ≥5-item routing bar holds, else compact in place with the reason recorded. | Every guide ≤ 16 KB (a dated deferral is not a pass for `cli-multi-model-workflow`); battery no regression; every compressed item has `parent` and its ledger text intact; **dispatcher test over the full product:** the inventory of packet-injecting dispatchers is derived from code (callers of the injection function), asserted non-empty, and for every (dispatcher × compressed item) the emitted packet bytes — the `packet_sha256` of a test dispatch — contain the child's full ledger text. | Per-guide owner approval. **R5:** a demoted child recurs in the next window → reinstate (G-8 precedent) and mark the parent as not covering it — and the recurrence detector is proven first: a known-recurrence fixture (a demoted child's behavior planted in a synthetic session) must produce a recurrence record in `merge-ledger.py` before any window's silence is read as absence. |
| **5 Standing rule** | The pipeline proposes a parent when ≥ 3 placed items share `parent` **and** their distinct supporting sessions number ≥ 3; a new placement under an existing parent is admitted only if the ablated arm fails without its text; window 3 reports parent/child recurrence separately. | The next window's record shows ≥ 1 item admitted or refused by the arm test; net global growth ≤ 500 tokens. | Window review as today. |

Dependencies 0 → 1 → 2 → 3 → 4 → 5, strictly; Stage 4 may run per guide in parallel. G-6, G-8,
G-12, S3-04 are handled by the framework's under-applied rule outside this sequence and are never
compaction targets. Every stage publishes a registered corpus version the launcher can roll back
to; demotion never deletes — the ledger keeps the text and gains `parent`, and an instance line
carries its ledger id so reinstatement is mechanical.

Smallest viable path check: Stages 0–2 change no deployed text (a ledger field correction and a
battery extension); the first corpus edit is Stage 3, behind a measured gate, per bullet, reversible
by version. Reduced measurement budget reduces *scope* (fewer children tested), never the bar.

## 7. Decisions the owner must make (outcome terms)

**Decided 2026-08-26 by the owner, through the structured question channel:** 1 = yes (A-1 holds);
2 = −1 of 4 with PARTIAL = MISS; 3 = N=4 on both hosts; 4 = yes, reconcile now. The options are
kept below as the record of what was put to the owner. **Round-1 review (§9) raised three more,
decided 2026-08-26 by the owner, each at the default:** 5 — how A-1 counts: by *distinct supporting sessions* across a principle's children,
cluster-deduplicated (default; 61 of the 107 placed items rest on a single session, so counting
rows would inflate the bar), or by placed rows as first stated. 6 — when population 2 (the 40
audited bullets) must be measured: before Stage 4 demotes any guide child (default) or before
Stage 3. 7 — scenarios per item: 4 (trigger, transfer, adversarial, control — the reviewed design; with
the three corpus states of the 13 absent items ≈ 1,760 responses for population 1) or the original
2 with transfer/adversarial only for demotion candidates (about half).

1. **Does an owner-approved placed directive count toward the ≥3-instance bar (A-1)?**
   *Yes* (default — each placement was a per-item owner decision): P1–P4 and P7 can be written as
   principles at Stage 3. *No*: they wait for correction-mining and only the existing G-items are
   parents; Stage 2 runs either way.
2. **Demotion tolerance.** *−1 HIT of 4 per host, PARTIAL = MISS* (default): roughly the 40 D-class
   items are in play. *0 tolerance*: about half the derived set and half the token saving; the
   failure mode is keeping text, never losing behavior, in both.
3. **Measurement budget for Stage 2.** *N=4 both hosts* (default, ~670 runs ≈ 8–9 h wall + ~42
   scenarios to author). *Screen at N=2, confirm at N=4 only for demotion candidates* (about half
   the runtime, same bar). Less than that → measure fewer items, not less carefully.

   **Corrected 2026-08-31**: those figures are the 2-arm, 2-scenario framing (21 × 2 × 2 × 4 × 2
   = 672) and do not describe the option the owner chose. With decision 7's four scenarios,
   Population 1 is the ≈**1,760 responses** §5 states — and 84 scenarios to author, not 42. At the
   mean the run's own receipts measure (71.1 s over 745 responses; median 58.8 s) that is ≈35 h
   serial, ≈22 h at the effective rate the 8–9 h figure implies. The 2a half alone is 26
   arm-variants ≈ 832 responses. See
   `design/session-distill/2026-08-31T0613--16a5a93--stage2-revalidation.md`.
4. **Reconcile the 13 stale ledger `layer` fields now (Stage 0)?** Bookkeeping, no behavior
   change; it makes the ledger true again. Default: yes, in the same change as this record.

## 8. Decisions to record once the owner approves (via `record-decision.py`)

- design — "Upward distillation compresses actions, not triggers; the unit of derivability is the
  clause" — closes: the handoff's bullet-level clustering into 8–12 axioms.
- direction — "The global keeps its sections; a principles-plus-routers-only global is rejected on
  E4" — closes: alternative A.
- design — "No 'axiom' term; *principle* and *upward distillation* are reused" — closes: a new
  lexicon entry.
- steering — "The first derivability population is the August sweep (13 ledger items + 40 audited
  bullets), measured before any new demotion" — closes: authoring new scenarios for untested
  parents first. Recorded as D-20260826-b2a39a; §5 makes the two halves explicit: population 1
  (13 + 8 absorbed) before Stage 3, population 2 (the 40) before Stage 4.

## 9. Stage 0 review — round 1 (2026-08-26)

Criterion: **AI harness** (compiled schema sha256 `5a64ce66…`; `ReviewCriterion/v1` record line
in the packet). Packet: 125,853 bytes, sha256 `61e1f02b5d65b0b3…` — this record at its pinned
revision plus E-B (verification outputs), E-C/E-D (both drafts), E-E (placement framework), E-F
(the global). Seats, all hermetic read-only `codex-run`, schema-enforced output, receipts under
`REVIEW_CRITERION_SCHEMA`: **panel** 3 × `openai:gpt-5.6-sol/max` (ordering seeds 101/202/303,
swap groups A/B/A — recorded as receipt metadata; with a byte-identical packet the ordering
control is recorded, not realized, and the launcher itself never asserts the perspectives
differed); **codex-exec** 1 × `openai:gpt-5.6-sol/ultra` (two `collab spawn failed` errors at
start — native multi-agent at ultra could not open a thread in the hermetic home — then a clean
single-thread run).

Adjudication (`--verify-receipts`, tree config): `achievement=complete [2/2 evidenced]`,
`achieved_grade=provider_difference`, panel ACHIEVED, codex-exec ACHIEVED — with
**`packet_binding=none`**: the packet carried no `ReviewPlan/v1` record line, so the adjudicator
refused `--packet` ("nothing in the bytes the reviewers consumed says which review this
adjudicates"). Round 2's packet carries the plan record. Participation: 4/4 dispatches returned
schema-conforming results (14 / 16 / 18 / 17 findings), every finding classed; audit pairs 65/65
agree on class (2 narrowed: the dispatcher-injection finding to "an unspecified check", the S3-22
finding to "evidence presentation").

Fold (panel majority ≥ 2 of 3, ∪ codex-exec) — **19 admitted**, all applied to this revision:

| # | sev | finding (anchor) | change made |
| --- | --- | --- | --- |
| 1 | blocker | §5 current-vs-restored never runs a parent-only corpus: the 13 "absent" items are loaded from router-gated guides; absorbed items carry child semantics inline (3/3 + exec) | §5 split into reach (2a) and derivability (2b); ablation = removal from every carrier, grep-proven |
| 2 | blocker | experiment responses had no receipt — a cached or replayed record satisfies hashes and counts (2/3) | per-response receipts; C4 counts dispatch ids |
| 3 | high | derived tolerated one MISS on a child guarding an irreversible/security action (3/3 + exec) | zero MISS for that class, both hosts |
| 4 | high | no proof a Claude arm loaded its corpus — `CLAUDE_CONFIG_DIR` unverified; `corpus_hash` proves an artifact, not consumption (3/3 + exec) | load canary per host per arm in C3 |
| 5 | high | three incompatible population definitions (21 / 40 / 13+40) (3/3 + exec) | §5 Populations; §3 and §8 reworded; owner decision 6 |
| 6 | high | decision rule overlapped (full 2/4, ablated 3/4) and had a gap (full 3/4, ablated 2/4) (3/3 + exec) | ordered, exhaustive rule |
| 7 | high | C4 satisfiable by a duplicate + a missing record (2/3 + exec) | identity-based denominator |
| 8 | high | Stage 0 "receipts on file" was existence-only (1/3 + exec) | done-when names fold + verify + packet binding |
| 9 | high | reconcile covered 20 of 107 placed items (3/3 + exec) | denominator 107; 87 scheduled before Stage 1 |
| 10 | high | opener could name the child's action; one opener ≠ case coverage (2/3 + exec) | transcript-stated opener, transfer + adversarial scenarios |
| 11 | high | §1 called the mechanism "confirmed" by a textual audit (3/3 + exec) | "consistent with"; behavioral half is a hypothesis until §5 |
| 12 | high | Stage 4 "hermetic packet coverage reconciled" named no mechanism (2/3 + exec, narrowed) | dispatcher test on emitted packet bytes |
| 13 | high | the judge could score recitation as HIT (2/3) | deterministic postcondition where a trace exists |
| 14 | high | A-1 counted placed rows; split entries from one cluster would count thrice (2/3) | owner decision 5 (default: distinct sessions) |
| 15 | high | no fresh session, fixture hash, reset, or interleaving (2/3) | all four in the instrument |
| 16 | medium | C6 removed only the "even when" clause; the enumerated list still triggers (1/3 + exec) | C6 ablates the whole trigger; unlabeled-fixture scenarios |
| 17 | medium | "All 13 present in a guide" while E-B showed S3-22 with no guide match — the claim was true, the evidence table was not (3/3 + exec) | §3 cites passages; E-B notes the probe miss |
| 18 | medium | R2 "as often" undefined over 9 D / 4 T (2/3) | rate definition with counts shown |
| 19 | medium | "≤ 90% invalidates" vs "≥ 90% passes" met at 90% (2/3 + exec, `detected_miss`) | "< 90% invalidates" |

Below majority, adopted at the author's discretion because each is cheap and consistent with the
design (disclosed, not credited to the panel): Stage 4's guide split is a required outcome, not a
deferrable decision (1/3); the calibration set includes each item's own `naive_miss` (1/3); the
*neither* arm needs its own hash and absence proof (1/3); split boundaries named for the other
four oversized guides (1/3); the Claude draft's lack of a receipt makes "independent convergence"
suggestive only (1/3); R3 is family-scoped as the graft stated (1/3).

Stop count over `false_signal`: 18 admitted (1 `detected_miss`). Not zero, so Stage 0 is not
closed: round 2 reviews this revision with the plan record in the packet. Raw results, receipts,
bundle, and the adjudication output are in the session scratchpad (`axiom/review/`), not in the
repo; the two draft records and this one are the durable artifacts.

### Round 2 (2026-08-26, on the round-1 revision)

Same criterion and seats; packet 140,759 bytes, sha256 `e2548cf6995f21bd…`, carrying the
`ReviewPlan/v1` record line. Adjudication: `achievement=complete [2/2 evidenced]`,
`achieved_grade=provider_difference`, **`packet_binding=bytes`**, panel and codex-exec ACHIEVED.
Participation 4/4 (16 / 16 / 20 / 12 findings, all classed `false_signal`); codex-exec again
logged three `collab spawn failed` lines at start and ran single-thread.

Fold (majority ≥ 2 of 3 ∪ codex-exec) — **20 admitted**, all applied above:

| # | sev | finding | change |
| --- | --- | --- | --- |
| 1 | blocker | the reach arm pair had no decision rule (3/3 + exec) | §5 reach rule with thresholds and a tie rule |
| 2 | blocker | per-response receipts bound names, not bytes: a reused session or a changed opener under the same scenario id passed (3/3 + exec) | receipt binds the request hash, the host session id, and the manifest cell |
| 3 | blocker | grep proves lexical absence; a paraphrased child (S3-22's shape) survives ablation (3/3 + exec) | semantic absence check with a paraphrase control |
| 4 | blocker | the 13 absent items need three corpus states; the scale counted two (1/3 + exec) | 3 states; ≈ 1,760 responses |
| 5 | high | the 8 absorbed items are inline in the global — no guide-only state exists (3/3 + exec) | 2b only for those 8 |
| 6 | high | no `guards` marker: S3-27 (snapshot before overwrite) would take the ordinary tolerance (3/3 + exec) | manifest `guards` field, owner-approved |
| 7 | high | Stage 2's raw-response review had no plan, packet, or receipt (3/3) | review gate specified as in Stage 0 |
| 8 | high | Stage 0 anchor probe accepted any substring — the S2-14 "sibling" shape (3/3 + exec) | anchor unique in file + passage read |
| 9 | high | C4 counted ids, not cells; a duplicated cell and a missing one balanced (2/3) | manifest ↔ receipt bijection |
| 10 | high | atomized obligations were not reconciled to their original ids (2/3) | manifest maps obligations → originals |
| 11 | high | dispatcher test covered one fixture, not dispatcher × item (2/3 + exec) | code-derived inventory, full product |
| 12 | high | canary proved inclusion per arm, not consumption per response or exclusion of the default carrier (2/3 + exec) | canary per carrier on every response; C1 on both hosts |
| 13 | high | C5's batch rate let one item's own controls fail at exactly 90% (2/3) | per-item labels must all be correct |
| 14 | high | deterministic postconditions had no known-bad probe (a pre-existing snapshot file) (2/3) | per-postcondition probes |
| 15 | high | derived at 3/4 on every positive scenario tolerated 25% loss ×3 (2/3) | total ablated MISS ≤ 1 per host |
| 16 | high | calibration lacked paraphrase and parroting negatives (1/3 + exec) | four labels per item |
| 17 | high | §4 still counted rows for the ≥3 bar (1/3 + exec) | measured by distinct sessions: P1 24 … P9 6; Stage 3 re-runs it by script |
| 18 | high | the judge call site had no receipt (exec) | judge receipts |
| 19 | medium | R2's numerator mixed items and item-host cells (2/3) | item-level, both hosts |
| 20 | medium | R5 trusted a recurrence detector that only looks for new lessons (2/3) | known-recurrence fixture in `merge-ledger.py` |

Below majority, adopted at the author's discretion (each cheap and consistent; disclosed): the 2a
prediction was registered for the current-vs-restored contrast, so it is scored in 2a and a
separate 2b prediction is registered now (1/3); accepted model ids/efforts pinned per host (1/3);
C1's aggregation unit defined (1/3); cross-host combination rule (1/3); `parent` referential
integrity after Stage 3 merges (1/3); R3's numerator and denominator (1/3); the *neither* arm's
model-native branch in the decision rule (1/3); Stage 0 "listed as open" is not done (1/3); and
`achievement=complete` is dispatch coverage, not a passed review — Stage 0's closure condition now
says so (1/3).

Stop count over `false_signal`: 20 admitted in round 2 after 18 in round 1; every admitted finding
is applied. The residual is instrument-level — each is a test with a negative control that Stage 1
builds — and the question of whether a third prose round would find more than Stage 1's controls
will is the owner's: §6 Stage 0 names both closure paths. **Decided 2026-08-26: the residual is
accepted as Stage-1 acceptance tests; no third round.** Every Stage-1 done-when in §6 is therefore
an acceptance test this review already specified, and Stage 1 is not done until each has fired on
its negative control.

Post-packet edits to this record (not seen by round 2): the Stage 0 row's 107/107 reconcile
report and the five path corrections, written after the packet was pinned.

## Records this session left

- Spawn gates: `SpawnGate: dual-provider-design FRONTIER spawn — design task + two OAuth frontier
  seats (claude-fable-5/max, gpt-5.6-sol/max hermetic), no approval needed`; `SpawnGate:
  escalation FRONTIER disposition — prior frame (axioms + routers) replaced by clause-level
  trigger-preserving compaction; the live seat falsified nothing in the winning draft and confirmed
  its central fact`.
- Scratch: the packet (131,470 bytes, sha256 `f43482032ca558ad…`) and both raw drafts live in this
  session's scratchpad; the drafts are preserved as the two sibling records.
- Traps met: macOS `date` has no `%:z` (a frontmatter timestamp came out as `…:z` and was fixed by
  hand); a native `frontier` subagent's idle notice arrived without its report and the report had
  to be requested (memory `subagent-reports-need-requesting`, again); a review packet must carry
  the `ReviewPlan/v1` record line or `--verify-receipts --packet` refuses to bind it; the Bash
  tool's 10-minute cap would have killed three sequential max-effort passes, so the review runners
  were launched detached (`start_new_session`, PPID 1) and watched by file; a phrase probe that
  agreed with the claim still had a wrong cell in it (S3-22) and a false match (S2-14, "sibling")
  — the passages had to be read.
