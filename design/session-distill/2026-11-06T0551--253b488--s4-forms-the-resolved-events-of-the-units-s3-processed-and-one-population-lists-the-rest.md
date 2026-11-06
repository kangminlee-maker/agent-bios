---
created_at: 2026-11-06T05:51:00+09:00
head: 253b488
kind: design
supersedes: null
---

# S4 forms the resolved events of the units S3 processed, and one population lists the rest

WP-09, commit 2. It decides which events S4 forms from (lead decisions D2 and the first half of D1 of WP-09 stage 0;
D-20261106-335d60). It adds the code check that every listed event is placed exactly once, and the population: design
§9's set as an explicit document.

## The subject: what S4 forms from

`stage_form.subject(run_dir)` reads S3's stores through S3's own readers:
- `read-results.json`;
- each unit's `read/<unit>.json`;
- `current_events` and `stored_claims` of every file the unit read;
- `evidence.load`.

S3's readers refuse an edited claim or event store by name.

**Which events are formed.** For a unit S3 processed (`read_complete`), S4 forms every event whose current outcome is
`resolved`, by its stored id. These are:
- an event its window resolved;
- an event the stitch joined to a later claim;
- an event an earlier run left pending that this run's stitch resolved. That event keeps its earlier id. Its line
  carries no claim of this run that describes it, only the stitch's outcome claims, and its description is S3's
  generic one for a carried event.

**Events handed on.** An event the unit hands on (`unresolved`, so coverage's next pending event) is listed as
`carried_forward` with its unit. It is formed by the run that resolves it. Forming it now would count it twice across
runs: S3 resolves it later under the same id. In C1's 0708c window, 4 of 8 events were handed on.

**Units not formed.** A unit S3 did not process (`read_partial`, `deferred`, `failed`) is listed as `not_formed`, with:
- its status;
- the reasons from its read record;
- the number of its events.

None of its events is formed. S3 credited nothing of such a unit, so the next run reads it again. This is the first half
of D1. The second half, the barrier that refuses a missing, running, partial or stale S3, lands with the CLI in
commit 5.

**Refusals.** The subject is refused by name in four cases:

| Code | When |
|---|---|
| SET_MISMATCH | a processed unit holds open an event its result does not hand on, or hands on one it does not hold open |
| SET_MISMATCH | a processed unit's resolved carried events are not its result's `resolved_events` |
| SET_MISMATCH | two units hold the same event id |
| RECORD_INTEGRITY | a claim cites evidence that no store of its unit holds |

Each event row carries:
- `session`: the unit, which is the lineage root, so a child's events count with its root;
- `claim_ids`: what describes it;
- `outcome_claim_ids`: S3's `stitched_from`.

## The partition, in the stage's check

`answer_problems` now counts where each listed event is placed:
- in a candidate's `event_ids`;
- in a rejected finding's `event_ids`;
- as a non-finding.

It refuses by name:
- `SET_MISMATCH events placed nowhere: [...]`;
- `SET_MISMATCH events placed more than once: {...}`.

A retry's correction therefore names the labels, as the rest of the check does.

## The population

`population(answer, subject, run_id, intake)` builds the population from the resolved answer.

| Part | What it holds |
|---|---|
| `candidates` | the formed candidates, with stored ids `sid("k", run, label)`, and the lifecycle intake (commit 4), each `{candidate_id, source, event_ids}`; a lifecycle candidate has no events of the window |
| `rejected_findings` | each with its failed requirements |
| `non_findings` | each with its reason |
| `event_membership` | every event of the subject: the candidate id, or the class name for the other two |
| `carried_forward` | the events handed on |
| `not_formed` | the units S3 did not process |
| `counts` | events, members per class, non-findings by reason, candidates by source, carried forward, units by status, and events not formed |

Lifecycle candidates are told apart by their id, not their entry. The intake gives each one an id of its own, so two
candidates from one entry are two rows. An example is a legacy candidate and a redundancy candidate of the same
`ledger_incubating` unit (lead, D5 scope).

`population_problems` refuses by name (SET_MISMATCH):
- a lifecycle candidate the intake holds and the population does not;
- a membership naming a candidate the population does not list;
- an event of the subject that is missing, not the subject's, or placed twice;
- a membership or count that disagrees with the subject;
- a candidate id listed twice.

`partition_rows` gives `partition.jsonl`, one row per event: `{event_id, class, candidate_id | finding_id | reason}`.

## The fixture

`fx_s3` runs S3 itself over S2's golden corpus with S3's golden host. No model is called. It takes 2-3 seconds.

- **The Claude unit** (session and child) is processed. It holds:
  - an event its window resolves;
  - an event the stitch joins;
  - an event no claim resolves, which is handed on;
  - the planted `pe-1`, resolved by the stitch;
  - one event in the child.
- **The Codex unit's** stitch is answered with a join it may not make, twice. So the unit ends `read_partial`, with its
  one event pending.

The subject is therefore four events, one carried forward, and one unit not formed.

## Controls

`stage_form.py --self-test` now holds 55 controls (18 new). The pretrial (`work/impl/wp09/logs/pt9-2.log`) ran 12 rows:
- the none row: PASS;
- 11 rows that each revert one check: every one CAUGHT by name, with traceback False.
