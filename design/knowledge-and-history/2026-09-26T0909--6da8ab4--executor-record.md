---
created_at: 2026-09-26T09:09:28+09:00
head: 6da8ab4
kind: design
plan: 2026-09-25T1636--6fa562f--development-plan.json
amends: 2026-09-24T2124--0fe13da--conformance-adapter-design.md
decisions: D-20260926-65ab72, D-20260926-8a61d8, D-20260926-2fc4d0, D-20260926-fce786, D-20260926-8ee6bb, D-20260926-1c8324, D-20260926-53cf12
---

# The executor: the driver runs a case's scenario against the code that serves it

The [21:24 adapter design](2026-09-24T2124--0fe13da--conformance-adapter-design.md) moved a family
case's verdict into the conformance driver: it runs the case's frozen scenario and holds what the
code in the profile's scope answers to what the scenario states. Its stage 3 is in the tree now:
the core, the host, given steps and placement, addressed routing, signing, replays and
`receipt_of`. The route through a family's own test module (`CASES` in `driver.py`) is deleted,
as the design required, not left beside the new one.

This is step 3a of V1. The [third-read record](2026-09-26T0219--3b7e8d1--third-read-record.md)
said V1's next work was "the family modules its cases need"; that contradicts `D-20260924-f63e31`,
which gave the verdict to the driver. The work was, and is, this executor.

## What is in the tree

| File | What it does |
| --- | --- |
| `gates/workenv/conformance/executor.py` | Runs one case: builds each request from the scenario and what the owner already returned, routes it, learns what the owner mints, holds the answer to the stated one |
| `gates/workenv/conformance/host.py` | One process per world process, importing the code under test from the tree and calling it with the design's call object |
| `gates/workenv/conformance/features/signing.py` | Generates a key for each public key a scenario states and signs every envelope over the bytes it names with `ssh-keygen -Y sign` |
| `gates/workenv/conformance/driver.py` | Resolves what a profile runs in a family, unchanged, and runs each case through the executor |
| `gates/workenv/scripted_owner.py` | The executor's test double: answers each step as stated, minting values of its own |

`cases.CORE` now holds the executor and the host beside the rule oracles, so every profile whose
cases the driver runs moves with them. P01 is re-frozen once, over the regrouped registry, when
V1's cases can be run.

## How one step runs

The executor's docstring states the rule; in short:

1. The request and the records it carries are built from the scenario. Every minted stand-in is
   replaced by the value the owner returned, every joined digest is recomputed over the bytes it
   names, and a size beside such a digest with it. A replay resubmits the bytes its step sent.
2. The serving table routes the step. An operation a node in the profile's scope serves goes to
   that node's entry through the layers in scope; `operation.query` and `operation.cancel` go to
   the layers, the journal answering, when the journal layer is in scope; every other step is
   given.
3. A given step is answered with its stated answer, and what it returns is handed to each place
   entry in scope. The layers in scope still run on it.
4. Each value the step mints is learned at its first place in the answer and must be of its
   shape.
5. The answer is held to the stated one: the result, then the receipt the result names, then each
   returned record by position. A digest of a record this answer returns is computed over what
   the owner returned, so a difference is reported where it is. Each record is also held in stored
   mode, because only a minted value can differ from the stated record, and a minted value its
   owner could not store (a receipt sequence of 0) would otherwise pass.
6. A refused step must be refused with exactly the stated triples and without `admitted()`.

A case stops at its first difference, `failed`, naming the step, the record and the JSON pointer.
A case is `blocked` by name when a feature it uses has no module, when its registry row names
runtime rules, or when an entry, layer or place it reaches is not written.

## Open items of the design, and how each stands

| Item (21:24 design and the V1 scoping) | Now |
| --- | --- |
| Layer, place and event entry signatures | `layer(call, inner)` and `place(call)` with the given answer as `call.given` (`D-20260926-2fc4d0`). Events are designed with the event features |
| How refusal triples name records; matching returned records | By position: `request`, `carried/<i>`; returned records in the order the result lists its outputs (`D-20260926-2fc4d0`) |
| Values a given step mints | The scenario's own stand-ins; what the layers in scope return is learned like any answer (`D-20260926-2fc4d0`) |
| Replays and `receipt_of` | Judged by the core, not by feature modules (`D-20260926-65ab72`) |
| Which records the rule oracles judge | Not built. A case naming runtime rules is blocked until it is (`D-20260926-8a61d8`) |
| Submit mode | Open. The call does not say which carried records are submitted. The six V1 cases whose scenarios name `submits` name it only on `team.found`, which V5 serves, so at V1 the driver gives that step |
| The checkout world, faults, the lost reply and the clock at V1 | Step 3b |
| Hook obligations in the contracts | Open |
| Access-generation bring-up below V4 | Open, with V1's first slice: nothing in V1's scope reads the generation, but its profile records may state it |
| Whether `members` by digest is enough | Open until an implementation reads a checkout by path |

## Controls

- **Positive.** Every scenario is run against the scripted owner, which mints fresh values and
  computes digests over the bytes it received. 82 of the 162 pass, scenarios that sign among
  them. The other 80 are blocked by name on a feature not written yet, and none fails. A scenario
  with answers stated `receipt_of` an earlier step also passes when its clock and process features
  are installed as nothing and its processes share one host.
- **Negative.** One planted difference per rule, each required to fail naming where. The planted
  differences are: a value stated otherwise; a principal id that moves after key rotation; a
  learned value answered otherwise at a later step; a digest over other bytes; a minted value of
  the wrong shape or missing; a value only stored mode refuses; a swapped refusal code; a refusal
  after `admitted()`; a refused request answered and an answered one refused; a replay and a
  settled duplicate that each write a new receipt; an addressed operation that no layer answers.
  The routing is checked by what the layers and places log: given steps reach every place and
  layer, and addressed steps reach the journal and are not given to it. Blocking is checked for a
  missing entry, function, layer and feature and for a case naming rules. The host is checked
  with code that prints, raises or dies, looks for the judge, or checks its HOME and its
  assertions. Signing is checked with `ssh-keygen -Y verify`: an envelope verifies over the bytes
  it names and not over others, no stated public key survives, and an unstated signer fails.
- **Reverts.** Each rule was reverted in a copy of the tree, one at a time, and its control was
  required to fail: 27 reverts, each held against every control that guards it, 33 pairs, all
  caught; the untouched copy passes. The first pass found three controls that did not test their
  rule, and each was fixed:
  - the journal log did not say whether a query was given, so routing queries past the journal
    still passed;
  - the printing test's output sat in a buffer and never reached the pipe;
  - `-E` and the environment filter did the same job, so removing either alone went unseen
    (`D-20260926-fce786`).
- **End to end.** The driver runs V1's N09 case against a root holding every V1 entry, a
  pass-through journal layer and a place, each delegating to the scripted owner. The case passes
  and the command exits 0. A planted difference fails the case naming the step and pointer, and a
  raising entry fails it with its line.

`gates/workenv/test_executor.py` runs 35 tests and `test_driver.py` 17. The 26 tests of
`test_driver.py` that judged the deleted route went with it, the `-O` refusal among them. The workspace gate passes: every unit test and ruff over `workenv/` and `gates/workenv/`.
`cases.py` reports `CASES OK`, the plan gate passes with 33 positive and 442 negative controls, and
the dated evaluator still reads `run-7` as accepted `[P00]`, ready `[P01]`.

## Where V1 stands

At V1 the driver runs 22 cases. Sixteen use no feature beyond signing and run now. Each of them is
blocked on `workenv.journal:layer_journal`, because no V1 code is written. The other six wait for
step 3b: faults (CMP-SELECT, N05-RESTART-POS), the file-edit event (CMP-QUALIFIED,
N27-SELECTION-NEG, SRC-01), the clock (SRC-01) and the lost reply (TUI-ENTRY-UNKNOWN).
N27-SELECTION-NEG also needs rule oracles.

The owner's V1 decisions from the same morning are in the ledger:

- the command surface extends the entrances that exist (`D-20260926-8ee6bb`);
- V1 is used from the worktree until PK installs a candidate (`D-20260926-1c8324`);
- V1's role-projection module is `workenv/roles.py`, because a path under `workenv/` may not
  carry a concept slug (`D-20260926-53cf12`). The plan's owned paths and the serving rows move
  with it in a plan successor.

## Next

- **Step 3b.** Clock, faults, the file-edit event with its checkout world, and the lost reply;
  rule oracles with their context.
- **V1 in slices.** Each slice is implemented, used here from the worktree, and tested:
  1. profile, storage, journal and identity;
  2. sources;
  3. preparation;
  4. delivery, hosts and roles;
  5. the entrances.
- **After the slices.** P01 re-freezes, then V1's acceptance.

Nothing here is pushed.
