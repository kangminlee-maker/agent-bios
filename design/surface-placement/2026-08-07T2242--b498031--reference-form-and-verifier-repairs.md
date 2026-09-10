---
created_at: 2026-08-07T22:42:00+09:00
head: b498031          # the commit the content was true at
kind: design
supersedes: 2026-08-07T1422--1acdd65--verifier-coverage-map.md
---

# Closing the reference form, and three verifier repairs it exposed

The map in the superseded record listed where the verifier could miss a product error.
This is what happened when one of those was closed. Numbers here are claims about the
tree at `b498031`; re-derive from `compose/domains.json` and the gates before acting.

## The finding that would not stop recurring

Seven review findings across four rounds had one shape: **the check's claim was broader
than the set it enumerated.** The router check said "a bullet or guide that names another
guide" while the code enumerated one *form* of naming — a path, then a declared handle,
then a handle derived from the filename. Each round found the next paraphrase.

The mechanism is structural rather than careless. Implementation comes from the failing
instance; the claim comes from intention. A negative control planted from that same
instance cannot see the gap between them, because it is drawn from the half that is
already covered. A reviewer catches it because they read the claim and probe its
boundary. Every one of the seven was over an **open-ended subject set**; no closed-set
check on this branch ever failed.

## Detection does not close. Declaration does

The first attempt kept detecting and tried to make detection exhaustive by triggering on
the guide's **name** rather than on a phrasing. It over-fired at ten violations, and the
reason is worth more than the attempt: **guide filenames are built from concept names.**
`session-distill` in a body is the pipeline, not the file, and three guides sharing the
`llm-capability-boundary` prefix flagged each other. A name-triggered rule cannot tell a
mention from a reference.

What is decidable is narrower and inverted:

> A token run that identifies **exactly one** guide, appearing outside a path reference,
> is a reference the code cannot resolve — unless LEXICON declares that run a concept.

A run two guides share identifies no file, so it can never be a reference and is not
judged. The open axis — how the sentence was worded — disappears. What remains is the
set of guide names that are also concepts, and LEXICON already owns and gates that set.
Measured on this tree: **one**, `session-distill`. A declared concept keeps the
referring-word test rather than a free pass, because "the session-distill guide" is
still a reference.

This is not zero residual, and the code says so instead of implying otherwise. A
reference worded around every referring word still passes — and it is a reference a
reader could not follow either.

## Three defects the closing exposed

**1. An author-side rule cannot live in a shipped gate.** The rule first went into
`compose/check-domains.py`. That file ships: `install.sh` runs it on verify and
`compose/assemble.py` runs it on **every install**, then `die()`s on a non-zero exit. It
now required `ko/claude/guides`, which `package.json` `files[]` does not carry. `npm
pack` and the extracted tarball reproduced it exactly — one violation, exit 1 — and the
install scenarios failed on this branch while its parent passed. Every check run from
the clone was green, which is the whole failure mode `AGENTS.md` §6 exists for. The rule
moved to `gates/check-lexicon.py`, which is author-side and may read `LEXICON.md` and
`ko/`.

**2. The prose form was hiding a real cross-domain gap.** Converting the last bare name
to a path made the co-package check fail: `cli-multi-model-workflow` is
`multi-agent-orchestration`, `coding-staged-workflow` is `builder-base`, and that reader
can hold the first without the second. This is the same class as the `builder-base` rule
that promised an orchestration guide. The sentence's two siblings already name their
principle and inline the substance in parentheses; this one now matches them.

**3. The reach scan was reading the gates instead of the wiring.** Review found the
seeding — roots listed the two umbrellas beside the pre-commit hook, so dropping either
from the hook changed no finding. Rooting the closure in the hook alone exposed why the
seeding had been necessary, and it was two more defects underneath:

- The extractor consumed `(.*)$` into the match, so `finditer` advanced to end of line
  and a line naming two scripts registered only the first. The hook invokes both
  umbrellas from one `for gate in A B` list — so `check-parity.sh` was never a hook edge
  at all, and without the seed the closure reached almost nothing.
- A file test counted as an invocation. The parity umbrella guards the package gate on
  one line and runs only its self-test on the next, so `[ -x ... ]` silently readmitted
  the edge the self-test rule had just removed.

Its control is the **empty hook** rather than a dropped edge: the umbrellas cite each
other and `install.sh` reaches the package gate a second way through the install
scenarios, so no single edge is load-bearing and a per-edge control fails on a correct
tree. It passes trivially today, and that is its job — re-seed the roots and it fires.

## What a control has to survive

Two controls on this branch survived a faithful revert and were therefore fake. A third
was written this session and caught its own author: the KO half of the reference-form
rule was inert because `\b가이드\b` never matches `가이드를` — a Korean particle attaches
with no space. The control found it before the tree did.

One revert attempt was itself unfaithful. Reverting the *tail computation* left the scan
green, because the real prior defect was the **regex consuming to end of line**. A revert
that does not restore the actual prior mechanism proves nothing, and its green reads
exactly like a passing control.

## Open

| Item | Why it is still open |
| --- | --- |
| Publication provenance | Nothing binds a published tarball to a commit; 0.9.9 shipped from an uncommitted tree |
| Revert test | Prose in `AGENTS.md`, run by hand. Mechanizing it is mutation testing of the gates |
| Monolith reference form | `claude/CLAUDE.md` section headings are concept names by construction (`## Multi-Model Workflow`), so the rule needs them declared first |
| Semantic correctness | Whether the relocated payload says the right thing. Recorded as a decision, not a gap |
