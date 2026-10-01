---
created_at: 2026-10-01T21:34:02+09:00
head: 3551ccb
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
decisions: D-20261001-c2900c, D-20261001-4c38cf
---

# V1 restructure after the blind diagnosis: one reading of what each unit means, and checks that reach the next step

V1's nine bound reviews gave 2, 2, 2, 2, 1, 2, 4, 2 and 2 findings. A blind cross-provider
diagnosis (`review-v1-design-diagnosis-20261001/`, 18:44–19:06) was given the source at
`3551ccb`, the nine results and every repair since the first review, and not the author's view.

- **What it found.** It supported H2 (code structure) and H4 (verification before review). It did
  not support H3 (the frozen contracts) or H5 (the review method).
  - **Composition.** Eight findings trace to composition rules that separate consumers rebuild
    for themselves.
  - **Partial repairs.** Four later findings were left behind by repairs that reached only the
    instance reported: r6-1→r7-1, r2-0→r7-2, r7-0→r8-0→r9-0.
  - **Verification.** All nineteen escaped through checks that stopped before the next step.
- **What it recommended.** Six changes, none of which needs a contract change.
- **The owner's choice.** All six before the tenth review (`D-20261001-4c38cf`).

This record states what each change is, in the order it lands. The contracts, the scenarios and
the frozen bindings do not move, so P01 is not reopened. Every check that holds today must hold
after.

## 1. One reading of what a composed unit means for a start (`workenv/preparation.py`)

Today seven places decide a unit's part in a start, each with its own filter on role, standing,
body, `needed_by` and `startup`:

| Place | Decides |
| --- | --- |
| `compete` | standing and `needed_by` |
| `bodies` | which bodies are read, and which missing ones are gaps |
| `roles.unmet` | which gaps refuse the start |
| `roles.moved` | which units are held to their document |
| `delivery.carried` | which units are delivered, and recorded as arrived |
| `start.unheld` | which units the session is told it lacks |
| `tui.position_of` and `commands.held_at` | the same again, from the collections, before any composition |

After this change they read one thing.

- **Composition stays the one place that composes.** `Composition` takes the state root, not a
  call, so the entry and `sources` run the same composition in memory, writing nothing. Today
  they rebuild a position from collections and sources themselves.
- **A need no unit answers is a gap.**
  - A winning unit's `needs` entry that matches no composed unit (by source and member) is
    `companion_unavailable` (C04: "a declared companion the answer needs and this installation
    lacks"). It is stated at the needing unit.
  - Today such a need leaves no trace, and a required winner starts without the bytes it relies
    on (r9-0).
  - Needs are followed one step, as C07's `unit_binding` words them: a unit's needs bind "while
    this unit wins". A needed unit that does not win carries no needs of its own.
- **`preparation.Reading` is the one reading of a composition's units.** It is built from a
  stored preparation, or from a composition in memory, and every consumer asks it:

  | Name | What it is | Who reads it |
  | --- | --- | --- |
  | `delivered` | an Instructions unit standing `winning` or `layered` | |
  | `carried` | delivered, with a body | the start's bodies, the projection's members, the hook's attempts, the observation's inventory |
  | `required` | an Instructions unit winning with `startup: required`, or a unit such a unit needs | `roles.unmet` refuses on a gap at one of them |
  | `claims` | with a body, and delivered or needed | `roles.moved` holds these to their documents, and the entry shows the ones that changed |
  | `unheld` | delivered, with no body and no gap | the session's notice, and the entry's |
  | `missing_needs` | per unit, the needs no unit answers | named in the environment and on the entry |

- **The entry composes before it starts.**
  - It composes the basis the start would send, in memory, and draws every position the start
    would apply from that composition.
  - A position the person has left out is drawn from a composition of that position alone. It
    takes no part in the start, so only its members and their bodies are shown.
  - Space recomposes. A position's names, missing bodies, changed documents, unresolved sources
    and missing needs come from the same units the start would compose.
  - `sources` draws each position the same way, over the basis a start would suggest.

## 2. Integration tests that reach the next step (`gates/workenv/units/v1/test_paths.py`)

**Invariant tests.** These run compose, activate (dispatch, then the session's report), render and
observe across distinguishing states. Each case states its invariant:

- **Refusal.** The start is refused exactly where a required unit (a required winner, or a unit it
  needs, answered or not) has no usable body.
- **Text.** The environment holds exactly the carried bodies, each once, rendered from the
  preparation the delivery records.
- **Inventory.** The observation lists exactly the carried units whose bodies were handed over,
  by identity. Equal bytes in another role or standing are not listed.
- **Changed documents.** A start is refused `working_bytes_moved` exactly where a claimed unit's
  document changed, and the entry shows exactly those.
- **The entry before the start.** It shows every cause the start refuses for.

The states crossed are:

- the needed unit: selected and on, switched off, left out, or shadowed;
- the winner: required or not;
- the body: held or missing;
- the bytes: the same as another unit's, or different.

**Sequences.**

- Check, unknown, check again, settled.
- More starts than the history lists, around a pending one.
- Both interleavings the journal decides on: the same id, and the same request under a new id.
- A refusal read before the unit of work that is no longer true inside it.
- A Codex compaction that fails after it was accepted, and a Claude Code `/compact` that reports
  no compaction.

**The terminal.** The terminal's own lines, not the model's elements, for a refused start and a
settled check.

## 3. A probe counts only a confirmed prerequisite (`workenv/hosts/`)

- **Codex.**
  - A turn counts only when Codex ends it `completed` (its `TurnStatus`). A failed or interrupted
    turn gives no reply, with Codex's reason.
  - A compaction counts only when the compaction turn ends `completed` and Codex reported the
    compaction: a `contextCompaction` item, or `thread/compacted`. Both are in the app-server
    schema of 0.159.2, generated with `codex app-server generate-json-schema`.
  - Otherwise the probe says that Codex did not compact the conversation, and asks nothing (r9-1).
- **Claude Code.** `/compact` counts only when the stream carries a `system` message of subtype
  `compact_boundary` before its result. That is the documented sign that compaction happened
  (Agent SDK, "Message types").
- **The real probes.** The real `rehydrated_delivery` probes of both hosts on this machine were
  made by the earlier code, so they are run again during real use.

## 4. One description of what a preparation hands a session (`workenv/hosts/start.py`)

`start.handed(state, prepared)` is the one description:

- the preparation;
- its carried units in order, by source, member, revision and body;
- their bytes;
- the rendered environment and its digest.

It is read in every place below:

- the start writes the launch text and the job from it;
- the hook's new-session check compares its own description with the job's;
- the hook's attempts name its carried bodies;
- a prompt's delivery compares the carried identities of the latest preparation with those the
  session last received;
- the observation's inventory is the same carried set.

## 5. Every admission decision is made inside the unit of work (`workenv/journal.py`)

What is decided before the unit is a forecast, and the unit decides.

- **A settled id.** Same-id replay of a settled request, and an id held with other bytes, are
  settled facts and may answer before the unit.
- **The unknown-outcome rule.** It is asked again inside the unit. A refusal there stands.
  - Where it refused before the unit and admits inside, the request runs again from the start,
    up to three times.
  - Today the refusal read before the unit is kept although it is no longer true.
- **An entry with a `prepare` step** names the admission checks it made before the unit
  (`admits`), and asks them again inside the unit.
  - For a revision these are: the source held with a home, the head, a published home, a home
    conflict, the binding. Today only the head is asked again.
  - A check that refused before and admits inside runs the request again.
  - A check that admitted before and refuses inside refuses.
  - A probe's checks read the request alone, so nothing moves under them.

## 6. Recovery as explicit states the entry derives from (`workenv/tui.py`, `workenv/journal.py`)

- **The start.** It is one of: not sent, sent, unknown, or refused.
- **The check of an unknown start.** It is one of: none, not checked, checking, still unknown,
  could not check, or settled.
- **What is derived from them, and nowhere else:**
  - Space and ← → can change the choices only while the start is not sent or was refused.
  - Enter on the start dispatches only then.
  - The check can be asked only while it is not checked, still unknown, or could not check.
  - The start is held back until the check is settled.
  - The wording of each result.
- **Finding the unknown start.** The entry reads its unknown start from the journal
  (`journal.pending_starts`), whatever the history lists.
  - The history read and that reading share one membership rule, `journal.starts_in`.
  - The frame still cites the history read where the history shows that start.

## How it is checked

- **Tests.** V1's existing 510 tests, and the tests above.
- **Mutation sweep.** A new sweep reverts each rule this restructure states, one at a time. The
  earlier sweeps are run again, and their anchors that the restructure removed are named.
- **Outcomes.** All 837 outcomes are identical before and after.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings, and the workenv gate passes.
- **Real use on both hosts.** A new session as before. Then a current delivery after a personal
  body changes, and a rehydrated one after `/compact`. The rehydrated probes are run again first.
- **The tenth review.** One bound review, whose result goes to the owner.
