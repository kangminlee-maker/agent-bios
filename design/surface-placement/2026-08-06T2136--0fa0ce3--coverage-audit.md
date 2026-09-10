---
created_at: 2026-08-06T21:36:00+09:00
head: 0fa0ce3
kind: design
supersedes: none — first coverage audit; corrects a claim made in-session, not in a prior record
---

# Almost nothing is delete-only: the guides do not yet hold what the global would hand them

The sweep's premise was that four sections compress to a pointer "because their guide already
exists". A guide existing is not the same as a guide answering. This audit reads the target
guide's body against each rule, clause by clause, and the premise mostly fails.

**This record exists because a keyword probe produced a wrong answer and it was reported as a
finding.** The probe searched each target guide for one distinctive word from the rule and called
a hit coverage. Six rules came back "delete-only"; reading the passages, one was. Four of the six
would have been deleted from the corpus while leaving a pointer to a guide that does not answer
them. A word is not a clause, and a hit is not a match — anything below that is not backed by a
quoted passage should be treated as unverified.

## Verdicts

`DELETE-ONLY` the guide answers every clause · `PARTIAL` some clauses, named gap ·
`AUTHOR` nothing usable · `KEEP` stays global, with the reason

### Coding Guidelines

| rule | target | verdict | what the guide actually has / lacks |
| --- | --- | --- | --- |
| 설계 trigger | coding-staged-workflow | **DELETE-ONLY** | states it near-verbatim, including "move to implementation after the user asks or approves" |
| think before coding | coding-staged-workflow | AUTHOR | Stage 1 lists goal/scope/tradeoffs; says nothing about stating assumptions or surfacing ambiguity early |
| smallest viable path | coding-staged-workflow | PARTIAL | has "make the smallest viable functional changes"; **lacks what minimum must not reduce** (behavior, authority, evidence quality, verification depth) — the half that stops it becoming an excuse |
| surgical changes | coding-staged-workflow | AUTHOR | absent. Core tier already carries the essence twice (`Keep file changes within the requested scope`, `stay within scope`) |
| clean up what this change introduced | coding-staged-workflow | AUTHOR | absent |
| own the full lifecycle | tooling-gotchas | **KEEP** | `## Own what you spawn` opens "Instance of the global rule" — a declared, anchor-pinned restatement. Guide covers subprocess/handle only; artifacts-out-of-temp and the deploy-managed/user-owned colocation ban have no instance |
| define success criteria | coding-staged-workflow | PARTIAL | Stage 1 names completion criteria; the before/after-verify pairing is not stated |
| reproducing test before fix | coding-staged-workflow | AUTHOR | absent (0 hits) |
| every changed line traces to request | coding-staged-workflow | AUTHOR | absent; core covers the essence |
| root cause at its authority | coding-staged-workflow | AUTHOR | absent (0 hits) |
| default-off + security weakening | coding-staged-workflow | AUTHOR | absent (0 hits). The longest bullet in the corpus at 827 chars |

### Verification Discipline

| rule | target | verdict | what the guide actually has / lacks |
| --- | --- | --- | --- |
| verification loop after every change | coding-staged-workflow | AUTHOR | the guide references "the global Verification Discipline loop" — it consumes the rule, it does not state it |
| static checks broadly | coding-staged-workflow | AUTHOR | the menus are per-domain mixes; the static-check list is not among them |
| narrowest reliable test | coding-staged-workflow | PARTIAL | "pick the narrowest reliable mix that proves the changed behavior, meaning, or contract" governs choosing a **mix**, not adding a test. Closest call in the audit |
| verification mix from the Menus | coding-staged-workflow | **KEEP** | already a router, and its anchor phrase is gate-pinned |
| case space from the artifact | coding-staged-workflow | PARTIAL | `### Deriving the case space` covers enumerate-from-artifact and record-the-verdict **more deeply than the bullet**; the LLM-derives / tools-execute division is not there |
| E2E stability | coding-staged-workflow | AUTHOR | absent (0 hits for deterministic data, resilient selector) |
| green check traversed real code | coding-staged-workflow | AUTHOR | absent (0 hits) |
| falsifiable completion criteria | coding-staged-workflow | PARTIAL | the guide's only "unfalsifiable" is about derived suites needing a negative control; **build the executable judge or do not claim the criterion met** is absent |
| common basis before comparing | coding-staged-workflow | AUTHOR | the A/B menu entry is about arms receiving different treatment, a different failure |
| adversarial review / convergence | review-request | PARTIAL | Review Loop has the severity contract and review kinds. The convergence heuristic's depth lives in `cli-multi-model-workflow`, which builder-base users do not receive — see the prose-router fix at `ff8afff` |
| proportion verification to cost | coding-staged-workflow | AUTHOR | absent (0 hits) |
| non-empty subject / vacuous pass | coding-staged-workflow | AUTHOR | absent (0 hits) |

### Tooling and Operational Safety

The design record judged this section "stays global, because an unknown trap is exactly what you
cannot look up". Two cross-family reviewers disagreed on two of the six. Reading the guide
settles it differently again: the section stays, but mostly because **the guide does not hold the
content**, not because the rules resist being looked up.

| rule | verdict | what the guide actually has / lacks |
| --- | --- | --- |
| ambient state | **KEEP** | `## Ambient state drifts — pin it` opens "Instances of the global rule" — declared and anchor-pinned. Covers interpreter, command resolution, cloud CLI context, installed-is-not-running. **'latest'-style pointers and version-bearing paths have no instance** |
| confirm empirically | AUTHOR | "Installed is not running" is about a live process, not about confirming a model id / flag / capability claim against the artifact |
| destructive action scoping | AUTHOR | "Own what you spawn" covers killing the right group; rm/force-push/reset scoping, the snapshot-before-overwrite, and the identity gate are absent |
| secrets procedure | AUTHOR | the secrets section covers config slicing and production probes; the env-slot procedure and the echo-back-on-create trap are absent |
| coarse runtime signal | AUTHOR | nothing on I/O wait, idle CPU, or reading the provider's own payload. The guide's "hang" hits are `read -d` and event-loop hangs — a different subject |
| git fetch / range / sibling PRs | PARTIAL | "Two-dot diff semantics" covers `git diff A..B` vs `origin/base...HEAD`. Fetch-first, the stale local base on a shared repo, and sibling-PR mergeable flags are absent |

**Not a defect, checked:** the global says `origin/<base>..HEAD` (two-dot) and the guide says
`git diff origin/base...HEAD` (three-dot). These are different commands and each form is right for
its own — `log` takes the range, `diff` takes the merge-base form.

### Documentation Hygiene

All six remain **BLOCKED** — no builder-base or universal guide owns the subject. Independently
reached by the cross-family reviewer, which also named `svg-visualization-guide.md` as a second
illegal target alongside `implementation-map.md`.

## What this changes

| | count |
| --- | --- |
| delete-only | **1** |
| keep (declared restatement or already a router) | 3 |
| partial — guide holds some, the named gap must be written | 6 |
| author — nothing usable in the target | 19 |
| blocked — no legal target guide at all | 6 |

The sweep is not a deletion pass. It is **authoring**: for all but one rule, the global copy is
the only copy, and moving it means writing it into a guide first. That is the same shape of work
as the Concept Economy guide, spread across two existing guides instead of one new one.

Two cheaper moves exist and neither is a deletion:

- **The `PARTIAL` six** are the best value: the guide already carries the recognizable half, and
  what is missing is one clause each. Six small edits, not six sections.
- **`AUTHOR` rules that duplicate core** (surgical changes, every-changed-line) can be dropped
  rather than written, because the universal tier already states them and reaches every user.
  That is deletion justified by an existing authority, not by a guide that would have to be
  written.

## Method, so the next reader can judge it

Every verdict above was reached by reading the target guide's body. `tooling-gotchas.md` and
`coding-staged-workflow.md` were read in full. Absences are stated as 0 hits from a `grep -a`
over a distinctive phrase **after** the body had been read, as a check on the reading rather than
as the reading itself — which is the inversion that produced the wrong answer the first time.

Not audited: whether each `AUTHOR` rule *should* move at all. This record answers "can it move
without losing content", not "does the placement criterion send it". Those are separate questions
and the second one has three independent classifications behind it already.
