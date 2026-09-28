---
created_at: 2026-09-28T12:47:35+09:00
head: da67fd2
kind: design
supersedes: 2026-09-28T0708--6c4f2c1--v1-slice4-hook-delivery-design.md
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260928-fad6ef, D-20260928-7c45ce
---

# V1, fourth slice, third increment: the environment goes in at launch; hooks record, and deliver only mid-session

This replaces the delivery mechanism of the
[07:08 design](2026-09-28T0708--6c4f2c1--v1-slice4-hook-delivery-design.md), where a hook printed
the bodies at every event. The measurements behind the change are in the
[09:30 record](2026-09-28T0930--d107ec0--v1-slice4-delivery-channels-record.md): a hook caps what
it hands over, and the launch channels do not.

These of the 07:08 design's decisions still stand:

- V1's own start launches the session (`D-20260928-30d875`).
- Children follow the rule that dispatched them (`D-20260928-4a1cc3`): tier seats receive the
  environment, a review child receives none of it.
- A rehydrated session keeps what it had (`D-20260928-3249ff`). It now keeps it because the host
  does, not because the hook hands the bodies again.
- The shipped guide's `fork_turns: none` rule for review children (`D-20260928-7d8bbb`).

`D-20260928-cc0692` (Codex hooks uncapped) no longer applies to any launch route. See
"Mid-session" below.

## One method on both hosts (`D-20260928-fad6ef`, `D-20260928-7c45ce`)

| Recipient | How the environment reaches it | Claude Code 2.1.283 | Codex 0.157.1 |
| --- | --- | --- | --- |
| `new` | at launch, as the main session's instructions | `--append-system-prompt-file <env>` | `-c developer_instructions=<native + env>` |
| `rehydrated` | the host keeps the launch instructions through compaction (measured on both) | nothing to hand | nothing to hand |
| `child`, a tier seat | at launch, in that tier's session-scoped definition | `--agents <file>`: the tier's definition (prompt, model, effort) + env | `-c agents.<tier>.description/config_file`: a generated role, the tier's role + env |
| `child`, review or other | nothing reaches it | the appended system prompt stays in the main session | the role's own instructions replace the session's. A generated `default` role, carrying the person's native instructions only, covers role-less children |
| `current`, mid-session | the `UserPromptSubmit` hook prints it | up to 10,000 characters | up to Codex's default, about 2,500 tokens |

Measured on this machine on 2026-09-28; the tools and outputs are in the workbench's
`team-env-20260920/v1-slice4-use/`:

- **Claude Code** (`context-size/`: `e1.sh`–`e6_compact.py`, `evlog.sh`): its `SubagentStart`
  input carries `agent_type` and `agent_id`.
- **Codex** (`manual/`: `subagent_input.py`, `codex_launch_channels.py`):
  - its `SubagentStart` input carries `agent_type` (`default` when no role is given) and
    `agent_id`, but not how the child was forked;
  - a role's `developer_instructions` replaced the session's in `reviewer`, `workhorse` and a
    defined `default` child;
  - a generated `workhorse` role carried the environment to its child alone;
  - the session's `developer_instructions` stayed through compaction: a turn's prompt was
    24,555 tokens before and 24,790 after.

The hosts differ only in the argument names, which each adapter declares as data. The owner
composes, activates and records the same way for both.

**Native instructions are preserved.**

- Claude Code's appended system prompt adds to the person's own; nothing replaces them.
- Codex's `developer_instructions` replaces the configured value for the session. The start
  therefore reads the effective native value (the app server's configuration read, as
  `compose/instructions_session.py` already does) and puts it first.
- The `default` role carries that native value alone.
- A tier definition is the one the host would have loaded: the person's installed definition
  where there is one, otherwise the shipped one (`claude/agents/`, `codex/agents/`). Its model and
  effort are carried over, since a session-scoped definition takes precedence over installed ones
  (measured on Claude Code; Codex's per-run role is the same shape).

## The start (`workenv/hosts/start.py`)

It is called by slice five's entrances, and by this increment's driver and direct-use run. In
order:

1. **Compose and activate for no link.** Composing and activating the preparation for no link is
   allowed ("recorded for nobody") and returns every delivered body's bytes.
2. **Render the environment.** One text holds the usage contract, the guide pointer, and each
   delivered body under a header with its unit, source and digest. The same text goes to the main
   session and into each tier definition.
3. **Write the launch files.** They go in a private directory for this launch under the state
   root:
   - the environment text;
   - Claude Code's agents file, or Codex's generated role files;
   - the hook job: state root, actor, host name and the version read from the binary, the
     preparation request, the delivered body digests, and the tier and review kinds.
4. **Return the host's arguments and environment** for the entrance to run:
   - the adapter's launch arguments;
   - the hooks, as the same groups in the same places as now (Codex trusts them by place);
   - `AGENT_BIOS_HOOK_JOB`.

## The hook: it records, and prints only mid-session

A host session's id exists only once the host reports it, and on Codex the start cannot choose
it. So the link, and the records that name it, are made at the host's own events. The same holds
on both hosts:

| Event | What the hook does | Prints |
| --- | --- | --- |
| `SessionStart` startup | Opens the link for the reported session id, then composes the job's request for it. Only if the composed bodies are exactly the ones handed at launch does it activate the preparation and record an attempt for `new` naming those bodies. If they differ (the checkout moved in the seconds between), it records nothing and says so on standard error. | nothing |
| `SessionStart` compact | Records an attempt for `rehydrated` naming the bodies of the preparation the session was activated with. That the host kept them is what the `rehydrated` probe qualifies. | nothing |
| `SubagentStart` | For a tier kind (`agent_type`, reported by both hosts), records an attempt for `child` naming the definition's bodies, under a use id minted for that child. For any other kind it records nothing. | nothing |
| `UserPromptSubmit` | Delivers a preparation composed for this link that has not reached the session: prints its bodies and records an attempt for `current`. With none, it is silent. It fires more than once a turn (it also fired as child results returned), so a delivery is made once. | only then |

`received` for a launch-channel recipient states that the adapter handed exactly those bodies to
the host, through the channel its probe qualified, for a recipient the host then reported. It
still does not state that a model read or followed them (C07).

**Mid-session.** A delivery above the host's hook limit is not handed in part. The hook prints a
short notice that the environment changed and that a new session receives it whole, and records
no attempt. Keeping each host's default limit is uniform, and it needs no new review of a Codex
hook. Raising Codex's limit would still leave Claude Code at 10,000 characters.

## Probes: each route is qualified through its own channel

The support rule is unchanged: a route is supported only where the adapter declares it and the
latest real probe on that host name and version worked. What a probe drives follows the channel:

| Recipient | Probe |
| --- | --- |
| `new` | launch with the handed code in the launch instructions; ask |
| `rehydrated` | the same launch; one turn; compact; ask |
| `child` | launch with the handed code in a tier definition only; ask the main session to start a child of that tier and relay its answer |
| `current` | the `UserPromptSubmit` hook prints the handed code, as now |

The probes of `new`, `rehydrated` and `child` on both hosts are therefore run again.

## The entrance

`workenv/hosts/hook.py` now writes kept state through the owner. Its row in
`gates/workenv/entrances.jsonl` becomes `routed` through `projection_owner`, with
`root_origin: caller`, since the job names the state root. That is the shape of
`compose/canary.sh`'s `session_start` row. `start.py` is a library the entrances call, not an
entrance of its own.

## Checks

1. **Fake hosts.** `gates/workenv/units/v1/fakehost.py` learns the launch arguments:
   - Claude Code's `--append-system-prompt-file` and `--agents`;
   - Codex's `-c developer_instructions` and `-c agents.*`.

   It then answers from them as the real hosts do: the main session from its launch text, a tier
   child from its definition, a review or role-less child from neither. Its compaction keeps the
   launch text and drops hook output.
2. **Unit tests for each event's record.** They cover:
   - a startup whose bodies moved;
   - a child of each kind;
   - a mid-session delivery made once;
   - a mid-session delivery over the limit;
   - a refused owner answer that leaves the host running.
3. **A mutation sweep**, run to the end before any commit.
4. **The real run** on both hosts, through the start: one prompt, one tier child and one review
   child, one compaction and one prompt after it. It reads the host's own record against the
   owner's observations, and ends in a dated direct-use record.
