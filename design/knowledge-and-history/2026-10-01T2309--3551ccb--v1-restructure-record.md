---
created_at: 2026-10-01T23:09:17+09:00
head: 3551ccb
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20261001-4c38cf, D-20261001-c2900c, D-20261001-7d8005, D-20261001-56feae
---

# V1's restructure landed as designed, and the path tests it added found three more places where the entry or a delivery read a unit otherwise than the start does

This records the implementation of the [21:34 restructure design](2026-10-01T2134--3551ccb--v1-restructure-design.md).
The owner chose all six changes before the tenth review (`D-20261001-4c38cf`). No contract,
scenario or frozen binding moved, so P01 is not reopened.

## What changed, in the order it landed

1. **One reading of a composed unit** (`workenv/preparation.py`).
   - `preparation.Reading` answers, once per preparation, what each unit means for a start:
     delivered, required, claimed, carried, unheld, unmet.
   - A need no composed unit answers is `companion_unavailable` at the winner. A needed unit
     stays required while its winner is, however it stands (C07 `unit_binding`).
   - The activation, the projection, the start's environment, the hook, the observation, the
     entry and `sources` ask it. Their own copies of these rules are gone.
   - `preparation.composed` composes in memory, so the entry draws a position from what a start
     of its basis would compose.
2. **Paths that reach the next step** (`gates/workenv/units/v1/test_paths.py`). It holds 56 cases.
   - `Crossed` (32 cases) crosses four things: where a needed unit stands (on, off, omitted,
     shadowed), whether the winner is required, whether the body is held, and whether the bytes
     equal the winner's. Each case runs compose, the entry, activation, the environment, delivery
     and observation, and states its expectation from the rule.
   - `OtherRole` (8 cases): the needed member is Team knowledge.
   - `Changed` (12 cases): a repository document changed or not, under each standing.
   - `Recovering` (4 cases): real queries, and the terminal's own lines.
3. **A probe counts only a confirmed prerequisite** (`workenv/hosts/codex.py`, `claude_code.py`).
   - Codex: a turn counts only where it ends `completed`. A compaction counts only where Codex
     accepted it, reported it and completed its turn.
   - Claude Code: `/compact` counts only where `compact_boundary` came before its result.
4. **One description of what a preparation hands a session** (`workenv/hosts/start.py`
   `Handed`).
   - The start writes the launch text and the job from it.
   - The hook's new-session check compares the digest and the carried units with the job.
   - The hook's attempts name its bodies.
5. **Every admission decided inside the unit of work** (`workenv/journal.py` `attempt`,
   `workenv/sources/revisions.py`).
   - The unknown-outcome rule and an entry's `admits` are asked before the unit and again in
     it, and the answer in it stands.
   - Refused before and admitted in, or found gone by the step that publishes: the request runs
     again from the start (`Again`), at most three times.
6. **Recovery as explicit states** (`workenv/tui.py`, `workenv/journal.py`).
   - The start's states and the check's states, and the actions and wording derived from them.
   - The entry reads its unknown start from `journal.pending_starts`, by the membership rule the
     history read uses (`acting_in`, `starts_in`). It cites the history only where the history
     lists that start.

## What the path tests found

Each was reproduced through the real code before it was fixed. The fix is the reading the start
already uses.

- **Two carried units with equal bytes.** An attempt named their body twice. C11's `bodies` is
  `uniqueItems`, so the hook's delivery record was refused and the session never observed.
  `Handed.bodies` now names each body once, and the hook uses it.
- **A switched-off unit a winner needs.** The start refuses where its body is missing or its
  document changed. The entry drew no switched-off unit, so it showed no cause.
  `tui.drawn_from` now draws such a unit's problem on its position, and never as a member name.
- **A needed member of another role.** A required Instructions winner needing a Team knowledge
  member whose body is missing is refused. The entry named a missing body for Instructions only.
  It now names one for any unit a winner needs. The case crosses scopes, because a position
  drawn from a composition of its own scope alone loses the need.

## Where this departs from the design record

- **A prompt's delivery** compares the text the session holds, which names each carried unit's
  layer, role, member, source and body. The design said carried identities.
  - A revision moving alone brings no new text (`D-20261001-7d8005`).
  - The new-session check does compare carried identities.
- **After three passes** whose admission moved, nothing is held and the journal says so
  (`D-20261001-56feae`). Publishing must precede the unit (B03), so the last pass cannot prepare
  inside it.
- **Signatures in `admits`.** A commit's signatures read the signer's bindings, so they are among
  the admission checks asked in the unit, besides those the design named.
- **Where the sequences live.**
  - The interleavings the journal decides on are in `test_journal` (`Held`, `Ruled`, `Decided`).
  - A compaction accepted and not done is in `test_probes`. The fake host gained
    `compactitemfails` and `saidinterrupted`.
  - `test_paths` names both.
- **Recovery wording** keeps the catalog's words: a check still unknown draws the unknown start's
  line with state `unknown`. No new words were added.
- **Removed.** `start.delivered` lost its last reader and is removed.

## How it was checked

- **Tests.** V1's unit tests: 589, all pass. `test_paths` is new.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical to
  `outcomes-after-v1zf.json`: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals `bindings-v1zf.json` and the 13 frozen bindings
  `run-18` holds.
- **This restructure's sweep** (`v1-accept/mutate_v1zg.py`) undoes each rule it states, one at a
  time.
  - First run: 30 mutations, 6 missed (`mutate_v1zg-first.txt`): the entry composing each
    position alone; a Codex turn ended otherwise; a compaction Codex fails; the new-session
    carried check; the prompt's text comparison; the step that publishes keeping a moved
    admission.
  - A test was added for each, and one mutation more. Re-run on the final tree:
    31 of 31 caught (`mutate_v1zg-rerun-restructure.txt`).
- **The earlier sweeps, re-run on this tree** (`*-rerun-restructure.txt`, run on copies by
  `rerun_sweeps.py`).
  - None missed a mutation it could apply.
  - The restructure moved 45 of their anchors (`moved_anchors.py rerun-v1zf
    rerun-restructure`). `mutate_v1zg-reanchored.py` anchors each again where its rule now
    lives, under its old name, and caught 45 of 45 (`mutate_v1zg-reanchored-run.txt`).

## Next

1. Commit, through the hook.
2. Real use on both hosts with the committed code.
   - Re-admit `AGENTS.md`, whose bytes changed, and run the rehydrated probes again.
   - Then a new session, a current delivery after a personal body changes, and a rehydrated
     one after `/compact`.
3. V1 recorded into `run-19`, and one bound review whose result goes to the owner.
