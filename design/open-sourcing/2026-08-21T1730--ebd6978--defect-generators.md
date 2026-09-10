---
created_at: 2026-08-21T17:30:00+09:00
head: ebd6978
kind: design
supersedes: none — cross-round analysis over the rounds recorded beside it
---

# Five generators behind every defect these rounds found, and what would actually close them

User direction: stop treating findings as results, and design so later rounds
stop producing the same problems. This record classifies the defect corpus by
GENERATOR rather than by symptom, measures how much of it is self-inflicted, and
proposes fixes ranked by instances-closed per cost.

## The corpus

| Source | Findings |
| --- | --- |
| PR #44 rounds 1–3 (previous session) | the transport seam leaked **three** shapes; round 2's fix killed records |
| Round 1 (this work) | 9 review findings + 2 I introduced while fixing them |
| Root-cause round | the audit-cost chain (see `2026-08-21T1330`) |
| Round 2A (fix delta) | 12 findings |
| Round 2B (harness assessment) | 9 blind-spot classes, and a verdict that the mechanism's claim is false |

## The measurement that matters most

**Seven of round 2A's twelve findings were created by round 1's fixes.**

| R2A finding | Introduced by |
| --- | --- |
| rollback control never reaches the real slot | R1 fix for non-atomic write |
| pin control not bound to the shipped SHA | R1 fix for the pin blocker |
| `CANDIDATES` word-splitting | R1 fix for the bash locator |
| fail-closed is command-blind | R1 fix for warn-only forwarding |
| empty `?`/`#` still accepted | R1 fix for query/fragment (incomplete) |
| empty `legs` returns OK having judged nothing | root-cause round's leg mechanism |
| `_expect` does not establish the catcher set | root-cause round's declaration rule |

A fix rate that produces defects in ~60% of its own output is not a discipline
problem to be solved by more care — the previous session recorded the same
pattern ("the fix for round 2 killed records") and it recurred anyway. **Knowing
it did not prevent it**, which is the whole argument for structural answers.

## The five generators

### G1 — the verification artifact is not the artifact under claim

The test measures something adjacent to the thing being asserted.

Instances: the wrapper E2E ran a symlinked clone, not the declared pin (R1) —
and its "fix" still read whatever sat in `node_modules` (R2A); the gate's decoy
fixture sat where the resolver cannot read (R1); a probe grepped `DEPLOYED`,
which `status` never prints; an isolation probe passed a path to a gate that
ignores arguments and re-measured the real repo; the CLI zero-egress probe
planted its decoy in `$HOME` where nothing reads it; the drain probe tested
`drain_uploads` rather than the shipped command (R2A). **Seven.**

### G2 — falsy is treated as absent; partial states are not modeled

Instances: `is_file()` answering False for EACCES (prev session); a name-set test
on a case-insensitive filesystem (prev); `is_file()` again for a dangling symlink
or directory (prev); `parts.query == ""` for `https://h.test?` (R2A); an
unreadable slot returning `None` and read as "no slot" (R2A); an empty `legs`
selection returning green (R2A); a value-only "unchanged" that ignored modes
(R1, and again when no token was available in R2A); a two-file write with no
model of the state between them (R1, R2A). **Nine, across two sessions, in one
product area.**

### G3 — fail-open by absence of decision

`|| true`, `return 0`, `except OSError: pass`. Nothing chose to continue; nobody
wrote "continue". Instances: warn-only forwarding kept a previous organization's
slot (R1); the rollback swallowed its own failure (R2A); and the overcorrection
— blocking every command, removing the operator's recovery path (R2A). **Three.**

### G4 — one rule, two implementations

The bash locator and the Python locator both decided "is this the pinned core",
and only one was fixed (R1). `ENDPOINTS.md`, the ontology concept, and the
resolver all stated the transport rule; the ontology kept the removed one (R1).
**Three.**

### G5 — the oracle's unit is coarser than the assertion

Round 2B's verdict. `_expect` addresses legs; `control-audit` addresses AST
statements; real checks share both units, so a table row, a predicate clause, a
narrowed subject list or an input class dies invisibly. **Nine classes, plus the
catcher-set finding.**

## What actually closed instances, and what did not

Looking at which fixes survived their own next round:

| Fix shape | Survived? |
| --- | --- |
| Hand-written expectation ("assert the slot is unchanged", "grep DEPLOYED") | **No** — every one was defeated in the next round |
| Expectation DERIVED from the artifact (resolved SHA from the lockfile; the expected reason built from the same path the assertion proved absent; `classify_status` compared against the constants that publish the contract) | **Yes** |
| A default that must be overridden explicitly (`Refusal.blocking=True`) | **Yes** — the overcorrection was about scope, not direction |
| A tri-state that makes the third case unrepresentable as the first (`slot_state`) | **Yes** so far |
| Removing the surface entirely (the ontology's behavioural restatement) | **Yes** — nothing left to drift |

The pattern is sharp enough to state as the design principle:

> **A hand-written expectation inherits the author's model. The code and its test
> are then wrong in the same direction, and the test passes.** An expectation
> derived from the artifact, or from the declaration the artifact must satisfy,
> does not inherit that model.

G1 is that principle violated on the verifier side. G2 is it violated on the
product side — "if the read failed there is nothing there" is a belief, and the
fix that held was enumerating the states instead of believing one.

## Design — ranked by instances closed per cost

### 1. Derived-expectation vocabulary (closes G1: 7 instances) — LOW cost

Make the wrong thing unavailable rather than discouraged. A small shared
vocabulary in the test harnesses:

- `expect_absent(needle, haystack, positive_sample)` — refuses to pass unless
  `needle` appears in `positive_sample`. An absence claim without a positive
  control becomes impossible to write, not merely bad practice.
- `subject_under_test()` — every harness must print and assert WHAT it ran
  against (revision, path, resolved config), and the assertion compares it to
  the declaration. `test/e2e.sh` already does this for the pin; the shape
  generalizes.
- Fixtures that name a path assert the path is READ: a planted fixture must
  change the answer when removed, or it is decorative by construction.

Predicted effect: the E2E-vs-pin, DEPLOYED-needle, decoy-placement and
argv-ignoring failures all become unwritable.

### 2. Tri-state reads at every external-state boundary (closes G2: 9) — LOW cost

One helper per boundary returning `absent | valid | unreadable`, and a gate whose
subject set is "every `except OSError` that returns a falsy value in the
transport and slot seams". The check is decidable (an AST shape), the subject set
is non-empty and assertable, and it fires on exactly the shape that has now
leaked six times.

### 3. Disclosure carries a trigger (closes the meta-decay) — TRIVIAL cost

The previous session disclosed the self-test's cost ("~2 min, full run per
mutation") and left it. It grew to 134s, which is why the audit was never run,
which is how a decorative assertion survived. A disclosure with no threshold is
a deferral with no owner. Every disclosed limitation gets a number and the
condition that converts it into work — "if this exceeds N seconds, it is fixed
before another mutation is added".

### 4. Per-assertion failure IDs (closes G5: 9+) — HIGH cost

Round 2B's proposal, and the only thing that reaches rows, clauses and input
classes. ~47 emission sites get a stable ID; controls declare expected IDs per
leg; `control-audit` maps ID → control instead of statement → self-test. The
per-leg needle now in place is the affordable half; the rest is a real refactor
and should be its own change, with its own review.

### 5. Generated, not restated, for every duplicated rule (closes G4: 3) — MEDIUM

The locator rule exists twice because bash needs it before Python runs. Either
the shell asks Python (a subprocess on every invocation — cost), or the rule
moves entirely into one of them (the shell can exec the provisioner first and
take its answer). The general rule is already in `AGENTS.md` §Where authority
lives; the wrapper simply violates it.

## What this does not promise

Later rounds will still find defects — the goal is that they find NEW classes
rather than the same five, and that fixes stop producing them at a 60% rate. The
falsifiable version of that claim, for the next round to test:

- no finding in the next round belongs to G1 or G2;
- fewer than a third of the next round's findings were introduced by this
  round's fixes.

If either fails, the level of the fix was wrong again, and this record is the
thing to revise — not the individual finding.
