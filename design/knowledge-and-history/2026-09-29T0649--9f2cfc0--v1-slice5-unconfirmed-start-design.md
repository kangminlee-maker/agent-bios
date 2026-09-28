---
created_at: 2026-09-29T06:49:08+09:00
head: 9f2cfc0
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-703c89, D-20260926-421d82, D-20260929-639ccf, D-20260929-dfe0e3, D-20260929-a97ae7
---

# V1, fifth slice, fourth increment: the unconfirmed start

This is the fourth increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md).
It makes a start whose session never confirmed it a state the product can reach, and it writes the
driver feature that TUI-ENTRY-UNKNOWN's draft waits on (`event_reply_lost`, deferred to this slice
by `D-20260926-421d82`).

## Where it stands at `9f2cfc0`

- **The start commits its activation at once.**
  - `start.start` composes, then asks `session.routing.activate`, which commits before the host
    runs.
  - When the session reports that it began (the hook's `new`), the hook composes for the
    session's link and makes a second, link-bound activation.
  - So no start is ever unknown. The entry's unknown start and its check are reached only by
    tests that plant an unknown answer.
- **The start replaces itself with the host.** `commands.execute` calls `execve`, so nothing is
  left to notice that a session ended without reporting.
- **The driver has no lost reply.** TUI-ENTRY-UNKNOWN is blocked on `event_reply_lost`.
  - Four more cases lose a reply, each on another operation:
    - `recipient.delivery.attempt` (N15-C11-NEG);
    - `carrier.provision` (N17-C09-NEG);
    - `team.profile.set` (N19-TRANSFER-POS, TUI-ENTRY-SHARED-UNKNOWN).
  - None of these is in V1's scope.

## The owner's decision (2026-09-29, `D-20260929-703c89`)

- The start stays the parent of the host it launches and waits for it to exit.
- A start whose session never reported by then is recorded as not reported, so it does not block
  the next start.
- Only a start whose parent was itself interrupted stays unknown, for the entry to check.

## Design

### 1. The start dispatches its activation, and the session confirms it

- **The start dispatches.** The start asks `session.routing.activate` through a new inner,
  `roles.session_routing_dispatched`, in place of the activation itself:
  - It refuses what the activation refuses, by the same checks.
  - Otherwise it answers `unknown`:
    - gap `outcome_unknown`;
    - recovery `query_same_request` and `retry_same_request`;
    - local effect `private_state_written`, provider effect `unknown`;
    - nothing returned and nothing committed.
  - This is the frozen answer of TUI-ENTRY-UNKNOWN's `activate_session` step, field for field.
- **Rendering moves before the dispatch.** The dispatch returns no bodies, so the start renders
  the environment from the preparation it composed:
  - each delivered body read from its revision's bundle, as the activation reads it;
  - the usage contract from `roles.usage_contract()`.
- **Nothing that can fail runs after the dispatch.** Rendering, the host's configuration and every
  launch file are written first. So an unknown activation always has a launch that holds it.
- **The launch directory** is `launches/<activation request id>/` under the state root. It holds:
  - the environment and the tier definitions, as now;
  - the job, which now also carries the activation's sealed request and payload;
  - a file, `waiting`, that the start's process locks (`flock`, exclusive) for as long as it waits
    on the host. The lock is taken before the dispatch, so no one sees the activation unknown
    with no process waiting.
- **The session confirms.** The hook's `new` first asks the activation again under its own id,
  with the activation itself:
  - An activation still unknown commits: the journal hands a pending request on again.
  - One already settled answers what it was settled with. The hook goes on either way, because
    the session did begin.
  - A refusal (the checkout moved between start and report) records nothing more and says so on
    standard error, as the hook's other refusals do. The journal keeps a refused answer to a
    pending request in its place, so the activation is settled as refused, and the parent has
    nothing left to settle.
  - Then the hook opens the link, composes for it, activates and attempts, as it does now.

### 2. The parent waits, and settles what was never reported

- **The host runs as a child.** `commands.begin` runs it with `subprocess`, not `execve`.
- **While it waits,** the parent catches SIGINT and SIGQUIT with handlers that do nothing:
  - Ctrl-C reaches the host through the terminal, and does not end the parent.
  - A caught signal is reset to its default across `exec`, so the host starts with its own
    handling.
  - SIGHUP, SIGTERM and SIGKILL are left as they are, so closing the terminal ends the parent.
    That is the interrupted parent of the owner's decision.
- **After the host exits,** the parent asks the activation again under its own id, through
  `roles.session_routing_unreported`, only where the journal still holds it unknown:
  - stage `expired`, gap `delivery_unobserved`;
  - recovery `new_governed_request`;
  - local effect `private_state_written`, provider effect `dispatched`.
  - The command says so in one line, naming the request.
- **Then** it releases the lock and exits with the host's status (128 + N for a signal).
- **Why `expired` and `delivery_unobserved`:**
  - `expired`: the window in which the session could have confirmed it has ended.
  - The other stages that end a request name something that did not happen here:
    - `rejected`, `withdrawn` and `changes_requested` are a reviewer's or a requester's acts;
    - `stale` and `conflict` name a moved base;
    - `blocked` waits on something that can still come.
  - `delivery_unobserved` is C07's gap for "a delivery that was requested and not observed".
  - Provider effect `dispatched`: the host was handed the environment at launch, and nothing
    observed whether it arrived.
- **The effect on the entry.** An expired start is not pending, so the entry holds no draft for
  it and starts again.

### 3. An interrupted parent leaves the start for the entry to check

- **The entry shows it.** An activation whose parent died stays unknown. The entry shows it as
  its draft and focuses the check, as the frozen case states.
- **The check dispatches one `operation.query`** for that request, as the frozen case states.
- **The terminal's dispatcher answers it.**
  - If the query answers the activation still unknown, and no process waits on its launch (the
    lock is free), the start settles it as not reported, as in 2.
  - The check's result then says so: `unavailable`, with the reason that the session never
    reported and the entry opens again to start.
  - Where a process still waits, because a session started from another terminal is running,
    the check stays `unknown`.
- **The model is unchanged.** It dispatches one query, and the driver's run of the frozen case
  sees only that. The settling is the start's, done by whichever process finds that nothing waits
  any more: the parent at exit, or the terminal that checks.

### 4. The driver's lost reply

- **Each operation names its own seam.** An operation row of the serving table may name
  `reply_lost`: the entry in the code under test that answers the operation while the reply it
  handed on is outstanding.
  - `session.routing.activate` names `workenv.roles:session_routing_dispatched`.
  - The serving check holds that entry to its node's owned paths, like the row's own entry.
- **`executor.Routing` gains `lost`:** the operations whose `reply_lost` a node in scope names.
- **The feature `event_reply_lost`.**
  - For each `reply_lost` event, it answers the named step through that entry, in place of the
    operation's own.
  - No reply follows, so the answer stands, and later steps see what the owner holds.
  - A step whose operation names no such entry in scope, or that no code in scope serves, is
    `blocked` by name: the driver cannot lose the reply of its own given answer.
- **Why the operation row, not an `events` row.** The five cases lose replies on four operations.
  - An `events` row names one entry per event kind, so that entry would have to choose by
    operation inside the product.
  - A table of product entries in the driver would put the product's seams on the judge's side.

## Checks

- **Unit tests.**
  - The dispatched and unreported answers, field for field, and their refusals.
  - The start: nothing activated, the job holding the activation, the lock held.
  - The hook: it confirms a pending activation, goes on past a settled one, and records nothing
    on a refused one.
  - The parent: settles an unreported start and says so; leaves a confirmed one; exits with the
    host's status; a caught signal does not end it.
  - The check: settles only where the lock is free.
  - The driver: the feature reroutes the step, is blocked by name without a seam, and the
    serving check refuses a seam outside its node's paths.
- **The V1 cases (`runv1.py`).** TUI-ENTRY-UNKNOWN's draft is expected to run, and the other
  cases to stay as they were.
- **A mutation sweep** over the new rules.
- **The full hook.**

## Open

- **The check's label for a start it settled** reads `확인하지 못함 · <reason>`, because the model
  draws an answer as `unknown` or `unavailable`. Opening the entry again shows the start settled.
- **An orphaned host.** A parent killed while its host runs frees the lock. A check can then
  settle the activation while that host is still running. The host's later report finds it
  settled, and the hook records its link-bound activation as now.
- **Two activations per session start remain:** the start's, for no link, and the hook's, for the
  session's link.
