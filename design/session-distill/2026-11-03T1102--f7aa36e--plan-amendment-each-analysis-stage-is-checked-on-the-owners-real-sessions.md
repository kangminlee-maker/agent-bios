---
created_at: 2026-11-03T11:02:28+09:00
head: f7aa36e
kind: design
supersedes: null
---

# Plan amendment: each analysis stage is checked on the owner's real sessions before the next is built

This amends `2026-10-20T2119--cc0498f--implementation-plan.md`. It is the owner's decision of
2026-11-03, taken when the remaining packages were counted: under the plan as written, the first
result the owner can judge is the rehearsal (WP-23), weeks of packages away, and every stage before it
is checked only against fixtures. A stage that is correct against its fixtures and useless on the
owner's sessions would be found last.

## What changes

After each analysis stage lands, the stages built so far run on a small, recent window of the
owner's real sessions, and the owner judges the result before the next analysis package starts.
The package order, the contracts and the §4.3 authorization are unchanged.

| Checkpoint | When | Stages run | What the owner judges |
|---|---|---|---|
| C0 | now | S0, S1 census, S2 views and inventory | whether every session in the window is counted, and what the run says it could not know |
| C1 | after WP-08 | + S3 read and stitch | whether the stitched reading matches what happened |
| C2 | after WP-09 | + S4 candidates | whether the candidates are worth having |
| C3 | after WP-10 and WP-11 | + S5 checks, S6 judgments | whether the judgments are believable |
| C4 | after WP-12 | + S7 proposals | whether a proposal would be accepted |

## How a checkpoint runs

- **A declared run, posture `development`.** Its window is one to three recent days; its run
  directory lives in the workbench, outside the checkout, mode 700. A checkpoint run is not a
  rehearsal or a production run: it is not evidence toward §4.3, and no later stage of a production
  run consumes it.
- **One page for the owner, in Korean.** The stage outputs are rendered into one local page with two
  or three questions. It holds the owner's session content, so it stays a local file the owner
  opens; it is not published. The lead and the implementer read the run's counts and structural
  fields, not the session content.
- **The answer gates the next package.** The owner's answers are recorded as a decision. An answer
  that the output is wrong reopens that stage before the next analysis package starts; the
  correction goes through the stage's own package rules (controls, review).
- **Cost.** C0 makes no model call. From C1 on, a checkpoint's model calls are declared with a
  budget in the order of §8.1's development rows for that package (≈60k–150k input tokens), and the
  owner's go for C1 is asked with its estimate before it runs.
- **Building the page** is part of the package that lands the stage (about half an implementer
  session each). The pages are working instruments; WP-20's S9 render is still the product's review
  surface and may reuse them.

## Not changed

- Native layers stay `unknown` in a run's inventory until the S0 native-capture package
  (`2026-10-23T1336--2a61d6b--plan-amendment-s0-native-capture-is-its-own-package.md`) lands; C0
  reports them as such.
- The thin end-to-end slice (deferring WP-16–WP-19 to wire read → candidates → proposals → review
  first) was the alternative offered; it was not taken because it reorders the plan and risks rework
  of stages built ahead of their checks.
