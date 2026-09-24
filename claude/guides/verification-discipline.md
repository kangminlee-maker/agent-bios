---
guide_id: verification-discipline
language: en
status: active
use_when:
  - deciding how much verification a change deserves, before spending on a slow or expensive run
  - choosing what to run for a domain — code, ontology, config/data, spreadsheets, docs, a release
  - building the case space for a check, or deciding what its expected answer should be
  - a check came back green, empty, or fast, and you are about to believe it
  - running independent or adversarial review, and judging what its agreement is worth
core_rules:
  - a check is only evidence if it could have failed — assert a non-empty subject before any "no bad X" claim
  - enumerate the case space from the artifact that defines it, and record real output instead of typing an expectation
  - proportion depth to cost, risk, and information gain; a single-user tool does not warrant production assurance
  - same-kind reviewers share blind spots, so their shared "clean" is an absence of objection, not verification
---

# Verification Discipline

A scoped extension of the global Verification Discipline section. Its subject is not "did you
test it" but the harder question underneath: **could this check have failed?** Everything below
is a way of answering that before the result is believed rather than after it is quoted.

The global rules that stay always-loaded are the ones whose moment does not announce itself — you
believe you are finished, and that belief is the failure. This guide is what you open once you
know you are verifying.

## Proportion the depth before you spend

Verification has a cost and an information yield, and they are not correlated by default. Decide
the depth first:

- Diagnose in code before running anything expensive, and replay the changed deterministic logic
  over persisted real artifacts rather than re-running the whole pipeline to observe it.
- Probe at N=1 with the inputs precondition-checked. A single well-chosen case that reaches the
  real path outranks a hundred that stop short of it.
- Bound the N=1 probe to reachability. One case settles whether a path works — never how often a
  stochastic behavior holds. Before quoting a rate-shaped property (determinism, flake rate, an
  A/B effect), confirm the mechanism honors your controls, establish the noise floor from runs on
  hand, then sample enough to bound the rate against a no-treatment control on the real path. A
  floor larger than the effect breaks the premise — record it before redesigning.
- Reserve the full design-review-plus-live-verification treatment for first-of-kind work and for
  changes that move authority — who may decide, who may write, what is irreversible.
- Proportion assurance to the deployment context. A single-user tool operating on its owner's own
  data does not warrant production-grade assurance, and treating it as if it did buys nothing
  while delaying delivery. Prefer shipping.
- Census the population before a costed or irreversible batch. Read its current state cheaply and
  deterministically — status distribution, version, presence of the artifacts the plan expects —
  and compare that against the premise the batch rests on, halting to re-diagnose when the
  distribution contradicts it. A probe validates the path; only the census validates that the
  population is what the plan assumes. A cheap idempotent batch over a few items needs none.

The failure this prevents is not under-testing. It is spending the verification budget on the
cheap half of the risk and having nothing left for the part that could actually hurt.

## The static floor

Run the broad, cheap checks first and let them fail before anything slower starts: typecheck,
lint, build, format, schema and config validation, graph validation, workbook structure checks,
import boundaries, and security checks where they exist. These are a floor, not a verdict — they
prove the artifact is well-formed, never that it behaves.

## Verification Menus

Pick the narrowest reliable mix that proves the changed behavior, meaning, or contract. Inside the
mix, the unit to add is the narrowest reliable runtime or semantic test that proves it — narrowest
meaning the smallest test that would fail if the change were wrong, which is not the same as the
cheapest one to write.

- Code: a layered mix of unit tests, integration tests for E2E segments, targeted E2E for changed flows, and full E2E for release or high-risk changes.
- Ontology: static graph checks, concept economy gates, changed-path integration checks, and competency-question E2E checks.
- Config or data: real parsers, schema checks, fixture validation, and sample transformations.
- Spreadsheets: static workbook checks, fixture-based output checks, cross-sheet flow checks, visual/layout checks, and real Microsoft Excel engine recalculation for formula-dependent results.
- Docs: links, terminology, current behavior alignment, and references to isolated historical notes.
- Multi-subject prose: when deliverables draw on material about different people, companies, or cases, bind every captured item to its subject and confirmation status at capture, and narrate nothing under a subject until that binding is confirmed. Cross-check subject-specific proper nouns and figures across all outputs before delivery — one subject's term under another is the signature of context bleed. Keep a figure in the same sentence as its composition, since a detached number is read at its worst.
- Release or distribution: after publishing to multiple independently writable channels (signed manifest, object storage, release host, embedded updater), digest-verify every referenced object against the staging original per channel — publish success and upload order are not evidence — and run the real installer/updater through its default path.
- A/B or on/off measurements: before accepting a null result, verify the arms actually received different treatment in the mechanism under test — a shared default or unconditional upstream step can silently apply the treatment to both arms.
- Multi-stage pipelines with nondeterministic stages: a final-output diff cannot attribute an effect or a regression to a stage — it conflates the change with run-to-run variance. Persist every stage's output, tabulate what each creates, may edit, and only guards, restrict the suspects to the stages that edit the content in question, and find the first stage where the intended effect disappears or the defect appears. Fix there, preferring a structural recheck over another prompt-level instruction that already failed.
- Before/after comparisons: pin the input to an immutable copy — a snapshot or versioned artifact — and run both arms against it, because a live artifact (a growing log, a regenerated upstream stage) drifts between runs and any diff over it, a matching one included, is evidence of nothing; when the arms are metered, restore the baseline's exact upstream inputs and re-run only the changed stage. This is input identity, not the separate unit-and-denominator basis rule.
- Cost figures from provider usage records: before pricing, map every provider's token fields onto one schema — uncached input, cache read, cache write, output. Some providers report input as a total that already includes cached tokens: treating that total as uncached input and then adding the cache-read field again counts the cached portion twice, while charging the inclusive total once at the full rate misprices that portion instead. Other providers exclude cached tokens from the input field. When a provider reports or prices cache writes separately, keep them in their own field. Confirm each provider's field meaning against its own usage documentation or a known sample, never by analogy with another provider, and derive the cache hit rate from the normalized fields.
- Model-behavior guardrails: verify by changed behavior, not recitation — a staged battery from named-trigger cases through disguised, deconfounded, category-wide, and single-variable framings; a clean pass means "no known defect", so re-run the battery when the model changes.
- Branch/version test builds against real data: explicitly separate every state sink the app touches (files, DB, OS-level stores that ignore env overrides), confirm the launch path propagates the isolation to child processes, and back up live data before the first run — a mismatched schema that drops unknown fields on write is data loss, not a no-op.
- Sandbox, replay, or re-adjudication runs on production-derived config: enumerate every outbound channel the stage can reach — publish, upload, notify, external write — and disable or redirect each one before the run, proving each disarm fires as you would prove a path guard; a guard on the input or target path alone leaves egress armed. Fingerprint every external destination before the run and diff it after, so an escaped write is caught by the run rather than by a recipient.
- Irreversible capture switches: when activation itself has unreproducible cost (a capture window that cannot be replayed), prove the downstream consumption path against existing samples before enabling — reversibility of the code path alone is not enough.

## Deriving the case space

Which scenarios exist is semantic work: derive them from the diff, the user impact, the
concept impact, and the failure modes. Running them is not — tools and code execute the
cases and report the evidence. Keeping that split is what stops a suite from being a
record of what someone imagined.

A check has two authored halves, and they rot differently. The **verdict** — what the
answer should be — rots by encoding a belief that was wrong from the start. The
**space** — which cases exist — rots by staying still while the thing it covers grows.
Recording the verdict is common practice; deriving the space is the half usually left
hand-written, and a suite can have every expectation derived and still cover a set
someone typed once.

- Make the criterion falsifiable before you make it green. Prefer a signal that fails when
  the mechanism is wrong — a negative or contrast control. Where no existing gate can judge
  a criterion, build the executable judge or do not claim the criterion met: a criterion
  nothing can fail is a description of the work, not a check on it.
- Record the verdict, do not type it. Run the real path and store what came back;
  drift then shows as a diff instead of as a belief someone has to re-justify.
- Enumerate the space from the artifact that defines it — the config's entries, the
  schema's fields, the router's routes, the installer's call sites. Adding one there
  should widen coverage with no edit here.
- Derive the exemption rule too. If some cases legitimately have no answer, decide that
  from a property the artifact carries, never from a list of names: the list is the
  authored space coming back through a side door, and it absorbs the regression where
  a case that should have an answer stops having one.
- Dedupe on the tuple that actually determines the outcome, and report how many
  collapsed. A coverage count that hides its own truncation reads as more than it is.
- Split by cost, not by space. When the real path needs money, credentials, or a
  network, run a cheap stand-in on every commit and the real one on demand — both from
  the **same enumeration**, so the two can never disagree about which cases exist.
- Derivation moves authorship rather than removing it: the extractor and the invariants
  are still written by hand. Give them a negative control, or the derived suite is just
  a larger unfalsifiable one.
- Planting a violation to prove a control fires is a write into the working tree, and
  the restore is not atomic with it: if the probe can time out, abort, or be
  interrupted, a restore sitting after it never runs and the plant survives into a
  commit. Plant in a copy where the shape allows it, and when it must be in place, snapshot
  first and restore from the snapshot as its own step rather than trusting the probe to finish.
- Attribute a fault by a controlled contrast before choosing a remedy. Hold everything constant —
  principal, path, input — vary only the candidate variable, and read a countable difference
  (element dimensions, request count, status-code family). A missing error report is not
  exoneration: channels can be suppressed, unobserved, or unwired from the mechanism at fault, so
  "no violations logged" rules a cause out only when the contrast shows none either. Read the
  contrast the evidence already holds before proposing a policy loosening.

## When a green means nothing

A passing check and a check that never ran look identical from outside. These are the shapes that
produce a green with no evidence behind it:

- **The empty subject.** Any "no bad X" or "all X satisfy P" claim over an empty set is
  vacuously true. Assert the entity-under-test set has cardinality greater than zero **before**
  the claim, and make the gate itself refuse to report clean when it judged nothing.
- **The fixture that misses the guard.** For a test touching a branch you are adding or deleting,
  confirm its inputs satisfy the live branch's entry guard. A copied fixture that fails the new
  guard routes silently into the about-to-be-deleted dead branch and stays green after the real
  behavior breaks.
- **The fixture the producer never emits.** A test's input is evidence only when the thing that
  produces it in production produced it. A wire fixture must be a raw response captured through
  the same client that will parse it, never a rendered listing or a hand-written payload; a gated
  feature's E2E must run with the gate in its production setting, on the state its real upstream
  leaves. Replay against the live producer once, then probe every sibling built the same way.
- **The permissive fallback in the checker.** A `a || b` inside a gate absorbs a wrong assumption
  and keeps passing. Checker code must assert the shape it expects and fail loud.
- **The suspiciously fast or empty run.** When a check goes green unexpectedly quickly, or reports
  nothing at all, dump what it actually ran over before believing it. A harness that crashed early
  and one that found nothing produce the same exit code.
- **The verdict that ran before its checks.** If a runner computes or prints its overall verdict
  before all checks finish, later failures cannot change it. Accumulate one failure count across
  every check, then compute the verdict and exit status once, after the last check. Read a
  multi-check run from that final count and an exit status verified to derive from it — never from
  `tail` or collapsed last lines, which hide failures printed earlier.
- **The control that failed by crashing.** A negative control is evidence only when it fails
  through the assertion it names: a traceback and a caught violation share an exit code, and an
  early crash can pre-empt every control after it. Treat each traceback in a control run as a
  defect until the run reports one named failure per planted violation. Run any unattended gate
  with stdin closed, so a path reaching a prompt fails at once instead of hanging.
- **The control that went quiet.** A negative control indexing a live list stops testing when that
  list empties, and says nothing about it. New controls build their own subject; resolving an item
  means re-reading the controls for ones that have gone silent.
- **The silent log.** Absence of activity is not evidence of non-use. Before retiring an
  identity, key, or endpoint on a quiet log, show that the queried field is the one recording the
  subject — delegated actions are attributed to the caller, with the target in another field, so
  the wrong field returns clean silence — and that no live binding still references it, since a
  reference proves use while emitting no traffic. Only a demonstrated "this use would have been
  logged" evidences non-use.
- **The population that shrank.** A gate scanning an explicit list of files sees only "listed but
  empty": a subject that migrates to an unlisted surface leaves the scanned set smaller yet
  non-empty, so the empty-subject guard never fires while coverage erodes. Retarget the gate in
  the same change that moves the code, and pin a floor so any decrease fails loudly — proved by
  moving one subject out. A floor is a ratchet: never lower it to pass a run.
- **The mutant that never ran.** A mutation verdict counts only if the mutant is valid: it
  compiled, sits on a path the exercised test traverses, and changes the guarded behavior, not
  healed downstream or coinciding with a default. The runner must report build failure,
  unreachable, equivalent, and timed out distinctly from KILLED and SURVIVED, and halt on a moved
  anchor. A timeout is not a kill: it moves with machine load, so set the limit well above the
  unmutated suite's runtime and accept a verdict only when repeated runs agree on which mutants
  timed out.
  More tests red than the mutation should touch indicts it; classify a survivor (rebuild,
  discard, genuine gap) before writing a test. **Equivalent is a verdict about the probe as
  much as the mutant**: a probe that is dead or returns a constant reports every mutant as
  equivalent, and one aimed at an input the mutant does not affect reports the same. Refuse
  the verdict unless the probe is shown to discriminate on UNMUTATED code and to exercise the
  input the mutant targets — an unusable probe is its own outcome, not an equivalent mutant.
- **The probe that measured the original.** A copied script that derives its root or targets from
  its own location (`$0`, `BASH_SOURCE`, a `cd` to its parent) scans the original tree, not the
  copy, so its verdict says nothing about the mutation you planted. Pin the subject in the copy,
  copy the whole tree, or plant in place with a snapshot-restore. The tell is a result identical
  to the unmutated run; a script taking its subject as an argument is safe to copy.

The discipline that covers every shape above: after adding a check, revert the fix it guards and
watch the check fail. A control that survives a faithful revert was never testing the thing it
names. Prove the plant landed: assert the altered input differs from the original and that the
control's cases reach the mutated branch before asserting rejection. Construct corruption
deterministically: scanning for a flip site yields no-op mutations reporting a rejection nothing
exercised.

## Before blaming code for a metric change

When a live metric collapses or crosses a pre-declared threshold, localize the change in time
before diagnosing the feature: confirm every inbound source is alive, compare only
contemporaneous cohorts, never re-processed rows, then bracket the transition to the finest unit
available and read the deploy log around that instant.

A change landing seconds from the last-good point is the prime suspect; a step in a window with
no deploys is an input-population shift, fixed by scoping the measured population, not the model
or the code. Declare the threshold before looking, and confirm a failure from the fleet's vantage
rather than your own — this does not replace fixing the comparison basis, which comes first.

## Keeping E2E honest

E2E is where flakiness is mistaken for environment noise and then ignored. Keep it deterministic
with fixed data, resilient selectors, isolated external dependencies, and explicit waits rather
than sleeps. A flaky E2E is not a weaker test; it is a test whose result carries no information,
and a suite that people re-run until it passes has been switched off without anyone deciding to.

## Independent review, and what agreement is worth

For non-trivial designs and high-risk changes, run independent adversarial review across distinct
lenses — ideally on the design, before implementation, when a finding is still cheap to act on.
Then re-verify each finding against real code before acting on it: a reviewer reasons from what it
was shown, and what it was shown may be wrong.

Apply the **convergence heuristic by reviewer kind** — judge the result by reviewer kind, not by count:

- Same-kind convergence is high confidence but blind-spot-sharing. Two reviewers of the same kind
  agreeing that something is clean is an absence of objection, not verification.
- Different-kind divergence is the expected signal, not a problem to resolve. Act on the union of
  what they found rather than the intersection.
- An orchestrated workflow's self-reported all-green is never sufficient on its own. Re-run the
  diff inspection and the verification suite yourself.

The cheapest way to buy real independence is a different provider; after that a different model;
after that strictly higher effort. A reviewer run at lower effort than the work it checks buys
nothing — cheaper is not another perspective.

## Reporting

Before calling the work done, state the checks that ran, their results, and any risk left
unverified. "Unverified" is a legitimate outcome and a useful one; silence about it is not.
