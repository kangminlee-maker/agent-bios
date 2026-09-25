---
created_at: 2026-09-25T10:48:40+09:00
head: 556dce2
kind: design
plan: 2026-09-24T0740--a0e289e--development-plan.json
decisions: D-20260925-814291, D-20260925-f52ccc, D-20260925-b19fcb, D-20260925-12e0e3
---

# Stage plan: every stage ends in something a user can use on this machine

The owner set the goal: real-use testing on this machine that finds no problem, and
deployment after that. Work proceeds in small steps that are implemented, used directly and
then verified (`D-20260925-814291`). For that to hold at every step, each stage of the plan has
to end in a feature a user can use (`D-20260925-f52ccc`).

The 07:40 graph does not meet that. It is ordered by component: identity, storage, knowledge,
memory, preparation, Team and the rest. No stage before M1 gives anyone anything to use. The
SSOT asks for the other shape already. S12 says "implementation can proceed in vertical slices.
Prefer one complete useful path over many independent screens", and its first acceptance group
is "Personal start → permitted sources/preparation → actual recipient with no Team or signup".

This record designs the stage plan. The successor plan, catalog, spec and evaluator are derived
from it.

## The stages

Each stage is one plan node. Every stage depends on the one before it. "Families" lists the case
families a stage adds; its acceptance runs these together with every earlier stage's cases.

| Stage | What a user can do when it ends | Direct check on this machine | Families added | U | W | C |
| --- | --- | --- | --- | --- | --- | --- |
| **V1** | Start a Claude or Codex session in this repository with an environment fitted to it: a local profile made at first use, with no signup or Team; repository Instructions, then personal ones, then supplied ones, composed in that order; and a record of what the session actually received | In this checkout: see the profile and the sources and their order, prepare, launch a real session, then read what reached it | N01 N09 N15 N16 N23 N27 | U01 U03 U04 U11 U19 U20 | W01 W02 W09 | C01 C03 C04 C07 C11 C12 |
| **V2** | Decision memory. Record a decision with its context, alternatives, reasons and premises. A later session, or another model, reads the decisions that apply in this repository and continues from them. Two conflicting decisions produce a question to the user inside the working CLI, and the answer is kept or asked again as chosen | Record two decisions that conflict, start a new session, get asked in the CLI, answer, restart, see the choice hold | N07 N08 | U07 U08 U09 | W04 | C05 C06 |
| **V3** | Domain knowledge. Add repository or personal knowledge with where it applies and its revisions; a session reads the knowledge that applies when it needs it | Add a knowledge item with a condition, revise it, and see a session read the right revision | N06 | U05 | W03 | C04 C06 |
| **V4** | Protection. Lock or sign out, and every open session, bridge and handle loses access to protected material; unlock with the device key; rotate the key and remain the same person | Lock while a session is open, try the old handle, unlock, rotate the key | N02 N03 N04 | U19 | — | C01 C02 |
| **V5** | Teams. Found a Team, enrol a second device or person, publish an environment and adopt it, and exchange it by package or peer with no GitHub. The repository > personal > Team order is complete | Two local profiles on this Mac found, enrol, publish, adopt and exchange | N05 N10 N11 N12 N13 N14 | U02 U12 U13 U15 U17 U18 | W05 W06 W07 W08 | C08 C09 C10 |
| **V6** | Learning intake. What a session learned becomes a typed candidate, is validated, and is accepted into its destination with its provenance | Capture from a real session, validate, accept, and see it applied | N28 | U21 | W10 | C05 |
| **V7** | Optional connections: a GitHub carrier, and Google, Slack or OIDC sign-in | Connect a real repository and one provider; disconnect both | N17 N18 | U16 | — | C09 C12 |
| **V8** | Operational completeness: corrections, retention and deletion, backup and recovery, search, bulk operations, advanced Studio and authoring, and the Team lifecycle | Back up and restore after deleting local state; archive and restore a Team; do bulk edits | N19 N20 N21 N22 | U06 U10 U14 | W10 | C03 C08 C10 C12 |
| **PK** | An immutable candidate package, installed on this machine | Install the candidate here | N24 | — | — | — |
| **V9** | The whole real-use test on this machine finds no problem. Deployment is the next action and is not part of this node | Every stage's check, end to end, on the installed candidate | all | — | — | — |

A requirement a later stage extends stays listed where it first becomes usable; V5, for
example, also completes U20's Team position. P00, the baseline, and P01, the contracts, stay as
they are. R0, the runner qualification, stays too, because it is what unattended dispatch
needs.

The acceptance claims become one per stage: `personal-start` (V1), `decision-continuity` (V2),
`knowledge-use` (V3), `local-protection` (V4), `team-sharing` (V5), `learning-intake` (V6),
`optional-connections` (V7) and `complete-operations` (V8). Of these, `local-backup-restore`
moves into V8. `package-readiness` belongs to PK, `real-use-verified` is terminal at V9, and
`runner-qualified` stays with R0.

## What a stage's acceptance is

- **Cumulative cases.** A stage's profile holds its own families plus every earlier stage's
  families, with the cases the registry binds to them. A stage cannot be accepted while an
  earlier stage's case fails at the current revision.
- **A direct-use record.** The check in the table is performed on this machine and written down
  in a dated record with what was run and what was seen. It is evidence alongside the cases,
  not a substitute for them.
- **Once per stage** (`D-20260925-b19fcb`). The evaluator's record and one cross-provider bound
  review come at the end of the stage. Inside a stage, the loop is implement, use, test.

## The evaluator successor (`D-20260925-12e0e3`)

The 09:00 evaluator was written for a graph of independent components. Two of its rules forbid
stages:

- "Two nodes may not own overlapping paths."
- Every accepted record's subjects must equal the current measurement.

A stage necessarily extends a file an earlier stage made. For example, the access owner V1
creates is the one V4 locks. The successor keeps both rules and adds one relation, a **chain**:

1. **Ownership.** Two nodes may own overlapping paths only when one transitively depends on the
   other. Nodes on one dependency path cannot write concurrently, so the race the rule prevents
   cannot happen between them.
2. **Currency.** An accepted node whose tested subject has moved still counts as current when a
   later node in its chain is accepted at the current revision **and** that node's profile holds
   every case of the earlier node's profile. The later record re-established the earlier
   guarantees on the bytes that exist now. Without such a record, the earlier node is stale, as
   today.

Everything else carries over unchanged: bindings, predecessor digests, review binding and runner
qualification. The successor is a new dated file with its own regression suite, and each new
rule gets a planted violation that must fail by name. The first is a stage that edits an earlier
stage's file with no later accepted record covering it.

## What carries over, and what changes

| Artifact | Fate |
| --- | --- |
| Contracts C01–C12 (P01) | Unchanged. The data model does not depend on the order it is built in |
| 162 scenarios and 100 registry cases | Unchanged bytes. Cases are regrouped by stage profile, and each stage's profile is cumulative |
| Serving table | `node` becomes the stage that first implements the operation; the journal layer arrives with V1 and the admission layer with V4 |
| Registry `given` rows and later bindings | Re-derived under the stage scopes; most dissolve, because a stage's scope holds every earlier stage |
| Catalog | Successor with one profile per stage, plus PK, V9, P00, P01 and R0 |
| Plan | Successor: nodes V1–V8, PK and V9 replace P02–P19, M1–M4, P17 and P18; P00, P01 and R0 remain |
| Spec | Successor: the stage order, and the S11 header reading restored ("implementation acceptance", the M2 finding) |
| P00 / P01 records | P00 is re-recorded minimally. P01 is re-frozen once, over the regrouped registry, when V1's driver needs are in |

## The work to reach a usable V1

1. The evaluator successor, with its chain rules, regression suite and controls.
2. The successor catalog, plan and spec, and the registry regrouped by stage.
3. The driver: the executor core and the features V1's cases use, grown with V1.
4. V1 itself: implemented, used here, tested. P01 is re-frozen when V1's case set is fixed.
5. V1's acceptance: record, cross-provider review (not before 2026-09-29), and the direct-use
   record.

## Open

- **The V1 command surface.** The spec gives the CLI to a client node. In the stage plan, V1 owns
  a minimal command set, and later stages extend it. Its spelling is decided when V1 starts.
- **Where V1's cases need no world features.** A V1 case that uses faults or processes is either
  moved to the stage that makes those features meaningful (V5 or V8) or kept with the feature
  built early. This is decided when the registry is regrouped, one case at a time, with a
  disclosure.
