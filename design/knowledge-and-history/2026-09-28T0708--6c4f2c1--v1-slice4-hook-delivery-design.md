---
created_at: 2026-09-28T07:08:27+09:00
head: 6c4f2c1
kind: design
plan: 2026-09-26T1404--f065835--development-plan.json
---

# V1, fourth slice, third increment: the hook delivers, and the session's own record shows it

The fourth slice's [design](2026-09-27T0134--0715475--v1-slice4-delivery-design.md) left real
delivery to this increment. Every route is now qualified on both hosts installed here ([the 18:00
record](2026-09-27T1800--ba744df--v1-slice4-codex-all-routes-record.md)). But every delivery so
far was submitted by a script standing in for the hook. No hook has answered a host event with a
preparation's bodies. This increment makes the hook do that, then shows it on a real Claude Code
session and a real Codex session on this machine.

It serves V1's done-when clauses that say "a record of what the session actually received",
checked by "launching a real session and reading what reached it", and "Deliver actual personal
new/current/child/rehydrated role bodies with exact result evidence". This record is the design;
the record written when the increment lands says what was built and measured. Four choices below
are the owner's, each marked **Owner decision**, and all four were decided on 2026-09-28. One
question found while measuring is still open: what a hook carries for repository-authored
Instructions that a host already loads natively (see Size).

## Who configures a session: a start, then the hook

A host runs the hook with the event on standard input and nothing else. So everything the hook
needs beyond the event is written before the host starts, into the job file that
`AGENT_BIOS_HOOK_JOB` names: the state root, the actor (principal, device and profile ids), the
host's name and the version the start read from its binary, and the preparation request the
session starts with.

A new function writes that job and starts the host with the adapter's hooks. It lives in
`workenv/hosts/start.py`, inside V1's `workenv/hosts/` owned path. It gives the host exactly the
hooks a probe gives it (`Adapter.groups`, the same command bytes), and that is load-bearing in two
ways:

- a probe qualifies a route under one hook configuration, and a real session must run under the
  configuration that was qualified;
- Codex trusts a hook by its place and a hash of it. Any difference in command, matcher, order or
  a per-hook field is a new hash, which Codex skips until the person reviews it.

This increment's own driver calls the start, and so does its direct-use run. Slice five's entrances
call it too (`workenv/cli.py`, `workenv/tui.py`). The first-use identity (the actor ids) is the
entrance's to mint and keep; the start takes it as given.

**Owner decision 1, decided 2026-09-28 (`D-20260928-30d875`): V1's own start.** Slice five's
entrances reach it. Joining `launch/agent-launch.py` and `compose/instructions_session.py`, which
already start both hosts with session-scoped hooks, is a shared-launcher edit that the plan routes
through the integrator, so it comes afterwards. Until then, sessions the owner starts through
agent-launch do not receive the V1 environment.

## What the hook does at each event

The hook stays one command, the same bytes on every run. The job and the event decide what it
does. It never fails its host: any refusal or error leaves the session as it was, with the reason
on standard error, while the journal keeps what it refused.

The order at each event is: the owner answers, then the hook prints and flushes, then the hook
records the hand-over.

- The attempt is recorded **after** the output reached the host's pipe. `received` says the
  adapter handed exactly those bodies to its host. A hook that fails between printing and recording
  therefore leaves a delivery unrecorded, never a record of one that did not happen.
- The session's host-side id is read from the event (`Adapter.session_of`).

The three host-session recipients (new, current, rehydrated) are one recipient to the owner:
`recipient_of` names each by the link's digest. That makes "which preparation has not reached
this session yet" a question the owner's own records answer, with no new state.

| Recipient | Event | What the hook does |
| --- | --- | --- |
| `new` | `SessionStart` startup | Opens the link (destination: the digest of the session id). Composes the job's request for it. Activates the session with that preparation. Prints the usage contract, the guide pointer and each delivered body. Records an attempt for `new` naming exactly those bodies. |
| `current` | `UserPromptSubmit` | Asks the owner for preparations composed for this link that no delivery has reached. With none, prints nothing: this is every prompt, so it must be fast and silent. With one, prints its bodies and records an attempt for `current`. A preparation composed mid-session (by a command the session runs, the backlog's mid-session activation) reaches the session at its next prompt. |
| `rehydrated` | `SessionStart` compact | Finds the link by the session's destination. Prints again the bodies of every preparation that reached this session. Records an attempt for `rehydrated`. See Owner decision 4. |
| `child` | `SubagentStart` | Reads the child's kind from the event. For a tier seat's child, it mints a use id (a child is named by its link and use id, never by a session id the owner makes up), prints the bodies of the preparations that reached the main session, and records an attempt for `child` naming exactly those. For a review child, or any other kind, it prints nothing and records nothing. See Owner decision 2. |

The link is found from the session id at every event after the first. The owner keeps links by id
only, so `delivery` gains a read of the link a destination names. It reads the owner's own records
and writes nothing.

**Owner decision 2, decided 2026-09-28 (`D-20260928-4a1cc3`): by the rule that dispatched the
child.**

- **Tier-seat children receive what the main session received.** These are children dispatched
  by the tier rule: frontier, helm, workhorse, sweep. The reason is consistent and predictable
  work.
- **A review child receives no agent-bios content**, only its review instructions. The reason is
  an isolated perspective.

How this is carried out:

- **The kind comes from the event.** The hook reads the child's kind from the `SubagentStart`
  event. The field is the adapter's to name, because the hosts differ. Whether each host reports
  a kind, and in which field, is observed in the real run before anything relies on it.
- **The kind names are data.** The job carries the tier-seat kinds and the review kinds, taken
  from the launch configuration. Renaming a seat changes no code.
- **Any other kind receives nothing.** That covers Claude's built-in `Explore` and `Plan`,
  `general-purpose`, and the agents of skills and plugins. This default follows the owner's
  earlier answer that a subagent is an isolated session. The owner has not ruled on these kinds
  separately.

What the hook cannot do by itself:

- **On Codex, the route by which a parent received content decides whether a child gets it.**
  Measured 2026-09-28 on Codex 0.157.1 through the app server (tool:
  `…/v1-slice4-use/manual/review_child_isolation.py`, outputs beside it). Two markers reached the
  parent:
  - one through the trusted `SessionStart` hook, V1's route;
  - one through session-wide `developer_instructions`, the existing launcher's route.

  The parent then spawned a child, and each child's rollout was read. The spawn arguments are
  confirmed in the parent's rollout.

  | Child spawned with | Hook-delivered marker | `developer_instructions` marker |
  | --- | --- | --- |
  | `fork_turns: none` | absent | present, in the child's base developer message |
  | `fork_turns: all` (Codex's default) | present, as a copied developer message | present |

  Only `SubagentStart` fired for the child; `SessionStart` did not. So V1's `new` route never
  reaches a child. A review child on Codex is kept clear of V1's deliveries only by a review
  dispatch that passes `fork_turns: none`; the hook cannot remove copied turns. The shipped
  guide now states that a review child is spawned with `none` (`D-20260928-7d8bbb`). The guide also says Codex's
  `SubagentStart` receives `agent_type` and may return `continue: false`. A hook could therefore
  refuse a review child, but whether the event says how the child was forked is not known.
- **Claude Code has no review kind of its own.** The shipped Claude agents are the tier seats
  (`claude/agents/`), while Codex also ships `reviewer`. A review dispatched as a Claude child
  would be indistinguishable from a tier child, so it would receive the environment. Reviews go
  to another provider through the wrappers today, as separate processes the hook never sees. A
  Claude review kind is an open item for the owner if Claude children are ever used for review.
- **The existing launcher's Codex activation reaches every child, review children included.** It
  sets `developer_instructions` for the whole session (`compose/instructions_session.py`). The
  measurement above found that text in the child's base developer message with and without
  copied turns. That breaks the owner's review-isolation rule today, for any review run as a Codex
  subagent in a session agent-launch started. That launcher is outside V1, so the fix waits until V1 joins it
  (`D-20260928-6a5d2c`, backlog `../session-scoped-corpus/2026-09-28T0821--6c4f2c1--review-child-isolation-backlog.md`). The measured child had no role (`agent_role: null`, as no Codex agent roles
  are installed natively here). Whether a role's own `developer_instructions` would replace the
  session's is not measured.

How the decision was reached:

- The owner first answered that a subagent is an isolated session, that whether it receives the
  parent's bodies is the main session's to decide, and asked which rule starts the child this
  route serves.
- The answer was none in particular. `SubagentStart` fires for every child the host starts,
  whatever caused it: the model delegating on its own judgment, an instruction telling it when to
  delegate, a person, or a skill or workflow. The hook sees only the event, and the child's kind is
  the one trace of the dispatching rule that the event can carry.
- The owner then stated the rule by dispatch.

The decision closes two alternatives: every child receiving the parent's bodies, and a child
receiving something only when the main session asks before starting it. V1's done-when ("child …
role bodies") is met by the route delivering to the children the rule names, not by delivering to
every child.

**Owner decision 4, decided 2026-09-28 (`D-20260928-3249ff`): the same bodies it had,
re-delivered whole.** C11 delivers to a rehydrated conversation whole, and
`rehydration_needs_bodies` refuses a hash where bytes are needed. Whether the checkout moved since
is not checked at compaction; composing again then was the alternative ruled out, because it could
hand the session an environment other than the one it was working under.

## Size: what a session actually gets

- **Codex** spills a hook's `additionalContext` above about 2,500 tokens to disk. It hands the
  session a preview with recovery metadata instead: the `additionalContextLimit` description in
  0.157.1's app-server schema reads "`null` uses 2,500 tokens; `0` disables spilling for this
  hook". The two guides used in direct use are 19,691 and 10,246 bytes. With the default, the
  model would see a preview and read the rest only if it chose to.
- **Claude Code 2.1.283 spills too.** Measured on 2026-09-28: a `SessionStart` hook whose
  `additionalContext` carried the two guides (30,132 characters) reached the session as
  "Output too large (29.4KB). Full output saved to: …/tool-results/hook-…-additionalContext.txt",
  with a 2 KB preview. That is the transcript's `hook_additional_context` attachment. The billed
  prompt grew by 771 tokens, not by the guides' size. Its threshold, and whether any setting lifts
  it, are not known yet; they must be found before building, because Owner decision 3's switch
  exists only on Codex.

How much a delivery weighs, measured 2026-09-28 in this repository:

- **Tokens.** Claude Code's `/context` counts this repository's `AGENTS.md` (42,636 characters)
  as 14.8k tokens, about 2.9 characters a token. The guides' figure uses that ratio.
- **Start sizes.** The billed prompt of a one-line first prompt, with nothing delivered, was:
  - 52,737 tokens on Claude Code 2.1.283 (`claude-opus-5-5`, 1,000,000-token window);
  - 25,558 tokens on Codex 0.157.1 (`gpt-6-astra`, 828,400-token window).

| What a session start carries | Characters | Tokens |
| --- | --- | --- |
| the usage contract and the guide pointer alone | 179 + a path and a digest | about 60 |
| the direct-use selection, the two guides | 30,132 | about 10.5k |
| this repository's `AGENTS.md` as repository Instructions | 42,636 | 14.8k |

Codex evaluates the threshold against one hook's whole output, so every realistic selection
spills.

Two findings bear on what repository Instructions a hook should carry at all:

- **Claude Code already loads this repository's `AGENTS.md` whole**, through `CLAUDE.md`'s
  import (`/context`: 14.8k tokens under Memory files). Delivering it again through the hook
  would put it in the session twice.
- **Codex already loads it, but cut short.** Codex 0.157.1 loaded only the first 32,320 of its
  42,864 bytes, which is its default 32 KiB project-document limit. The sections from "Traps that
  cost a real attempt here" onward never reach a Codex session.

So what a hook carries for repository-authored Instructions is a question for this increment:
nothing a host already loads whole, and what it drops where it cuts.

**Owner decision 3, decided 2026-09-28 (`D-20260928-cc0692`): `additionalContextLimit = 0`** on
the adapter's Codex hooks, so the session is given the bodies whole. This changes the four hooks'
hashes. So the four delivery routes on Codex 0.157.1 are probed again, and the person reviews the
four hooks once more in `/hooks`. A probe qualifies the configuration a session runs under, so
probe and session change together. Keeping the default spill was ruled out: it hands the session
a preview and a path, and the environment would reach the model only as far as it opens the file.

The ledger row's token figures (about 7,500 and 10,700) were estimated at four characters a token
and are low; the measured ones are in the table above, and they only strengthen the choice.

## Evidence of what reached the session

The owner records what the adapter handed over; C07 keeps observed use a third fact, and this
increment does not change that. The direct-use run needs one more thing: what actually reached
the session. It reads that from the host's own record of the session, not from the model's
answer (Codex's model will not repeat a developer message, `D-20260927-f05a86`):

- **Claude Code:** the session's transcript under `~/.claude/projects/`, where hook output is kept
  with the event that produced it;
- **Codex:** the session's rollout under `~/.codex/sessions/`, where the added context is a
  developer message.

Each delivered body's bytes are compared with what the record holds: whole, spilled to a preview,
or cut. Both formats are the hosts' own and can change; the run states each host's version, as a
probe does. `compose/instructions_session.py` already reads the native session log before it
records a pin, so this repository reads host records this way already. That read stays in the
direct-use tooling; the owner does not read host files.

## The entrance

`workenv/hosts/hook.py` now writes kept state, so its disposition in `gates/workenv/entrances.jsonl`
changes:

- **From:** `no_reach` / `holds_no_write`.
- **To:** `routed` through `projection_owner`, with `root_origin: caller`. The job names the state
  root, which is a root the caller sets for this route alone.

This is the same shape as `compose/canary.sh`'s `session_start` row. A routed entrance is guarded,
so no cutover follows. `test_entrances.py` holds the rows equal to the shipped entry scripts, and
`test_each_owner_is_held_by_at_most_one_route` is unaffected, because the hook routes rather than
holding the choke point.

## Time

- A Claude Code hook has a time limit, and so does a Codex one. `preparation.compose` reads the
  checkout, and the hook pays Python's start and the runtime's imports on every event.
- `UserPromptSubmit` fires on every prompt, so its no-delivery path must stay short: read the job,
  find the link, one query, exit.
- The real run measures each route's time on this repository. A per-hook `timeout` is set only if
  the measurement calls for it. On Codex, setting one is a hash change, so it would join Owner
  decision 3's re-review rather than cost a second one.

Concurrency:

- Children can start together, and each child's hook writes. The store opens with a 30-second busy
  timeout and every unit begins `IMMEDIATE`, so writers queue rather than fail.
- A test starts several child events at once and checks that every attempt is recorded once.

## Checks

1. **Units with the fake host** (`gates/workenv/units/v1/fakehost.py`). The fake runs the real hook
   with a job, against a real state root. The tests check:
   - each route's records: link, preparation, activation, and attempt with exact bodies;
   - silence on a prompt with nothing pending, and delivery on a prompt after a mid-session compose;
   - rehydration naming held bodies;
   - one attempt per concurrent child;
   - printing without recording when the owner refuses;
   - that the hook's exit status is 0 on every failure the fake can bring about.
2. **A mutation sweep** over the new code, run to the end before any commit. Each sweep in this
   slice has found live reverts.
3. **The real run** on Claude Code and on Codex, in this repository:
   - start through the start function;
   - one prompt, one subagent, one compaction and one prompt after it;
   - then read the host's record and the owner's observations side by side;
   - written down as a dated direct-use record.

## Not in this increment

- **Mid-session activation**, the backlog's first item: the command that composes for the current
  session from inside it. This increment builds the route it lands on.
- **The entrances and first-use identity** are slice five's.
- **`SessionStart` with source `resume` and `clear`** is not a declared route. A resumed session
  that lost its context is not delivered to until one is declared and probed.
