---
created_at: 2026-09-26T14:09:34+09:00
head: f065835
kind: design
supersedes: 2026-09-25T1636--6fa562f--development-plan.json
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260926-53cf12, D-20260926-b757f7, D-20260926-d8e48f
---

# Plan successor: two planned module paths leave a concept's name

The [14:04 plan](2026-09-26T1404--f065835--development-plan.json) supersedes the
[16:36 plan](2026-09-25T1636--6fa562f--development-plan.json). It changes two planned paths and
nothing else, before V1 writes the first of them.

## What moved, and why

`gates/check-lexicon.py` fails a machinery file whose path carries a concept's slug outside that
concept's home. Two modules every plan has named since 2026-09-14 would have failed the day they
were written:

| Planned path | Owners | Serves | Now |
| --- | --- | --- | --- |
| `workenv/instructions_adapter.py` (`instructions` belongs to `compose/`) | V1–V8 | `role.project`, `session.routing.activate` | `workenv/roles.py` (`D-20260926-53cf12`, the owner's choice this morning) |
| `workenv/decision_use.py` (`decision` belongs to `decisions/`) | V2–V8 | `memory.use.prepare`, `memory.preference.record` | `workenv/memory_use.py` (`D-20260926-b757f7`) |

The second was not in the owner's decision. It moves in the same successor because a later one
would re-record P00 again for the same cause.

Only the plan's owned paths (15 entries) and `gates/workenv/conformance/serving.json` (4 rows)
named these modules. No SSOT, spec clause, test case or contract does.

## The bundle

- **Plan.** New, with the 15 owned paths moved, `spec` naming the new spec, and the spec's
  document binding re-hashed.
- **Spec.** [Re-stamped](2026-09-26T1404--f065835--development-spec.md). Only its frontmatter and
  its link to the graph it governs changed, because it says the graph owns file ownership.
- **Unchanged.** The SSOT, the test catalog, the dated validator, its regressions and the
  mutation sweep keep their stamps, since their bytes did not change. Their default plan path
  still names the 16:36 plan; the gate passes the selected plan to them explicitly.

`gates/check-development-plan.py` passes on the 14:04 bundle (33 positive, 442 negative controls)
and its self-test passes (7 and 71).

## P00 re-recorded

A record accepted under one plan reads stale under another. Run-7 was copied to `run-8` outside
the repository, and P00's record was rewritten by `plan_digest` alone. The re-record tool refuses
any other moved field. `SHA256SUMS` was resealed, and it differs from run-7's in `run.json` only.
Evaluated both ways with the dated validator:

| Run | Under the 16:36 plan | Under the 14:04 plan |
| --- | --- | --- |
| run-7 | accepted `[P00]`, ready `[P01]` | accepted `[]`, ready `[P00]` |
| run-8 | accepted `[]`, ready `[P00]` | accepted `[P00]`, ready `[P01]` |

The bound review stands: the evaluator leaves `plan_digest` out of the review subject by design.

## The check that would have caught it

`check-lexicon.py` now also reads the plan `CURRENT.md` selects, the way the plan gate selects it.
Every path that plan assigns to a node or to the integrator must lie in its concept's home
(`D-20260926-d8e48f`). AGENTS.md §5 says so.

- **The 16:36 plan.** Pointed at it, the check names both paths.
- **The 14:04 plan.** The check passes over 108 planned paths.
- **Self-test.** It plants a path outside its home, paths inside it or with no slug, an empty
  plan, no plan, and a reader over fake files. Reverting the rule fails it.

## Next

V1's first slice: profile, storage, journal and identity, used here from the worktree and tested.

Nothing here is pushed.
