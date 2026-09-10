---
guide_id: review-defect-criteria
language: en
status: active
use_when:
  - declaring what counts as a defect before dispatching any review
  - choosing or writing the defect criterion for a system type × work goal
  - a review loop plateaus, diverges, or its "material 0" stop never arrives
  - a finding's class is contested at the boundary, or two lenses class it differently
core_rules:
  - choose and declare the criterion before the review starts — undeclared, every reviewer substitutes its own
  - the severity ladder answers how bad; the criterion answers whether it is a defect, of which class, and what "zero" is counted over
  - a criterion with an empty cell is a hunch, not a criterion — do not start the review
  - paste the goldens into the packet verbatim; a definition alone does not classify consistently at the boundary
  - put the class enum on the accepting channel where one exists; on prose routes, run the fold procedure
  - a mixed packet is split — never run two observers in one trajectory
verification_focus:
  - every dispatched packet names its criterion and carries its goldens
  - each round audits reported class against post-measurement class; repeated disagreement mints the next golden
  - the stop condition is evaluated over the stop-relevant class only, never the whole finding count
---

# Review Defect Criteria

A defect criterion is chosen, not assumed. This guide is a scoped extension of
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/review-request.md`: before that guide's
request composition starts, this one decides what the review is hunting. The
evidence: one codebase, two stop criteria, opposite trajectories.

| Rounds | Criterion | Trajectory |
|---|---|---|
| early | material = contract violation **or** unprotected contract sentence, small frozen surface | 10 → 4 → 1 → 0 |
| late | same, scoped to client-observable behavior | 17 → 19 → 21 → 23 → 19 — **plateau** |
| final | split classes: behavioral_defect / coverage_gap / doc_gap; stop = behavioral 0 | behavioral 10 → 5 — falling again |

The plateau was the criterion, not the code: counting "a contract sentence no test
protects" as a defect means every fix adds contract rows, each a potential defect
next round — a self-refilling criterion cannot reach zero while its surface grows.
Yet that same criterion is exactly right for a library, where an unprotected promise
is a first-class defect. Neither is wrong; starting without choosing is.

The **severity ladder** (in `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/coding-staged-workflow.md`)
answers *how bad* a finding is. The **criterion** answers *whether* it is a defect at
all, of which class, and what "zero" is counted over. The plateau happened entirely
inside "material" — no severity adjustment could have ended it. Ordering: system type
+ goal → defect criterion → classification → defect? → severity → materiality → stop.

## The criterion schema

One entry carries all of these. An empty cell makes it a hunch, not a criterion — do
not start the review on it.

| Field | Meaning |
|---|---|
| observer | whose eyes judge — client, caller, operator, a model reading the output |
| defect | what the observer must experience |
| classes | the enum, exactly ONE class stop-relevant; the others are relief valves that keep the stop class honest |
| evidence | what one finding must present |
| non-defects | defect-lookalikes excluded by this criterion — named explicitly |
| stop condition | what "0" means, counted over the stop class, and WHY it is reachable — how a growing surface is pinned |
| misclassification cost | which error is expensive — the direction to tell the reviewer to lean |
| goldens | ≥2 positive, ≥2 negative, ≥1 boundary; each with why, date, and provenance: `measured` (dated incident) or `constructed` (authored to pin a boundary) |

## The catalog

Four system types. A starting set, not a census.

### Web service / API surface (contract compliance)

- **Observer**: the HTTP client.
- **Defect**: a client today receives a response that differs from the contract — status code, envelope, stream terminal frames, the model actually run, isolation, resource caps.
- **Classes**: `behavioral_defect` (stop-relevant) · `coverage_gap` · `doc_gap`.
- **Evidence**: the concrete request and observed vs promised response.
- **Non-defects**: internal lifecycle (unless a request sequence shows two different responses), absence of a test, documentation wording.
- **Stop**: behavioral 0 — reachable: the code surface is finite and shrinks monotonically unless a fix creates a new behavioral defect.
- **Misclassification cost**: false negatives (a client actually breaks); but inflating coverage gaps into defects destroys the stop condition — audit category creep separately.
- **Goldens** (all `measured`, 2026-08-13–15):
  - **+** `GET` on a nonexistent path returned 405, not 404 — an existing-method complaint attached to a path that does not exist.
  - **+** a streaming endpoint's terminal delta carried only `output_tokens`, so cache/input token counts never reach a streaming client — non-streaming was correct, which is why nobody saw it.
  - **−** "no test catches a one-line flip of this default": today's behavior is correct — `coverage_gap` here, a defect only under the library criterion.
  - **−** child-process kill grace period — out of scope until a request sequence shows a client-visible difference; pins the observer to the client.
  - **±** rejecting a documented-as-valid boundary value (compression 100, docs say "below 100 requires jpeg/webp") — the documentation is what makes it a defect; without that sentence it is taste.

### Library / SDK / contract-first system

- **Observer**: the caller **and** the future maintainer.
- **Defect**: a promise violated today, or a promise unprotected — a one-line change breaks it and nothing catches it. The API criterion's `coverage_gap` is first-class here.
- **Classes**: `contract_defect` (stop-relevant) · `style_note` · `internal_change`.
- **Evidence**: for a violation, as above; for an unprotected promise, the promise sentence + the one-line change that breaks it + the absence of any catching test.
- **Non-defects**: style, internal structure.
- **Stop**: caution — this criterion self-refills while the contract grows. Declare "0" only over a surface whose growth has stopped; on a growing surface, narrow the stop to "every promise this change added is protected."
- **Misclassification cost**: balanced — miss an unprotected promise and the next refactor breaks it silently; over-report and the loop never ends.
- **Goldens**:
  - **+** a streaming-image event test matched only `.completed`, so an edit stream misnamed `image_generation.completed` still passed — mutation survival showed the promise unprotected. (`measured`, 2026-08-13–15)
  - **+** the contract promised "storage serves a large image at least once"; the code evicted it on the next request — resolved by fixing the **contract**: the disagreement is the defect, whichever side moves. (`measured`, 2026-08-13–15)
  - **−** renaming an internal helper no document promises — the observer holds the contract; undocumented internals carry no promise. (`measured`, 2026-08-13–15)
  - **−** a caller breaking on undocumented iteration order — no promise existed; the rename boundary pinned from the caller's side. (`constructed`, 2026-08-19)
  - **±** an inventory-listed test turns out vacuous — asserts nothing about its promise. "A test exists" is a claim about names until the assertion is read; hand the reviewer "check the assertion, not the name." (`measured`, 2026-08-13–15)

### AI workbench / harness (agent orchestration, review loops, verification pipelines)

- **Observer**: the operator, and any model consuming the harness's output.
- **Defect**: **a false signal that looks true** — a wrong PASS, a vacuous test, a silent fallback, a packet missing the call site, a wrong denominator. Being wrong is not the defect; being wrong while *looking right* is. Second form: a run claimed without provable dispatch — no receipt.
- **Classes**: `false_signal` (stop-relevant) · `detected_miss`. An unproven dispatch — a run or PASS claimed with no receipt — is classed `false_signal`, not given its own relief valve: a signal that cannot be shown true is counted false, or a round could declare completion while every dispatch stayed unproven.
- **Evidence**: the input on which the instrument gave a false verdict, plus the known correct answer. The standard probe: run the instrument against an input whose answer is known to be the opposite.
- **Non-defects**: one output's style; a false positive the harness itself **detected** — a caught error is the harness working.
- **Stop**: every PASS emitted this run survives a known-opposite check and evidences its own dispatch. The unit is "this run's signals are trustworthy," not a standing zero.
- **Misclassification cost**: false passes dominate. An instrument bug reporting failure dies in minutes because someone looks; one reporting success survives — a selection effect.
- **Goldens**:
  - **+** a shell test runner received one nonexistent path (zsh does not word-split an unquoted variable), so every run exited 1 and every mutation reported KILLED — a green instrument that never ran its subject. (`measured`, 2026-08-13–15)
  - **+** a test-inventory grep matched only `^test('...'` and missed every parameterized name; three reviewers judged a populated file empty — nothing tied the inventory's denominator to the source's own count. (`measured`, 2026-08-13–15)
  - **+** a negative control kept passing after a faithful revert of the fix it was written against — a guard satisfied by an absence, a false PASS about the gate itself; found only by re-running reverts. (`measured`, 2026-08)
  - **+** a review round returned "clean" with no receipt evidencing that the declared packet was dispatched on the exact seat — `false_signal` although nothing observed was wrong: what the stop refuses is absence of proof of dispatch, not proof of falsity. (`constructed`, 2026-08-19, pinned after a classification dispute at exactly this boundary)
  - **−** one reviewer over-classed an item as material; another lens plus measurement filtered it — the harness caught it, so it worked: `detected_miss`, not a defect. (`measured`, 2026-08-13–15)
  - **−** five review rounds returned 8 → 9 → 10 → 5 → 12 findings, refusing to converge — and every count was true. A truthful unpleasant signal is not a false signal; the defect lived in the undeclared criterion. (`measured`, 2026-08-16–17)
  - **±** a surviving mutation proved equivalent — the platform already normalized what the mutated guard checked. Neither a harness defect nor a test gap; but a harness that auto-reads "survived = gap" has a defect in that rule. (`measured`, 2026-08-13–15)

### Decision ontology (an ontology a model decides from)

- **Observer**: a model or agent deciding from the ontology alone.
- **Defect**: a representation that produces a wrong decision or blocks a right one: overlapping concept boundaries, a missing distinction the decision needs, an instance contradicting reality, a wrong relation direction or cardinality, a name implying what the definition does not say.
- **Classes**: `decision_defect` (stop-relevant) · `representation_note` · `out_of_scope_gap`.
- **Evidence**: a **decision scenario** — "answered from the ontology alone, this question yields X; reality is Y" — with the question, the path taken, and the ground truth.
- **Non-defects**: representation format, completeness as such, a question the model would get wrong without the ontology too.
- **Stop**: zero wrong decisions over the agreed scenario set. The set is the scope — fix it first, or this criterion self-refills like the library one.
- **Misclassification cost**: situational — feeding a hard gate makes false negatives expensive; exploratory aid makes false positives expensive. Filling this cell is mandatory at declaration.
- **Goldens** (all `constructed`, 2026-08-19, authored to pin boundaries the source loop's decision-scenario framing left open):
  - **+** `Customer` and `Account` both define "the paying party"; a refund-routing question resolves through both paths — overlap is a decision defect even when each definition is individually correct.
  - **+** `Order —hasOne→ Payment` while split payments exist — cardinality is a claim, and a false claim misleads the deciding model.
  - **−** a verbose concept description — no decision changes; form is outside this observer's sight.
  - **−** a domain absent that no scenario in the agreed set needs — completeness is scoped by the set, not the world.
  - **±** the distinction exists but the model cannot find it (name or link missing) — with the observer fixed as "a model seeing only the ontology," unreachable is a representation defect, not a search defect. The observer clause decides the class.

## Before any review

1. Write one sentence: the system type and this work's goal. ("API surface — make the responses clients receive today match the contract." / "Harness — make this run's PASS signals trustworthy.")
2. Pick a criterion from the catalog, or fill the schema fresh. A cell you cannot fill means the review does not start.
3. Paste the goldens into the packet verbatim. Never the definition alone.
4. Declare the stop condition and why it is reachable — or how the scope was pinned to make it so.
5. Put the classification on the accepting channel (next section).
6. Audit every round: reported class vs the class confirmed after measurement. A repeated disagreement is the next golden.

## Enforcing the enum, by channel

Ranked by how much the channel refuses for you:

1. **A route with a submit schema**: classification is a required enum field. The
   measured precedent is anchors — 2,466 of 2,466 findings carried one, because the
   schema refuses output without it. Where this channel exists, use it.
2. **Prose-packet routes** (the shipped deep-review methods): the packet header
   declares `Criterion: <name>` with the goldens pasted verbatim, and the dispatching
   agent runs this fold procedure on what comes back:
   1. For each returned finding row, look up its class against the declared enum.
   2. A row carrying a class from the enum enters the findings ledger under that class.
   3. A row with no class, or a class outside the enum, is **not admitted**: send it
      back once for classification, or record it as refused with the reason. Never
      admit it unclassified, and never guess its class for it.
   4. Count the stop condition over the stop-relevant class only.
   5. Record the audit pair (reported class, confirmed class) for procedure step 6.

   Stated honestly: on a prose route this is steering, not control — the fold is
   performed by an agent following this guide, and nothing structural refuses a
   class-less row for it. That is the known weaker result of a request-only rule.
3. **The launcher's criterion discipline** (agent-launch): a preset declaring
   `criterion = true` renders one core-owned discipline clause into every review
   method row — the criterion's content never enters the per-launch config; it rides
   the packet as a `ReviewCriterion/v1:` record line beside the prose above.
   `--compile-criterion` refuses a document failing the schema's decidable subset and
   emits the canonical findings schema; where the host CLI's structured-output flag
   probes present (`--check-schema-flag`), the dispatch passes that schema, and
   receipt emission under `REVIEW_CRITERION_SCHEMA` refuses a class-less or
   out-of-enum result — no receipt, and an unproven dispatch is already in the stop
   class. `--verify-receipts --packet` recompiles the packet's record and refuses a
   receipt whose schema digest was compiled from any other criterion. A route whose
   flag probes absent runs rank 2 and is disclosed as prose discipline — never
   credited as schema-enforced.

## Golden lifecycle

- **Admission**: only a golden that decides a boundary the definition leaves open,
  evidenced by a recorded classification disagreement or an audited misclassification;
  provenance labeled `measured` or `constructed`, each with its why and date.
- **Overturn**: only by a measured counterexample. Correct the golden in place — this
  guide describes the present — plus a dated decision record, in whatever channel the
  repo keeps decisions, naming the closed golden and the counterexample. Silent
  deletion is forbidden: a wrong golden makes reviewers systematically wrong, and an
  untracked fix hides that it ever did.

## Declaring, switching, and mixed packets

- Every dispatched packet names its criterion. A harness round declares `AI harness`;
  a round whose system type has no catalog entry declares a **task-local criterion**,
  written in the packet itself, conforming to the schema above and labeled task-local
  — repeated use is what earns a catalog entry.
- A mixed packet is split into one packet per criterion. Two observers in one
  trajectory produce findings no single stop condition can count.
- When a criterion changes mid-loop: re-classify only the findings still open; rounds
  already recorded are dated history. Never splice pre- and post-switch counts into
  one series — they count different things.

## Evidence base

Derived from a 39-round adversarial review loop (3 lenses × a frontier reviewer) on a
peer OAuth CLI-API adapter, 2026-08-13–15: the same codebase plateaued at
17→19→21→23→19 findings under a self-refilling criterion and resumed falling
(behavioral 10→5) the round the classes were split and the stop counted over
`behavioral_defect` alone. The boundary evidence is from the same loop: a packet
instruction saying "do not inflate coverage gaps" still left two lenses classing one
finding `doc_gap` and `behavioral_defect`, both defensibly — one golden would have
decided it. The non-convergence golden (8→9→10→5→12, every count true) is this
environment's own launcher-review loop, 2026-08-16–17, run under an undeclared
"material" criterion; the two series are two populations under two criteria and are
cited separately for exactly the reason the migration section gives. Re-derive when
the review routes or the bound models change.
