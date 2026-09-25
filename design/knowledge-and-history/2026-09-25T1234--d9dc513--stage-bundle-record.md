---
created_at: 2026-09-25T12:34:00+09:00
head: d9dc513
kind: design
status: stage-bundle-published-p00-re-recorded-p01-stale-no-stage-implemented
plan: 2026-09-25T1232--d9dc513--development-plan.json
supersedes: 2026-09-24T0616--9b26d79--successor-bundle-record.md
decisions: D-20260925-f59493, D-20260925-ebd7b8, D-20260925-88be89, D-20260925-192296
---

# The stage bundle: the plan is a chain of stages, and the evaluator admits it

The [10:48 stage-plan design](2026-09-25T1048--556dce2--stage-plan-design.md) recast the
component-ordered graph as stages that each end in something a user can use on this machine, and
listed five steps to a usable V1. This record publishes the first two as one bundle, because the
regression helper names nodes and cannot be published ahead of the plan it names:

1. the evaluator successor, with its chain rules, its regression suite and their controls;
2. the successor catalog, plan and spec, and the case registry regrouped by stage.

Nothing here implements anything. No stage is built, no host or runner is qualified, and every
claim the evaluator tracks is false. The next steps are the driver V1's cases need, V1 itself
(implemented, used here, tested), P01's re-freeze once V1's cases are fixed, and V1's acceptance.

## What moved

| Member | From | To |
| --- | --- | --- |
| Plan | `2026-09-24T0740--a0e289e--development-plan.json` | `2026-09-25T1232--d9dc513--development-plan.json` |
| Test catalog | `2026-09-24T0553--9b26d79--test-catalog.json` | `2026-09-25T1232--d9dc513--test-catalog.json` |
| Development spec | `2026-09-24T0740--a0e289e--development-spec.md` | `2026-09-25T1232--d9dc513--development-spec.md` |
| Static plan checker | `2026-09-22T0900--c1915b2--check-development-plan.py` | `2026-09-25T1232--d9dc513--check-development-plan.py` |
| Bound acceptance regressions | `2026-09-22T0900--c1915b2--acceptance-tests.py` | `2026-09-25T1232--d9dc513--acceptance-tests.py` |
| Mutation sweep | `2026-09-22T0900--c1915b2--mutation-sweep.py` | `2026-09-25T1232--d9dc513--mutation-sweep.py` |
| Design SSOT | unchanged | `2026-09-24T0553--9b26d79--consolidated-design-ssot.md` |

Every new member is its predecessor copied and changed by content-addressed edits — each anchor
must match exactly once and every edit must apply — so the diff against the predecessor is the
change and nothing else. The regrouped `gates/workenv/case-index.json`,
`gates/workenv/conformance/serving.json` and `gates/workenv/subjects.json`, and the changes to
`gates/workenv/cases.py`, its schema, `gates/workenv/conformance/driver.py` and their tests, land in
the same commit. The generators, the placement of every case with its reason, and the
measurements below are preserved outside the repository in
`~/.local/share/agent-bios-workbench/team-env-20260920/stage-bundle-20260925/` with a
`SHA256SUMS`.

## The stages

| Stage | What a user can do when it ends | Cases it adds | Families it adds | Claim |
| --- | --- | --- | --- | --- |
| V1 | Start a session in this repository with an environment fitted to it | 22 | N01 N04 N05 N09 N15 N16 N27 | `personal-start` |
| V2 | Decisions carry forward, and a conflict is asked in the working CLI | 25 | N07 N08 N23 | `decision-continuity` |
| V3 | The knowledge that applies is read when it is needed | 5 | N06 | `knowledge-use` |
| V4 | Lock, sign-out, unlock and key rotation | 10 | N02 N03 | `local-protection` |
| V5 | Found, enrol, publish, adopt and exchange Teams, with no GitHub | 32 | N10 N11 N12 N13 N14 N22 | `team-sharing` |
| V6 | What a session learned becomes an accepted source, with its provenance | 19 | N28 | `learning-intake` |
| V7 | An optional GitHub carrier and provider sign-in | 11 | N17 N18 | `optional-connections` |
| V8 | Operational completeness, backup and restore included | 25 | N19 N20 N21 | `complete-operations` |
| PK | An immutable candidate package, installed here | 4 | N24 | `package-readiness` |
| V9 | The whole real-use test on the installed candidate | 5 | — | `real-use-verified` |

R0 keeps its 4 cases and `runner-qualified`; P00 and P01 are unchanged. The 162 required cases are
all placed, each exactly once. A stage's profile holds its own cases and every earlier stage's,
so V8 runs 149 and V9 158; PK runs its own 4. Every claim is terminal, and the V1–V4 claims are
independent of the Team and external facets. `local-backup-restore` is part of
`complete-operations`, and `integrated-target` is `real-use-verified`.

A case is placed at the stage whose code first makes it usable: by default the earliest profile
that selected it in the component graph, mapped to that node's stage, with an override where the
case's assertion belongs to another stage. Every case carries its reason in the preserved
`placement.json`. A stage's done_when items are its own usable check and direct-use record plus
the completion clauses of the component nodes it absorbed, each carried with its old covering
cases, trimmed to what the stage holds. The spec's "Where the component work went" table maps
every old node to the stages that own its work now.

## The chain rules

The 09:00 evaluator forbade two nodes from owning overlapping paths and required every accepted
record's subjects to equal the current measurement. A stage extends files an earlier stage wrote,
so both rules would make every stage invalidate the ones before it. The successor keeps both and
adds a chain (`D-20260925-12e0e3`, refined by `D-20260925-f59493`):

- **Ownership.** Two nodes may own overlapping paths only when one transitively depends on the
  other **and the later one can re-establish the earlier**: its families, required atomic cases,
  bootstrap cases and subjects include the earlier node's. Anything else is refused by name. P01's
  bootstrap cases belong to the freeze, so no later node can co-own the freeze's paths.
- **Currency.** A node whose record measured every subject, and some of whose subjects have moved,
  stays current while an accepted, itself-current node that depends on it covers it: that node's
  bound case map holds every case of the earlier one, bound to the same family, and its subjects
  include the earlier one's. This is computed as a greatest fixpoint, so a discharger whose own
  subjects moved discharges nothing unless something later covers it in turn. Each discharge is
  disclosed in the result as `discharged: {node: [dischargers]}`.
- **Dispatch.** A node is not ready while another node owning an overlapping path has an unresolved
  attempt.

The regression suite adds the chain's controls: shared paths on one dependency path admitted;
a moved stage discharged by a later accepted one; a moved later stage named as no discharger; an
edit with no covering record stale; a later stage lacking a case, binding it to another family or
omitting a subject refused as a discharger; a sibling that covers without depending refused; an
unaccepted later stage and an unmeasured record refused; other errors kept; the wait on another
owner; a discharge in the middle of a chain. The gate went from 28 positive and
412 negative controls to 32 and 438. The mutation sweep adds 18 named reverts of the
chain rules and re-points the overlap revert at the new check; all 96 named reverts are
caught by the control each one names.

## The registry, regrouped (`D-20260925-ebd7b8`)

- **Selection.** A stage's `selects` row lists only the cases it introduces. `cases.case_map` runs
  every case an implementation or package node in a stage's scope selected again at that stage,
  and the catalog lists the atomic cases cumulatively, because the evaluator reads the catalog
  alone. The conformance driver resolves a profile's cases through `case_map`, so it cannot run a
  set the binding does not name.
- **Joined cases.** Each stage from V2 on joins its predecessor's first introduced case; V1 has no
  implementing predecessor and says so. A joined case must be one the stage binds.
- **Runtime rules.** A rule is checked where its case is bound at a profile whose node, or a node
  it depends on, implements the rule's contract. A later stage is never asked to restate an
  earlier stage's contracts.
- **Serving.** Each operation is served by the stage that first implements it. The journal layer
  arrives with V1 and the admission layer with V4. There is one place, V1's store.
- **`given`.** Every row dissolved: a stage's scope holds every stage before it, so no step a
  bound case uses is served outside it.
- **Subjects.** `component:V1` to `component:V8` measure the paths each stage owns;
  `full-runtime` reaches PK.

Two revert controls were run before this was believed: restoring the old implementer check fails
the new scope test by name, and removing the inheritance fails the driver, binding and coverage
tests by name.

## Where this departs from the 10:48 design (`D-20260925-88be89`)

| The design said | The bundle does | Why |
| --- | --- | --- |
| Family entry per the table (N04 at V4, N05 at V5, N23 at V1, N22 at V8) | N04 and N05 enter at V1, N23 at V2, N22 at V5 | A family enters where its first case becomes usable; the cases decided it |
| V4 locks every open session, bridge and handle | V4 claims sessions and handles; the Studio bridge and its assets are V8 | The bridge is advanced Studio, which V8 builds; V4 cannot lock what does not exist yet |
| Ownership: one node depends on the other | Also: the later owner re-establishes the earlier | Without it a later node could rewrite a freeze's paths without running its cases |
| Currency: the later profile holds every earlier case | Also: same family, subjects included, the discharger itself current | A case id alone can be rebound to another family, and a moved discharger re-established nothing |
| The three component verification nodes carry clauses | Their generic clauses are dropped; V9 carries the integrated node's | They said "run this profile", which cumulative profiles now do |

## The spec successor

39 content-addressed edits to the 07:40 spec. The heading list and the first line are unchanged,
and no component node id survives outside the delimited "Where the component work went" table.
The S11 reading is restored: a row with no clause behind it stands under its own header, which
requires "a truthful unsupported state and implementation acceptance, not an inert success
button"; the 07:40 spec had dropped "implementation acceptance". The SSOT needed no edit.

## P00 re-recorded; P01 stale until its re-freeze (`D-20260925-192296`)

The run evidence is `~/.local/share/agent-bios-workbench/team-env-20260920/run-6/`, a copy of
`run-5/` in which exactly one field moved: `records.P00.plan_digest`, to `a2fd2b050d8ca366…`.
`run-5/` is untouched. Under the stage plan `digest(records[P00]) = 6768ccceb8e3817619fa3aaba870cfc4caa3d9eea7999b3cb2cd1e034da50d01`. P01 is not
re-recorded: its frozen artifact carries the component graph's 25 profiles, and it is re-frozen
over the regrouped registry once V1's cases are fixed.

| Plan | Run | Accepted | Ready |
| --- | --- | --- | --- |
| 07:40 | `run-5` | P00, P01 | P02, P03, R0 |
| stage | `run-5` | — (P00 `stale plan/node`) | P00 |
| stage | `run-6` | P00 | P01 |
| 07:40 | `run-6` | — (P00 `stale plan/node`) | P00 |

The second and fourth rows are the known-opposite controls: the untouched run is stale under the
new plan, and the re-recorded run is stale under the old one, so the digest binds both ways.

## Not done

- **No independent read of this bundle yet.** The cross-provider reviewer is out of credit until
  2026-09-29. Until then this bundle rests on its own gates and the controls above; a blind read
  of the plan and spec against the 10:48 design is owed, and a defect it finds is fixed in a dated
  successor.
- **The V1 command surface** is decided when V1 starts, as the 10:48 design says.
- **Every binding moved.** The regrouped registry changes every profile's binding, which
  `gates/workenv/binding-drift.py` discloses against the run evidence; that is what P01's re-freeze
  settles.
