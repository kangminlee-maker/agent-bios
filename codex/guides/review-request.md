---
guide_id: review-request
language: en
status: active
use_when:
  - writing a review request, packet, or reviewer role for any model
  - deciding what evidence bar and verdict shape to demand from a reviewer
  - triaging why a review returned noise, nothing, or a clean bill of health
  - choosing which perspectives to run and whether to pay for deliberation
core_rules:
  - demand a failure path, not a gap — "X is unverified" dies, "X breaks when Y" survives
  - require every finding to anchor to file:line, and every empty result to cite what was checked
  - say what the target is and is not — stage, boundary, and what absence means
  - bundle the consumer the target depends on, or its most load-bearing claim is unreviewable
  - forbid carry-forward findings — anything phrased "watch" or "document later" is not a finding
  - read participation before believing a verdict; a crashed harness reports zero findings
  - treat a finding's causal attribution as the reviewer's weakest claim, not its severity
verification_focus:
  - a zero-findings verdict is confirmed against participation, not accepted at face value
  - findings are checked for a stated failure path before they are acted on
  - an empty result is trusted only when it cites the evidence it checked
---

# Review Request Guide

This guide is a scoped extension of the global Coding Guidelines. Use it when
composing what you ask a reviewer for — the request, the evidence bar, the
verdict shape. It does not cover when to review, how deep, or what counts as
material — that last question splits in two: the severity ladder and review loop in
`${CODEX_HOME:-$HOME/.codex}/guides/coding-staged-workflow.md` own *how bad*,
while whether something is a defect at all, of which class, and what "zero" is
counted over is the defect criterion, owned by
`${CODEX_HOME:-$HOME/.codex}/guides/review-defect-criteria.md`. Nor
which reviewer kind to route to — the convergence heuristic in
`${CODEX_HOME:-$HOME/.codex}/guides/verification-discipline.md` owns that. Phrasing a prompt for a specific model
family is out of scope here; where that guidance ships, the rule that needs it
points at it.

The rules below are derived from ~330 real multi-lens review sessions run in
this environment. That corpus is one model family in practice, so nothing here
is a per-model claim; these are the failures that persist regardless of who
reviews. Every rule names the evidence behind it, because a review guide that
asserts without evidence would fail its own bar.

## Declare the criterion

Before composing anything else, name the defect criterion the review runs under —
the per-system-type definition of what a defect is, its class enum, and what "zero"
is counted over. `${CODEX_HOME:-$HOME/.codex}/guides/review-defect-criteria.md`
owns choosing it; this guide assumes one is declared. Put `Criterion: <name>` at the
top of the packet with that criterion's goldens pasted verbatim — a definition
without goldens does not classify consistently at the boundary, and an undeclared
criterion means every reviewer substitutes its own.

## Demand a failure path, not a gap

The dominant reviewer failure is not hallucination. Across 372 rejected
findings, "asserted a gap without demonstrating a failure" accounts for the
largest share (~34%), while misreading correct code accounts for **one** case
and speculation for seven. Reviewers do not invent defects — they report
unverified things and call them findings.

The corpus separates these cleanly by how the finding is framed:

| Framed as | Dropped |
|---|---|
| `evidence_gap` — "not covered / not verified" | 94% (n=143) |
| `needs_evidence` | 93% (n=118) |
| `document_only` | 92% (n=144) |
| `root_cause` — a defect with a cause | 3% (n=878) |
| `fix_now` | 3% (n=1026) |

So say it in the request: **state the input, the branch, and the observable
wrong behavior. "X is not verified" is not a finding; "X breaks when Y" is.**
A reviewer that cannot show the failure should say so as a boundary note, not
file it against the target.

## Set a severity floor, because low never survives

Severity is the single most decisive predictor in the corpus, and it is close to
deterministic:

| Severity | Reaches the deliverable |
|---|---|
| `blocker` (n=16) | 100% |
| `high` (n=366) | 96% |
| `medium` (n=1338) | 92% |
| `info` (n=44) | 5% |
| `low` (n=226) | **0%** |

Not one low-severity finding out of 226 survived. The tokens that produced them
were spent for nothing, twice — once writing, once reading.

So state the floor in the request: **do not report a finding you would rate low.
It will be discarded; spend the effort on a medium-or-above finding instead.**
This is not a quality bar on the reviewer, it is a cost decision — the corpus
shows the discard happens regardless, so the only question is whether you pay to
generate it first. (What counts as each severity is the ladder in
`${CODEX_HOME:-$HOME/.codex}/guides/coding-staged-workflow.md`, not
this guide's.)

## Forbid carry-forward findings

Every finding the corpus classified as deferrable died: `planned_later` 100%
(n=104), `watch` 100% (n=36), `defer_watch` 97% (n=71), `out_of_scope` 92%
(n=26). Not one survived to the deliverable.

Ask only for what must change in this target now. Anything the reviewer would
phrase as "carry forward", "watch", or "document later" costs tokens to produce,
tokens to read, and is discarded — say that up front so it is never written.

## Stop the loop on provenance, not on count

A review loop's finding count says nothing about whether to run another round. What decides
it is where the findings came from: a finding that a previous round's **fix** created is a
different animal from one that was always there.

Classify each finding three ways, not two: **caused** by the last fix, **surfaced** by it (the
fix made someone look there, but the defect reproduces on a path the fix never touched), or
pre-existing. The split is a revert rule, not a taxonomy: reverting removes a caused defect and merely
hides a surfaced one. Collapsing them is how someone reverts a design change, counts the
findings cleared, and leaves the surfaced ones live. The test that separates them is whether
the defect reproduces on a path the fix never touched. Then read the caused share across rounds. A rising share means the fixes are generating the work, which is the
signature of an undecided design question being patched at its consequences. Stop reviewing
and take the design as its own task.

The mechanism is the one Concept Economy already names: a fix that adds a lasting concept —
a field, a member, a contract, a failure mode, a new error status — is a design change no
matter how small the diff, and the next round finds its consequences. A fix that *removes*
a concept is the healthy shape.

When you stop, split the tree rather than leaving a half-designed mechanism in place: keep
the pure defect fixes, revert the design change, and record the gap where it will be read.

Source: an external 13-round campaign on a local API adapter, where rounds 12 and 13 ran 3-of-6
and 6-of-10 caused-by, all traceable to one two-line fix that introduced a new namespace. One
campaign, not a measured rate — the mechanism is the transferable part, not a threshold.

## Say what the target is, and what absence means

The most common thing reviewers report they lacked is the stage context: they
review a design and cannot see the implementation, then hedge every finding into
a design-contract claim. Their own words, recurring across sessions: *"The packet
reviews a design, not an implemented patch, so the exact future API is not
visible."*

Name the stage and say what absence means — "this is a pre-implementation
design; do not treat missing implementation as a defect." A session given exactly
that instruction returned zero findings and proved it had looked, anchored on
both sides of the comparison. A session not given it filed unimplemented code as
blockers, and the user caught it manually.
The target also has a revision. Name the commit or content hash the packet
was dispatched on, and hold the artifact still until every reviewer on
that revision has returned. When a fix must land while a lens is still in
flight, map the returned findings against the pinned revision before
counting them: a finding whose anchor text no longer exists is stale,
closed by that mapping rather than re-fixed, and never tallied as open.

## Bundle the consumer, not just the artifact

When a target says "see X", X is part of the target. The corpus's sharpest
example: a reviewer identified the most load-bearing connection in a design and
then could not review it — *"§6.4 is outside the review boundary, so
axis-consumption completeness cannot be verified within the artifact."* The
request bundled the child and not the parent it depended on.

What reviewers needed, almost every time, was the consumer: the code that reads
the field, the parent doc defining the weights, the log proving the behavior. If
a claim's evidence lives outside the boundary, either widen the boundary or
accept that the claim is unreviewable — do not expect a finding about it.

## Make evidence structural, not requested

In this corpus every finding carries a `file:line` anchor and every empty result
carries a rationale — 2,466/2,466 and 981/981. Not because the prompts asked
nicely: the submit schema refuses output without them. The result is a corpus
where reviewers are right about existence (0.3% of issues end unresolved after
argument) and where "found nothing" is a verified statement rather than silence.

This is the general capability-boundary rule applied to review:
when output must have a property, make it unavailable without it. If your review
route has a schema, put the anchor there. If it does not, the demand belongs in
the request — but expect the weaker result that a request-only rule gives you.

The same applies to the target: a document that cites its own facts as
`file:line` gives the reviewer a falsifiable surface, and the corpus's best
findings are refutations of exactly those cited facts. Prose gives nothing to
check.

## Claim only what the evidence proves, and attribute it to one root

Reviewers are calibrated on whether a defect exists and miscalibrated on why.
When a finding is narrowed, the defect itself almost always survives (97%,
n=212). What gets cut is the causal attribution (45%) or the surface the claim
covered (34%) — not the proposed fix (10%), and not the defect. Lenses register
this as a first-class stance: `narrow` appears 1,320 times against 101 for
`oppose`. They rarely disagree that something is broken; they routinely disagree
about what broke it, and about how much of the system it touches.

"Narrowed" is a misleading name for what happens. Narrowed claims get **longer**
— 94% of them, by a median of ~118 characters — because narrowing adds
qualification and re-attribution rather than deleting text. The final root cause
is a near-rewrite (median text similarity 0.21 against the original). What looks
like trimming is the reviewer being made to say what its evidence actually
supports.

That makes narrowing and rejection the same force at different granularity:
overclaim beyond your evidence and the finding is narrowed if a proven core
exists, dropped if it does not. The corpus language is identical in both — the
survivors are "narrowed to the directly evidenced command-wiring gap", "to files
proven in capsule authority_refs", "to the demonstrated side-effect path".

So ask for the observable failure and the evidence that proves it, scoped to the
surface that evidence covers. Treat the reviewer's causal story as its weakest
claim — a hypothesis to verify, not a conclusion — and do not let a proposed fix
become the design by default.

One axis is easy to miss: in ~17% of narrowings every lens accepts the defect,
the root, and the fix, and the only live disagreement is **how bad it is**. That
matters more than its share suggests, because severity decides survival — a
finding rated low never reaches the deliverable. If severity is contested, it is
the thing to adjudicate, not a detail to average out.

## Read participation before believing a verdict

Seven sessions reported `Finding count: 0` — a clean bill of health — with
`Participating lenses: 0/N`. Nothing was reviewed. And when the harness dies, two
separate channels lie about why. Twenty-two sessions recorded
`failure_kind: output_contract`; in the ones whose nested stderr is readable the
cause is a provider usage-limit rejection — *"You've hit your usage limit"*,
`exit=1`, no model output produced at all — so the label blames the model's
output format for a pre-dispatch billing refusal, when no output ever existed to
violate a contract. Triage by that label and you debug the prompt when you needed
to buy credits.

Two consequences for anyone consuming a review:

- The tell is the participation count and execution status, never the severity
  counts. A crashed harness renders as a perfect score.
- Artifacts named for failure may not carry it, and the two failures compound. In
  those same quota-killed sessions the file named `environment-warnings.yaml`
  recorded only `non_fatal` dispatch traces with `outputTrustImpact: unknown` and
  never once mentioned the quota; corpus-wide it holds ~9,800 warnings and has
  never fired on a real failure. So the channel named for failures never fires,
  the channel that fires uses the wrong name, and the truth is only in the nested
  stderr. Read the channel the mechanism actually writes, confirmed against the
  low-level log, not the one named for the thing you want.
- Participation tells you the lenses ran, not that they saw the whole subject.
  Git-diff-based review tools silently omit staged-but-uncommitted changes from
  a HEAD-range diff, and untracked files from any diff. Before dispatch, list
  the subject with `git status --porcelain` and expose untracked files
  (`git add -N` or a WIP commit); after the run, compare the reviewed-file list
  against that listing — an unexplained gap demotes the verdict to incomplete.
  (Our own dispatch wrapper does this check itself; apply this manually on
  review routes we do not own.)
- A review deliverable names the findings it *rejected* as well as the ones it
  kept, so a finding's presence in the document is not its survival. Deriving
  survival from presence returns 100% by construction — it did here, until the
  count was scoped to the material section, at which point 16% of the same
  findings turned out to have reached the reader explicitly flagged
  non-material. Read the verdict field, not the mention.
- Count the emitted item list against every total the harness reports —
  findings count, verdict tally, per-item decision log — before triaging.
  Zero findings is only the extreme case: any shortfall means items were
  dropped in aggregation, and the dropped set is not random, since a merge
  or filter tends to lose a whole class. Recover the difference from the
  raw per-item record and triage the union; with no raw record the
  deliverable is incomplete, not clean.

## Trust an empty result only when it cites what it checked

Empty is common and usually correct: 42% of lens invocations produce nothing,
and those runs have *larger* inputs and sit *later* in a repo's review sequence
than productive ones — they are re-reviews of targets already fixed. The waste
worth naming is not the empty result; it is paying full pipeline cost to
re-review something you already repaired.

An empty result earns trust from its rationale. A reasoned null names the
evidence it checked on both sides of the comparison. A rationale-free empty
result is a failed run wearing a clean verdict — gate on the rationale, not on
the emptiness.

## Spend deliberation where it adjudicates, not where it agrees

Two-thirds of issues (66%, n=1153) never need deliberation, and the largest
single cause of halted sessions is the user cancelling. But they do not cancel
early: of 27 cancelled sessions all 27 reached the raw first pass, 22 reached the
consolidated finding ledger, and only 2 reached deliberation. Users wait for the
deduplicated, severity-tagged ledger, act on it, and abandon the deliberation and
synthesis that would have run next. Meanwhile the issues that *are* deliberated
and survive are the most reliable in the corpus (94% material vs 74% for
undeliberated).

So deliberation is worth its cost when it adjudicates a contested claim, and is
ceremony when every perspective already agrees — one of the largest deliberation
artifacts in the corpus resolved 22 of 22 issues as "no deliberation needed".
Front-load the actionable findings, because that is the part that gets used.

## Choose perspectives that can bite

Adding a perspective is not free. In this corpus the concept-surface lens
produces the fewest findings, is silent most often, and half of what it does
produce is discarded — because 43% of its candidates are rated low, and low
never survives. Naming, redundancy, and abstraction concerns count only when
they change runtime behavior or enforced semantics; ask for them on that
condition or not at all.

The inverse failure is worth watching for: when no perspective owns the real
risk, a reviewer files a governance gap instead of a defect — *"this is a
review-governance gap, not a design defect in the target."* That is the review
telling you its own lens set was wrong for the target.

## Evidence base

Derived 2026-07-16 from ~330 onto review sessions across 15 repositories in this
environment (1,738 classified issues; 2,466 anchored findings; 278 deliberations;
14,370 lens stances). Every count here was reproduced independently before being
written down, and several first attempts were wrong: survival measured by
document presence returns 100% by construction, and hand-rolled verb-object
counting undercounted the narrowing axes about fivefold. Where a share is given
for how narrowing splits, read it as a floor — ~19% of cases resist
classification — and trust the ordering (root > scope > severity > remedy) rather
than the magnitudes.

Two limits bound what this guide may claim. The corpus is ~95% a single model
family, so nothing here is a per-model claim. And it contains no under-specified
requests — the shortest still names its axes and its evidence bar — so these are
the failures that survive a *good* request, not an argument that requests need
specifying. Re-derive from a fresh corpus when the review route or the bound
models change.
