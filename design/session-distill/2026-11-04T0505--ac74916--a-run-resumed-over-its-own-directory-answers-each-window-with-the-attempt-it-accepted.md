---
created_at: 2026-11-04T05:05:00+09:00
head: ac74916
kind: design
supersedes: 2026-11-04T0232--fedc526--s3-judges-the-observations-the-pinned-ledger-holds-due-and-records-resolutions-it-can-derive-again.md
---

# A run resumed over its own directory answers each window with the attempt it accepted

WP-08 commit 5a makes S3 resumable (plan WP-08 done-when 7). The lead split commit 5 into 5a (Q1 to Q5,
resumability) and 5b (Q6, concurrency) and answered each question on 2026-11-04. Each section names what the code
now does and the controls that hold it.

This record supersedes one point of the commit 4b record: `observations/<window>.jsonl` was appended through the
claim stores' writer. It is now replaced whole, through a temporary file and a rename (`records.write_text`),
because its lines carry the basis of the stage's end judgement over the whole scope, which a resumed run may revise.
Everything else in the 4b record stands.

## The defect closed

Before 5a, running S3 a second time over the same run directory raised nothing and doubled the stores:

| | first run | second run |
| --- | --- | --- |
| calls | 12 | 24 |
| claim lines | 11 | 22 |
| expansion decisions | 4 | 8 |
| evidence records | 11 | 11 |

Evidence stayed at 11 because `evidence.append` already skipped an evidence id it held. The doubled stores
surfaced only when read: `stored_lines` refused with CLAIM_IMMUTABLE. The probe that measured this is a
development tool outside the repository (`work/impl/wp08/c5/probe-rerun-2.py`). After 5a, the same probe reports
the same counts after both runs, and both stores read clean.

## Q1: an accepted attempt answers its item again, through dispatch

`Supervisor.item(..., resume=True)` first asks `Supervisor.reusable`. That function looks at the item's earlier
attempts, latest first. An attempt is reused only when all of these hold:

1. `gate.accepted(call_dir, judged=<the stage judges>)` accepts it. This is the one read of acceptance, so an
   attempt whose recorded stage check failed is never reused (STAGE_CHECK_FAILED).
2. Its `call.json` matches the new call on four fields: `payload_sha256`, `seat`, `schema_sha256` and
   `max_output_tokens`.
3. The stage's check, asked again, still holds of it.

Each attempt that is not reused is named in the item's `not_reused`. The names are REUSE_NOT_ACCEPTED,
REUSE_PAYLOAD_CHANGED, REUSE_SEAT_CHANGED, REUSE_SCHEMA_CHANGED, REUSE_CAP_CHANGED and REUSE_JUDGE_FAILED. A reused
item returns `reused: <call id>`, and nothing is dispatched for it.

`payload_sha256` is new in `call.json` and is declared in gate's closed `CALL_SCHEMA` as optional. It is the hash of
the payload the item was asked with, taken before any retry's correction. Both attempts of one item therefore carry
the same value, and a changed packet is told apart from a retry.

S3 asks every window, expansion and stitch call with `resume=True`. Its read records carry `reused` and
`not_reused` on each window row, and the summary counts `reused`. The dispatcher's per-call reads of the
declaration (seat, allowance, budget, stop) are unchanged, as agreed.

Controls in `dispatch --self-test`:

- `resume-reuses-the-accepted-attempt-made-for-this-call-and-dispatches-nothing`
- `resume-does-not-reuse-when-the-{payload,seat,schema,output-cap}-changed-and-names-it`: four controls, one per field
- `resume-does-not-reuse-an-attempt-the-stage-check-no-longer-holds-of`
- `resume-never-reuses-an-attempt-its-recorded-stage-check-failed`
- `resume-never-reuses-an-attempt-no-stage-check-judged-when-the-stage-judges`
- `resume-dispatches-a-new-attempt-when-none-is-reusable-and-says-why`

Decision: D-20261104-33ce25. It closes an S3-only call journal.

## Q2: each store holds each record once

- **Claims and events.** `stage_read.append_lines` skips a line already in the store, compared by digest. A row
  whose identity the store holds with other content is refused before anything of the batch is written. Claims use
  CLAIM_IMMUTABLE, keyed by `claim_id`. Events use EVENT_IMMUTABLE, keyed by `(event_id, phase)`. An event has one
  `read` line and one `stitch` line per stitch outcome. A carried event's line counts as a stitch line.
- **Expansion decisions.** `views.record_decision` skips the same decision line made again. When the same call
  decides the same omission otherwise, it is refused (EXPANSION_DECISION_CONFLICT). A decision by another call is
  another line, as before.
- **Evidence and expansion windows.** These were already idempotent. `evidence.append` keeps one record per
  evidence id, and the expansion windows are whole-file writes named by call and omission.
- **Observation instances.** Replaced whole, as stated at the top of this record.

Controls:

- `stage_read --self-test`:
  - `5a Q2: S3 run twice over one run directory leaves every store byte for byte as the first run left it and
    dispatches no call, each window answered again by the attempt it accepted`. Its subject set must include claims,
    events, evidence, observations, the expansion decisions and the expanded windows.
  - `5a Q2: a claim kept again under its id with other content - another call's - is refused where it would be
    written, and no store changes`
  - `5a Q2: an event kept again under its id with other content is refused where it would be written, and no store
    changes`
  - `5a Q2: a second judgement of a window's instances replaces the first whole, and reads back as its own`
- `views --self-test`: three `5a:` controls for a decision made again, the same call deciding otherwise, and another
  call's decision.

## Q3: a dead run's open reservation is closed as interrupted

S3's lock is held when `stage_read.run` starts. Any S3 reservation still open at that point belongs to a dead run.
`Supervisor.interrupted(stage)` closes each one with outcome `interrupted`, charged as follows:

| What the call left | What is charged |
| --- | --- |
| Never dispatched | Nothing (`unspent`) |
| The dispatcher's `usage.json` | Its measured totals |
| The host's own finished report | That report's measured total (`host_reported`) |
| Nothing measured | The reserved amount, as provisional spend (`reserved`) |

The host's own finished report is one of two things:

- Claude's closing `result` event in `capture/stream.jsonl`, summing its `modelUsage`.
- codex-run's `capture/usage.json` (CodexCaptureUsage/v1), only when every request in it is measured. One that holds
  an unresolved request is charged the reservation instead.

A host-reported charge is not reconciled per request, so it is recorded as `complete: false`. An interrupted call is
never a calibration sample, because `charge` takes samples only from `completed` calls.

Once its runner is stopped or gone, the interrupted call's cell (its temporary home) is removed. The transcripts the
cell holds are first kept in the call's capture, as a settled call's are. Only a directory under this supervisor's
cell root with the call's own prefix is ever removed.

Controls in `dispatch --self-test`:

- `interrupted-closes-a-reservation-never-dispatched-unspent`. It also requires the closed set to be exactly the
  planted open reservations.
- `interrupted-charges-a-dispatched-call-its-reserved-amount-when-nothing-was-measured`
- `interrupted-charges-what-the-call-directory-measured`
- `interrupted-charges-what-a-finished-claude-host-reported-in-its-capture`. The reported total must equal the live
  call's measured total.
- `interrupted-charges-what-a-finished-codex-capture-measured-and-only-when-all-of-it-is-measured`
- `an-interrupted-call-is-never-a-calibration-sample`

The S3 kill-and-resume control (Q5) closes its killed call at the reserved amount and removes its cell.

Decision: D-20261104-21b261. It closes charging zero and leaving the reservation open.

## Q4: an orphaned host is stopped only by the identity recorded at its start

Right after `Popen`, the dispatcher records the runner's `{pid, start, pgid}` in the reservation
(`dispatch.runner_identity`, one `ps` listing) and writes the ledger.

At resume, `stop.stop_recorded(identity)` signals only when a fresh listing shows all of these:

- the recorded pid;
- the recorded start time;
- the recorded process group;
- the pid leading that group, as every runner does under `start_new_session`.

It then SIGKILLs the group's members, each only while its own listed start time holds, and verifies the kill. It
returns one of these outcomes:

| Outcome | Meaning |
| --- | --- |
| `stopped` | The runner was found and killed, and the kill was verified |
| `gone` | No such pid is listed |
| `identity_mismatch` | Some part of the identity differs; it is named and nothing is signalled |
| `survivors` | Members of the group outlived the kill |
| `unverified` | There is no listing, or the identity was recorded in part; nothing is signalled |

`interrupted` refuses the resume with RESUME_HOST_UNVERIFIED, before closing anything, when a runner is `survivors`
or `unverified`. In both cases the host may still be spending, and a new call beside it would spend twice. This is
my reading of the lead's condition, and it is distinct from the closed RESUME_HOST_ALIVE. A host that is alive and
verified is stopped, never refused. A reservation marked dispatched with no runner recorded died before its runner
started, so it is not a refusal.

Safety, per the lead's three conditions:

1. Nothing is signalled unless pid, start time and group all match.
2. Every control targets processes its own suite started:
   - `stop.py` launches three fixture trees. The another-start-time case uses a second fixture tree started 1.2 s
     later, because `ps` lists start times to the second.
   - The gone case uses pid and group 2**30+7, which no system issues. A reverted check therefore has nothing it
     could signal, even though the stopped runner's own pid may already be another program's.
   - `dispatch.py` plants identities of three fixture sleepers; the reused-pid case is a live fixture pid with another
     fixture's start time.
   - The S3 kill test's only target is the golden host its own child started.
   - The S3 suite never signals a host the resume failed to stop. The golden host ends by itself after 120 s, and the
     leftover check names it.
3. No control can reach a real Claude or Codex process. Every runner in these suites is `dispatch.FAKE_HOST`.

Controls:

- `stop --self-test`:
  - `stop_recorded: the runner recorded, at its pid with its start time and group, is stopped with its group`
  - `... a runner no longer listed is named gone`
  - `... another start time at its pid is named and nothing is signalled`
  - `... another process group ...`
  - `... a process listed in another group than the one recorded ...`. Its recorded group is its own pid, so it reads
    as leading that group; only the listed group differs.
  - `... a member that does not lead its group ...`
  - `... an identity recorded in part is unverified and nothing is signalled`
  - `... the fixture runners have distinct start times`
- `dispatch --self-test`:
  - `interrupted-stops-the-runner-a-dead-run-left-alive-by-its-recorded-pid-start-and-group`
  - `interrupted-names-a-runner-listed-with-another-identity-and-signals-nothing`
  - `interrupted-refuses-the-resume-while-a-runner-it-cannot-verify-may-still-run`
  - `the-fixture-processes-of-the-identity-controls-have-distinct-start-times`

What stays outside the guarantee: a host process that leaves its group (setsid and a double fork) is not in the
recorded group, as `stop.py` already states for the cap stop.

Decision: D-20261104-efa3ec. It closes RESUME_HOST_ALIVE and leaving the host running.

## Q5: the kill-and-resume test

`stage_read --self-test` runs these steps:

1. Read one golden run in one go. Every omission is expanded, the 4b observations are judged, and a pending event
   is on each window's claim, so every store has lines.
2. Make a second run with the same name ("k") in another root.
3. Pick the middle window of the one-go run's window calls, taken in reservation order. Its plan row gets `hold`:
   the golden host's first call of that row writes its call id to a marker file and sleeps.
4. Run `stage_read.py --fixture-driver RUN_DIR ROOT PLAN` as a child (`-I`). This is declared in dispatch
   `SCRIPT_RUNS`.
5. Wait for the marker, then SIGKILL the child, and only the child. The host it started lives on in its own session,
   which is the orphan Q4 is about.
6. Resume in-process with a new fixture supervisor over the same directory.

Controls:

- `5a Q5: the driver was killed while its host held the middle window, and the host it started outlived it`
- `5a Q3/Q4: the resumed run stops the orphaned host by its recorded identity, charges the dead call its reservation
  and removes its cell`
- `5a Q5: the resumed run's stores are the one-go run's but for the call id of the window it read again, and it made
  the one-go run's calls and the killed attempt`

  The comparison renames the re-dispatched window's call id (`-a2` to `-a1`) in lines and in file names. The
  expanded windows' file names carry their call id, and that file name was the only other difference found. It also
  requires the unrenamed stores to differ, so the rename is doing something. The resumed run must have reused at
  least one window. Its calls must be the one-go run's plus the killed attempt (13 against 12 in the golden run).
- `5a Q5: nothing this suite started outlives it - its driver, the host the driver left - nor its temporary tree`

## Not in 5a

Q6, concurrency, is commit 5b. It covers:

- jobs=1 and jobs=12 giving byte-identical stores apart from time fields;
- the shared files, merged in a fixed order or written under a lock.

The read records (`read/<unit>.json`) are the run's account of itself, not a store. A resumed run's records say
which windows were reused, so they are not compared byte for byte.
