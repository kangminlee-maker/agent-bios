---
created_at: 2026-09-30T11:54:29+09:00
head: 2a4a466
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-b36ceb, D-20260930-89edca
---

# The person and the session are shown which selected source does not resolve, and a Codex probe keeps Codex's reason

This follows the [09:42 direct-use record](2026-09-30T0942--6265ff4--v1-acceptance-direct-use-record.md).
That run confirmed the 09:23 repair in real use, and found three places where the person is not
shown what the session or the host knows. The owner chose to fix all three before V1 is recorded
again (`D-20260930-b36ceb`). The alternatives closed:

- fixing the two visibility findings and deferring the Codex probe's reason to `FINDINGS.md`;
- deferring all three and recording V1 on `6265ff4`.

The owner also chose to run Codex real use again after changing their own Codex default model;
agent-bios does not edit the person's `~/.codex/config.toml` (`D-20260930-89edca`).

## What changed

- **One reading of whether a collection entry resolves: `preparation.resolved(store, entry, role)`.**
  - It returns the gap codes the entry states at its position, and the source and manifest of the
    revision it pins where one is held. The rules are composition's, moved rather than restated:
    - a source of another role (`role_promotion_refused` in an Instructions position,
      `selection_unresolved` elsewhere);
    - a memory entry switched on whose source has no head;
    - a source or revision not held;
    - a declared member the revision lacks.
  - `Composition.entry` composes from it. `revision_of` is a module function; the start of
    `preparation_compose` checks the basis's pins with it.
- **The entry (`workenv/tui.py`).**
  - `position_of` reads each switched-on entry of a held collection through `resolved`. A position
    some of whose entries do not resolve is `partial`, and one none of whose entries resolve is
    `missing`. Both are states the frozen C12 element enum already has, so no contract moved.
  - The label names the first source that does not resolve by its short id, and how many more.
    Example: `개인 지침 · korean-writing.md · 쓸 수 없는 원본 src_832de866`, or, with nothing
    resolving, `개인 지침 · 쓸 수 없는 원본 src_… 외 2개`.
  - The detail view states `일부 원본을 쓸 수 없음` or `원본을 쓸 수 없음`.
  - The new catalog keys are `position.unresolved`, `unresolved`, `unresolved.more`,
    `state.partial` and `state.missing`, in `ko`, `en` and `ja`.
  - Such a position stays available: focus lands on it, and it stays included, since the
    selection is the person's.
- **`sources` (`workenv/commands.py`).**
  - A position states `some selected sources do not resolve` or `no selected source resolves`.
  - Each entry that does not resolve ends in `does not resolve here (<codes>)`, for example
    `src_832d… revision 666666666666: does not resolve here (selection_unresolved)`.
- **The session's environment (`start.gaps_text`).**
  - A collection's gap names each source the collection selects that states that code, with the
    revision it pins, read through `resolved` from the collection head the preparation names. An
    example line: `- The personal instructions collection, selected source src_… at revision
    666666666666: ...`.
  - A line is written once, so several entries that do not resolve give one line naming them all.
  - The text is still a function of cross-preparation facts: no unit id, and the head the
    preparation read, not the one the store holds now. The hook's environment-digest check
    (`D-20260930-6c708c`) is unchanged.
- **A Codex probe keeps Codex's reason (`workenv/hosts/codex.py`).**
  - `Server.until` keeps what Codex said failed a turn:
    - an `error` notification it will not retry;
    - a `turn/completed` whose turn `failed`.
  - `reason` unwraps the provider's JSON message where Codex passes one on.
  - `drive` puts `Codex ended the turn with an error: <reason>` in what the probe observed:
    - where the asked turn said nothing;
    - where a rehydrated session could not be compacted.
    It says nothing of a failure when a later turn answered.
  - The wire is the one recorded on 2026-09-30 (`v1-accept/use/16-codex-app-server-turn.jsonl`).
- **The fake host (`gates/workenv/units/v1/fakehost.py`)** gains Codex modes `refuse`,
  `refusenoend`, `refusequiet`, `refusefirst` and `retrysilent`, each built from that wire.
- **Tests.**

  | File | Tests before | Tests after |
  | --- | --- | --- |
  | `test_preparation.py` | 43 | 44 |
  | `test_tui.py` | 65 | 67 |
  | `test_commands.py` | 33 | 34 |
  | `test_start.py` | 35 | 37 |
  | `test_probes.py` | 38 | 41 |

  One `test_start.py` expectation was updated to the new wording of the missing section.

## How it was checked

- **Mutation sweep** (`v1-accept/mutate_v1u.py`, output `mutate_v1u.txt`): 24 mutations, each
  undoing one part of the repair, all caught. Every mutant compiles, so no catch is a syntax
  error. The 09:23 repair's sweep (`mutate_v1r.py`) was re-run: 8 of 8 caught.
- **The workenv gate:** `WORKENV OK`, ruff included.
- **Every profile's cases** (`v1-accept/all_outcomes.py`) were run on a scratch worktree of
  `2a4a466` and on this change.
  - Both runs give 837 profile-case outcomes: 61 passed, 764 blocked, 12 failed.
  - No outcome changed. V1's 21 cases all pass.
- **Bindings.** `cases.py --bindings` emits every binding unchanged. V1's equals the frozen
  `bindings.V1` in `run-11`. No contract file, serving row, scenario or fixture changed, so P01's
  freeze stands.
- **On a copy of the real-use state,** `sources` now states the person's collection
  `some selected sources do not resolve` and names `src_832d…` as not resolving here.

## Next

1. **Real use with this commit,** by the coordinator:
   - the entry and the session with the unresolved selection;
   - `prepare codex` under the person's settings as they stand when it is run.
2. **Codex real use** once the owner has changed their Codex default model.
3. **V1 recorded** into `run-11`, then one bound review.
