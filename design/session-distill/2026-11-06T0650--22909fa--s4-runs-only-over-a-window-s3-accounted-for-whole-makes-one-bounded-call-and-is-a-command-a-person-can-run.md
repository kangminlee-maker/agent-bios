---
created_at: 2026-11-06T06:50:00+09:00
head: 22909fa
kind: design
supersedes: null
---

# S4 runs only over a window S3 accounted for whole, makes one bounded call, and is a command a person can run

WP-09, commit 5 (plan WP-09 done-when 5; the Goal's `distill.py form`). This record covers:
- `stage_form.run`, `barrier`, `form_budget`, `supervisor` and `report_lines` in `session-distill/runlib/stage_form.py`;
- the `form` command of `session-distill/distill.py`;
- the follow-up reader of `runlib/lifecycle_intake.py` (`window_occasions`);
- one `SCRIPT_RUNS` row in `runlib/dispatch.py`;
- one `READER_EXCEPTIONS` row in `runlib/census.py`: `INPUTS` names `census.json` as S4's S1 input, as `views.run` and
  `stage_read.run` name it for theirs. The barrier reads the census itself through `census.load` and `census.rows`.

The lead decisions it carries out, all from WP-09 stage 0:

| Decision | What it settles |
|---|---|
| D1 (M1 (b)) | the barrier: what blocks S4 and what is only listed |
| D7 | lifecycle candidates are formed by code and never sent to the model |
| D9 | the output cap of 32k and a by-name refusal for a packet over its bound |

X round 1 (rework, four major findings) reported on commits 1 to 4 while this commit was written. Its fixes are
commit 6: carried-forward events from earlier runs (F1), G candidates from a placed cluster alone (F2), the origin of a
resolved carried event (F3) and the population's set accounting (F4). This commit calls `subject` and
`population_problems` as they stand, so its golden run holds what those functions hold today and no more.

## The barrier (done-when 5, D1)

The plan says S4 refuses while an eligible session's S3 record is missing or partial, except sessions the census marked
`deferred`. The census never marks `deferred`: S3's `read-results.json` does. So the source moves from the census to
S3's results, with the same intent.

S4 is refused, by name, when:
- a unit the census made eligible has no result in `read-results.json` (`INPUT_PARTIAL S3 <unit>`);
- a result's status is not terminal (`INPUT_PARTIAL S3 <unit>`);
- a result names a unit the census did not make eligible, or two results name one unit (`SET_MISMATCH`);
- the results are of another window than the census (`INPUT_INVALID`);
- S3's record is running, partial or stale. This is checked where S4 is admitted (`records.run_stage`:
  `INPUT_PARTIAL S3`, `INPUT_STALE`), before any record of S4 is written.

A terminal unit S3 did not process (`read_partial`, `deferred`, `failed`) blocks nothing. It is listed in the
population as `not_formed`, and none of its events is formed (`subject`, commit 2). In C1 one unit of three ended
`read_partial`; with 4 to 12 units in a window, blocking on it would stop almost every run.

## What S4 reads

S4 declares five inputs. Each is pinned at admission to the record of the stage that produced it:

| Input | Producer |
|---|---|
| `read-results.json` | S3 |
| `read.json` | S3 |
| `observations/resolutions.json` | S3 |
| `census.json` | S1 |
| `inventory/current.json` | S2 (the inventory part) |

S3's event, claim and evidence stores are not inputs. They are read through S3's own readers, which refuse an edited
line by name.

The window's occasions for each due decision are now read through `stage_read.stored_resolutions`. That reader
believes an instance only when its line is the one S3 recorded, and a resolution only when the instances derive it
again (`INSTANCE_IMMUTABLE`, `RESOLUTION_DRIFT`). Commit 4 read the two files directly. Its reading matched the
writer's shape (`{resolutions: {<id>: {resolution, basis, counts}}}`), but it checked nothing. A follow-up of another
window is refused (`INPUT_INVALID`).

The lifecycle intake is built from the declaration S4 was admitted against (`records.StageRun.declaration`), never
from a read of `run.json`.

## The bound (D9)

A formation call carries no view window, so the dispatcher does not bound it. S4 bounds it itself:

- The packet's driver bytes are measured as the dispatcher measures them (`bound.driver_bytes`, the packet and the
  schema), under the call id of a retry.
- They may take at most `bound.INPUT_BOUND` less the host's measured hermetic allowance, less the room a retry's
  correction takes (`stage_read.CORRECTION_ROOM`, 4,096). This is rule (a) of the window bound, owned by
  `runlib/bound.py`. Each token covers at least one byte, so bytes bound tokens.
- The allowance is a host's, measured per host version and profile in `seats.json`, so the S4 seat's host is read.
  For Claude 2.1.317 it is 3,795, and the bound is 112,109 bytes.
- Over the bound: `FORM_OVER_BOUND`, naming the bytes and the counts of events, claims and quotes. Formation is one
  call over the window and is not sharded, so the answer is a smaller window.
- Check (d), the seat's context capacity, is not made. The S4 seat's capacity is unmeasured. The first live call
  records it from the host's report (D9).

A consequence to know before C2: C2-pre estimated S4 at 43 to 88k input tokens. At about two bytes per token, the upper
end is 160 to 180 KB of driver bytes, which this bound refuses. The dry run measures the chosen window's packet before
any call.

The output cap is 32,000 (`OUTPUT_CAP`). It is the module's constant, not a declared value. The declaration's
`output_caps` holds S3's cap, which S2 cuts its windows against, and changing it invalidates every stage from S2
(`declare.INVALIDATED_FROM`). Only S4 reads S4's cap.

## The call

- One item, `form`, of case `form`, through `Supervisor.item` with `view_window` false.
- The stage's check is `answer_problems` (commit 1). An attempt it fails is retried once with the failure lines.
- It runs in a calibration tranche. It is one call, so its class runs at concurrency one, measured before or not.
- `resume` is on. A run of S4 again over the same run reuses the accepted attempt, and leaves the same population
  bytes.
- An outcome other than accepted leaves `form.json` with the outcome and its codes, and S4's record `partial`.
- A subject with no event makes no call. The population then holds the lifecycle intake alone.

## What S4 leaves

| File | What it holds |
|---|---|
| `intake.json` | the lifecycle intake (commit 4) |
| `candidates.json` | the formed candidates under stored ids (`k-...`, with the answer's label), each with its events and sessions; the lifecycle candidates, each by its intake row; the rejected findings (`r-...`) |
| `partition.jsonl` | one row per event of the subject: its class and its candidate, finding or reason |
| `population.json` | design §9's population (commit 2) |
| `form.json` | the packet's measure, the subject's and the intake's counts, the call's outcome, the population's counts |

The driver prints counts, bytes and codes only, never a claim, a quote or a lesson.

## Dry

`form --dry` stops before the call and needs no supervisor. It writes `intake.json`, the packet (`form/packet.md`) and
its measure (`form/dry.json`: driver bytes, the bound, at most how many input tokens, the output cap, the label
counts). S4's record is left `partial`, since nothing was formed, so a later stage refuses it (`INPUT_PARTIAL S4`).

The packet holds the window's claims and quotes. That is the same content a call directory holds, and it stays in the
run directory.

D5 asks for the redundancy pair count before any live call. The dry run's intake counts are that count.

## The command

```
distill.py form --run-id ID --dry [--index ROWS.json]
distill.py form --run-id ID --cells DIR [--golden-plan PLAN.json] [--index ROWS.json]
```

- Live, the pinned runner. Its token reaches claude-run only as `CLAUDE_RUN_TOKEN_FILE`, a path never read here. When
  it is unset, the command is refused (`TOKEN_FILE_UNSET`) before the cell root or any record is made.
- With `--golden-plan`, realization golden: dispatch's golden host answers from the plan and starts no model. The
  dispatcher refuses that runner under any other realization (`RUNNER_REALIZATION_MISMATCH`).
- `--index` takes the occasion index's rows (WP-21's interface; golden until it lands).

S4's self-test runs the command as a process over golden runs it made: dry, then with a golden plan. So the parser,
the handler and the stage behind them are held as a person runs them. The run reaches `lifecycle_intake.build` with
the admitted declaration. `runlib/dispatch.py` `SCRIPT_RUNS` declares that child.

## Controls added

In `stage_form.py --self-test`, over the golden S3 run of commit 2 (its checkout now pins the intake's case ledger, its
due incubates expiring the day before the window, and S2's inventory part leaves the intake's library):
- the barrier passes the golden window; a missing unit and a non-terminal result are `INPUT_PARTIAL` naming the unit;
  an extra or a repeated result is `SET_MISMATCH`;
- an S3 record that is partial stops S4 at admission, and no record of S4 is written;
- S3 results that hold no result for an eligible unit, recorded by S3's record as its own, stop S4 through `run`
  (`INPUT_PARTIAL` naming the unit) before the intake is written;
- an instance line added to S3's follow-up after S3 is `INSTANCE_IMMUTABLE`;
- dry: the record is partial, with exactly its three outputs, and no call is made; a stage reading S4 refuses it;
- `FORM_OVER_BOUND` refuses a packet over a narrowed bound, and the record is failed; the bound equals rule (a) less
  the correction room; no measured allowance is `ALLOWANCE_UNMEASURED`;
- no supervisor is `FORM_UNSUPERVISED`;
- golden: the call is accepted and the record complete with every output; the intake holds two due decisions (one a
  pending intervention on a placed entry), two legacy entries, one redundancy pair and one G cluster; the population
  lists every intake id and the formed candidate; the partition places each event once;
- golden again: the accepted attempt is reused and the population bytes are the same;
- the command as a process: dry, then golden.

In `distill.py --self-test`: `form` without `--dry` or `--cells`, `--dry` with `--cells`, and a live run with no token
are each refused by name before anything is made.

## Not covered

- The live supervisor is held only to its refusal. Past it, the pinned runner starts a model, which no control may do.
- No control runs S4 over a subject with no event. The golden corpus always yields events.
