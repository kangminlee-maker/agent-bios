---
created_at: 2026-09-29T07:39:08+09:00
head: 9f2cfc0
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-703c89, D-20260929-34e9ab, D-20260929-639ccf, D-20260929-dfe0e3, D-20260929-a97ae7
---

# V1, fifth slice, fourth increment: the unconfirmed start (record)

This records the fourth increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md),
built to the [06:49 unconfirmed-start design](2026-09-29T0649--9f2cfc0--v1-slice5-unconfirmed-start-design.md).
It lands in the commit that carries this record. V1 is not complete, and no node is accepted by
this work. No person has used the entry on a real host yet; that is the slice's real use, still
ahead. The owner decided on 2026-09-29 that the real use prepares its binding and sources with a
workbench script, and that no command is added for them (`D-20260929-34e9ab`).

## What landed

### The product

- **`workenv/roles.py`.**
  - The activation's checks are one function, `activating`.
  - Two more answers to `session.routing.activate`:
    - `session_routing_dispatched`: refused as the activation is; otherwise `unknown`, with
      `outcome_unknown`, recovery by query or retry of the same request, local effect
      `private_state_written` and provider effect `unknown`, returning nothing.
    - `session_routing_unreported`: `expired`, with `delivery_unobserved`, recovery
      `new_governed_request` and provider effect `dispatched`.
- **`workenv/hosts/start.py`.**
  - `seal` makes a request, and `answered` takes an answer to use in place of the operation's
    entry.
  - The start renders from the preparation, then writes the launch into
    `launches/<activation request id>/`, locks its `waiting` file, and only then hands the
    activation on. The job carries the activation's request and payload.
  - `waiting`, `settle` and `release` are the lock and the settling.
  - A refused hand-over removes the launch directory and releases the lock.
- **`workenv/hosts/hook.py`.** `new` asks the start's activation again first:
  - one still unknown activates;
  - one already settled stays, and the hook goes on;
  - a refusal records nothing more and says so.
- **`workenv/commands.py`.**
  - The host runs as the program's child, and `start` exits with the host's status (128 + N
    for a signal).
  - While the host runs, the program catches SIGINT and SIGQUIT and does nothing with them.
  - After the host exits, `start` settles an unreported start and says so in one line, then
    releases the lock.
  - The check of an unknown start settles it where nothing waits on it any more, and its result
    says so.
- **`docs/recovery.md`** says what `start` does while and after the host runs.

### The driver

- **The serving table.** `session.routing.activate` names
  `reply_lost: workenv.roles:session_routing_dispatched`. The serving check holds such an entry
  to its node's owned paths.
- **`executor.Routing.lost`** holds the in-scope `reply_lost` entries.
- **`features/event_reply_lost.py`** answers the event's step through that entry. It is
  `blocked` by name where no code in scope names one, or where the driver gives the step.

### The drafts (workbench `v1-slice5/`, for the P01 re-freeze)

- **`restate.py` gains one named edit, `member`.** TUI-ENTRY-UNKNOWN's `start_preparation` now
  names its unit's member, `AGENTS.md`, as FOCUS, KO-STATE and OPTIONS name it for the same
  shape.
- **Why the edit was needed.** With the lost reply written, the case first ran and failed there,
  at `compose_start`, before any step this increment changed.

## Where it departs from the 06:49 design

1. **A refused confirmation settles the start as refused.**
   - The design said the activation would stay unknown until the parent settled it. But the
     journal keeps a refused answer to a pending request in its place.
   - So a confirmation refused on a moved checkout answers the activation `refused`, and the
     parent has nothing left to settle.
   - The design was corrected the same day, and `D-20260929-639ccf` says so.
2. **A refused hand-over also removes its launch directory.** Only a launch whose activation the
   journal holds unknown is kept. A refused hand-over is held as `refused`, not unknown, so it
   is not kept.

## How it was checked

### Unit tests

| File | Tests | New here |
| --- | --- | --- |
| `test_roles.py` | 20 | the dispatched answer and its refusals; the unreported answer; resubmission while unknown |
| `test_start.py` | 32 | the hand-over and its lock; a refused hand-over; settling, and what it leaves; the hook's confirmation in three outcomes |
| `test_commands.py` | 33 | the not-reported line; a reporting session; the check that settles; the host as a child |
| `test_executor.py` | 90 | the lost reply rerouted, blocked by name, in the profile routing; every V1 case and every lost-reply scenario |
| `test_cases.py` | 81 | a `reply_lost` entry outside its node's paths |

- **What the child-process tests run.** They start a real child process. It reports what it
  saw, then sends SIGINT and SIGQUIT to the test process, or kills itself.
- **What they check:**
  - the host gets the launch's environment;
  - the host starts with default signal handling;
  - the program survives the signals;
  - the program's handlers are restored;
  - a signal death reads 128 + N.
- **`check-workenv.py`'s ruff** (line length 100) found one test line too long; it was
  re-wrapped.

### Mutation sweeps (workbench `v1-slice5/`)

- **`mutate5e.py`** (this increment): 40 of 40 caught (`mutate5e.txt`). One mutation is listed
  as equivalent: a descriptor not closed on a refused start, whose directory is removed with
  it.
- **`mutate5d.py`** (3b): 58 of 58 (`mutate5d-inc4.txt`), after one anchor moved with the new
  `execute`.
- **`mutate5c.py`** (3a): 22 of 22.
- **`mutate5b.py`** (increment 2): 87 of 87.

### Cases

- **The V1 cases with drafts** (`runv1-inc4.txt`): 19 passed, 3 failed.
  - The only change from `runv1-3b.txt`: TUI-ENTRY-UNKNOWN moved from `blocked` to `passed`.
    All 15 of its steps pass: the activation answered unknown by the dispatched answer, history,
    the reopened entry, the query, and the refused resubmission.
  - The three failures are the ones the P01 re-freeze list already names: DEL-PERSONAL,
    N15-C11-POS and CMP-QUALIFIED.
- **Against the scripted owner,** every V1 case passes.
  - Of the five scenarios that lose a reply, N15-C11-NEG and TUI-ENTRY-UNKNOWN pass.
  - N17-C09-NEG, N19-TRANSFER-POS and TUI-ENTRY-SHARED-UNKNOWN are blocked on the `processes`
    and `partitions` features.

### A pseudo-terminal smoke run (`smoke5e.py`, `smoke5e.txt`)

- **Setup.** A fake Claude Code qualified by a real probe, then replaced by a script that stands
  for a session that never reports. Everything ran in its own HOME, state root and PATH.
- **The six runs:**

  | Run | What happened | Exit |
  | --- | --- | --- |
  | 1 | The host exits 5; the line saying the start is recorded as not reported | 5 |
  | 2 | Ctrl-C while the host runs: the host traps it and exits 9, and the program settles | 9 |
  | 3 | No unknown start is shown, and the start runs at once | 5 |
  | 4 | The program is killed (SIGKILL) while its host runs; the start stays `unknown` | – |
  | 5 | The entry shows `Last start: result unknown`. Enter checks it, and the check draws `Not checked · the session never reported…`; the start is `expired` | 130 |
  | 6 | No unknown start is shown | 130 |

- **A harness fault, not a product one.** The first attempt gave the pseudo-terminal no size,
  so the entry drew nothing. The key-driven runs were unaffected. The harness now sets 100×30.

## Open

- **The check's label for a start it settled** reads `확인하지 못함` / `Not checked`, followed by
  the reason. The model draws an answer as `unknown` or `unavailable`. Opening the entry again
  shows the start settled.
- **An orphaned host.** A parent killed while its host runs frees the lock.
  - A check can then settle the activation while that host still runs.
  - Its later report finds the activation settled, and the hook records the link-bound
    activation as it does now (tested).
- **F-19** (FINDINGS.md): a session started with no Instructions body loses its `new` delivery
  record.
- **Two activations per session start remain:** the start's, for no link, and the hook's, for
  the session's link.
- **From increment 3, still open:**
  - the probe line and command output are English;
  - no probe has run with the permission flags.
- **Next.**
  - The real use on both hosts, with a new state root and a workbench script for binding and
    sources.
  - Then the P01 re-freeze and V1 acceptance.
