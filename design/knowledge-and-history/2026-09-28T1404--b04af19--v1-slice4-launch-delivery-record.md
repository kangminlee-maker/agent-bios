---
created_at: 2026-09-28T14:04:08+09:00
head: b04af19
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260928-bf66d1, D-20260928-5b8737, D-20260928-251417
---

# V1, fourth slice, third increment: sessions start in the environment on both hosts

This implements the [12:47 design](2026-09-28T1247--da67fd2--v1-slice4-launch-delivery-design.md):
the environment goes in when the host starts, and the hook records what reached the session at the
host's own events. It was checked with unit tests, with real probes of every route on both
installed hosts, and with a real session on each host started through the new start. The direct
use found one leak on Codex, which is fixed and re-run. V1 is not complete and no node is accepted
by it.

## What was written

Three commits, each through the commit hook.

- **`7498d73`: a probe qualifies only the carrier it drove** (`D-20260928-bf66d1`).
  - Each adapter route names its carrier: `launch` for `new` and `rehydrated`, `definition` for
    `child`, `hook` for `current`. The table is the same on both hosts; only the arguments
    differ (`Adapter.launch`).
  - A probe hands its code through the route's carrier and states that carrier's wire
    (`launch_instructions`, `session_definition` or `command_hook`, version 1).
    `capability.probe` refuses a wire the route does not take.
  - Qualification requires the latest real probe to be through the route's current wire. The hook
    probes kept before this change no longer qualify `new`, `rehydrated` or `child`.
  - Claude Code's `rehydrated` probe is now one stream-json process (a turn, `/compact`, the
    question), because launch instructions belong to a process.
  - Codex `-c` strings are now TOML basic strings, so any text survives as itself.
- **`08762ab`: the start and the recording hook** (`D-20260928-5b8737`).
  - `workenv/hosts/start.py` composes the request for no link and activates the session with it
    ("recorded for nobody"). It then renders the usage contract and each delivered body, and
    returns what an entrance runs:
    - the launch instructions, with the person's own first where Codex replaces them;
    - a session definition for each tier;
    - the hooks;
    - the job file the hook reads.
  - The start refuses to launch where no probe qualified `new`. Where `child` is not qualified,
    it leaves every kind as the host would load it.
  - A tier's definition is the one the host would have loaded: the project's, then the person's,
    then the shipped one. Only its instructions are extended, so the read-only fences survive:
    `disallowedTools` and `tools` on Claude Code, `sandbox_mode` on Codex.
  - `workenv/hosts/hook.py` records through the owner:
    - At startup it opens the link, composes for it, and activates and records `new` only if the
      bodies are the ones handed at launch.
    - At compaction it records `rehydrated`.
    - For a tier child it records `child`.
    - Mid-session it prints a newer preparation's bodies once and records `current`. Where they
      exceed the host's hook limit (10,000 characters on Claude Code, 2,500 bytes on Codex), it
      prints a one-time notice instead and records nothing.
  - The hook's entrance row is now routed through the projection owner.
- **`b04af19`: the leak the direct use found** (`D-20260928-251417`). See the Codex section below.

## How it was checked

- **Unit tests.**
  - `test_start.py` (20 tests) runs the start, the adapters, `hook.py` and the owner against
    `fakehost.py`. Two of its tests run a whole session on each fake host.
  - `test_probes.py` (38 tests) and `test_hosts.py` (27 tests) cover the carriers and wires.
  - The fake hosts answer as the real hosts were measured to:
    - A session answers from its launch text, which compaction keeps.
    - A child answers from its kind's definition.
    - A Codex child of a role with blank instructions takes the session's instructions.
  - `nolaunch` and `forget` modes are the negative controls: the host ignores launch arguments,
    or drops them at compaction.
  - `WORKENV OK` at `b04af19`.
- **Mutation sweeps, run to the end before each commit.** Each mutation was put in the code, the
  named test file was run, and the code was restored.
  - 3a: 11 mutations, all caught. Two were missed on the first run; that led to two new tests.
  - 3b: 21 mutations, all caught. Two redundant checks in the mid-session path hid each other;
    one was removed and a test for a recomposition with unchanged bodies was added.
  - The fix: five mutations. The four in the start were all caught; reverting the fix makes the
    end-to-end Codex test reproduce the leak. The fifth changed the fake host's own rule. It is
    not observable while the start is correct, because the start then writes no blank role; the
    fake's rule is what makes the reverted fix fail.
- **The V1 cases on the real driver:** 12 passed, 8 failed, 2 blocked. The one new failure is
  `N15-C11-POS`. Its frozen probe steps state `command_hook` for the `child` route, which no
  longer qualifies it. The P01 re-freeze restates them, with the other delivery probe steps
  already listed there. The other seven failures and two blocks are the ones the
  [19:44 handoff](2026-09-27T1944--d80365f--handoff.md) lists.

## Real probes (step 5)

`capability.probe` ran for real, through the journal, on Claude Code 2.1.283 and Codex 0.157.1 on
this machine. The state root is a new one, set up with two real guides as personal Instructions.

| Host | `new` (launch) | `rehydrated` (launch) | `child` (definition) | `current` (hook) |
| --- | --- | --- | --- | --- |
| Claude Code 2.1.283 | worked | worked | worked | worked |
| Codex 0.157.1 | worked | worked | worked | worked |

Codex still ran the adapter's hooks: all three hooks in the adapter's places are enabled and
trusted, as before the change of string encoding. Every route is supported on both hosts.

## Direct use through the start (step 6)

On each host, the start composed and activated the environment: two bodies, 30,551 characters,
three times Claude Code's hook limit. The host was launched with what the start returned, reading
the person's own settings, in this repository's checkout. One session ran five steps. Each prompt
asked for the body digests the session's agent-bios work environment names; only the launch text
or a tier's definition carries them.

| Step | Claude Code | Codex (after the fix) |
| --- | --- | --- |
| Prompt | both digests | both digests |
| Tier child (`workhorse`) | both digests | both digests |
| Child outside the tiers | `NONE` (`general-purpose`) | `NONE` (no role; started as `default`) |
| Compaction | the transcript holds a compaction boundary | the rollout holds a compaction |
| Prompt after compaction | both digests | both digests |

**The owner's record agrees with the host's own.** On each host the owner recorded, in order:

1. the session activated;
2. `new` received;
3. `child` received, one child under a use id of its own;
4. `rehydrated` received.

`delivery.observe` answers `activated` for the session and `delivered` for the child, each with
both bodies in its inventory.

- Claude Code's transcripts name two subagents, `workhorse` and `general-purpose`, so the child
  outside the tiers was not recorded.
- Codex's rollouts name a `workhorse` child holding the environment and a `default` child that
  does not hold it.

**The Codex leak and its fix.** In the first run, the child Codex started with no role answered
with both digests. Its rollout shows `agent_role` null, and its first developer message is the
environment. It did not come from copied turns: the child was spawned with `fork_turns` `none`.

The start had defined the `default` role with the person's own developer instructions. This person
has none, so the role's instructions were empty. The same day, one child each, it was measured
what Codex does with each kind of `default` role:

| The session-defined `default` role | `agent_role` | The environment in the child |
| --- | --- | --- |
| developer instructions empty, as the start first wrote it (with and without `features.multi_agent`) | null | yes |
| a single space | null | yes |
| no `developer_instructions` key | `default` | yes |
| one sentence | `default` | no |

Codex applies no role whose instructions are blank, and a role without them leaves its child the
session's instructions. The start now gives `default`, and every non-tier role the person defined
with blank instructions, the one sentence `start.PLAIN` where the person has none. A person with
instructions of their own gets those instead.

## What this does not show

- **The start has no entrance yet.** Slice five's entrances (`workenv/cli.py`, `workenv/tui.py`)
  call it. Here the direct-use driver did.
- **Mid-session delivery is exercised only on the fake hosts.** Nothing in V1 yet composes a
  preparation for a live session's link.
- **A session resumed outside the start** (`claude --resume`, Codex's resume) is launched without
  the launch arguments, so it does not take the environment. No route declares `resume`.
- **Untrusted Codex hooks leave a delivery unrecorded.** Codex runs the hooks only once the person
  trusts them. The environment still reaches the session at launch, but no link is opened and
  nothing is recorded.
- **Claude Code enforcing `disallowedTools` in an `--agents` definition was not measured.** The
  start carries the field; whether the host applies it to a session-scoped definition is not
  shown here.
- **Codex's launch instructions go on the command line as one argument.** macOS took 30,551
  characters here and 120,000 in the channel measurement. Linux caps one argument at 128 KiB;
  that was not measured.
- **The `N15-C11-POS` failure** stands until the re-freeze (`D-20260928-bf66d1`).

## Evidence

In the workbench's `team-env-20260920/v1-slice4-use/start/`:

- `use5.py` and `use5.home3.txt`: the setup and the real probes.
- `use6.py`, `use6.home3.txt` (both hosts, before the fix) and `use6.home3.codex-fix.txt` (Codex
  after it): the direct use.
- `default_role.py`, `default_role.out` and `default_role-2.out`: the measurement of Codex's role
  rule.
- `config_read.py`: the shape of Codex's `config/read`.
- `realv1-after.txt`: the V1 cases.

The state root is `../home3/`. The commit logs are `../commit-3a.log`, `commit-3b.log` and
`commit-3c.log`.

## Next

1. **Slice five:** the entrances call the start, `operation.history.read`, and
   `capability.probe` for `read`.
2. **The P01 re-freeze:** CMP-QUALIFIED to V5, DEL-PERSONAL's second preparation, and the
   scenarios' delivery probe steps, `N15-C11-POS`'s wires among them. Then V1's acceptance.
3. **Before the tier fences are relied on:** measure whether Claude Code applies `disallowedTools`
   to an `--agents` definition.
