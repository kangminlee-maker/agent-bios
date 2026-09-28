---
created_at: 2026-09-28T15:28:40+09:00
head: 5870357
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260928-202a51, D-20260928-09cd4b, D-20260928-d6ff3a
---

# V1, fifth slice, first increment: the owner operations of the entrances

This is the first increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md):
the owner operations an entrance calls. No entrance calls them yet. The entry model
(`workenv/tui.py`) is the second increment, and the terminal is the third. V1 is not complete, and
no node is accepted by this work.

## What was written

- **`workenv/cli.py`: `route.offer` and `route.select`.** The module docstring states the rules.
  - An offer is kept with the instant it was made.
  - A route whose support says it is qualified must name a probe held here. That probe must be of
    the capability the route's action needs, and among the latest probes of it on its client.
    Those latest probes must have run for real through the route's current wire and worked.
    Otherwise the offer is refused `capability_not_qualified`, at that route's support.
  - The action table is `NEEDS`: `use` needs `new_delivery`, and `decide` needs `question`.
  - A selection answers for the start request it names. That request must be held here and be of
    the route's action, and it must have been answered with a record. The outcome names the
    first record it returned. A pending start is `outcome_unknown`, settled by querying it.
  - A route that is not qualified now is refused `capability_not_qualified` and never run. Its
    outcome says the route is unsupported, on the client that probed it, or else on the one
    client the offer's qualified routes were probed on. Where no one client exists, the refusal
    returns no outcome.
- **`operation.history.read` in `workenv/journal.py`.** The journal now keeps each request's note
  (`rationale`) and the scopes its work names (`works_in`), in storage layout 6. The module
  docstring states the three rules (`D-20260928-202a51`):
  - A request acts in a scope when the scope is its owner, its target is the scope's id, or its
    work names the scope.
  - A scope's recent requests are the ones that start work: action `use`.
  - A checkpoint is the first record returned by a request that acts in the scope, when the person
    wrote a note with that request.
  - History offers only the recovery that reads: `query_same_request`.

## Which requests belong to a scope

C03 does not say. The rule was settled against the two V1 cases that read history, and it gives
exactly what both state.

- **REPO-NO-ENV:** no entries, and one checkpoint, which is the repository binding with its note.
- **UNKNOWN:** the start's compose and its activation, and one checkpoint, which is the
  preparation with the note written at the start. The case does not list the repository's
  binding or its source commits.

Four cases of later profiles also read history. No single rule meets all of them:

| Case | What its history states | Where it disagrees |
| --- | --- | --- |
| N16-C12-POS | the Team's founding, and no checkpoint | SHARED-UNKNOWN omits a founding of the same shape |
| TUI-ENTRY-SHARED-UNKNOWN | the unknown profile change only | the Team's founding is left out |
| TUI-ENTRY-TEAM-SCOPE | no entries, and one checkpoint noting an old goal | it omits the compose and activation UNKNOWN lists, and no request in it carries the note |
| N03-ENTRANCES-NEG | the unlock only | the lock, and handle issues after the unlock, are left out |

Their nodes restate them when they are built. `D-20260928-202a51` records this.

## The case drafts

Per `D-20260928-d6ff3a`, the restated cases are drafts until the P01 re-freeze. They live in the
workbench, `team-env-20260920/v1-slice5/`.

- `restate.py` writes each draft from the frozen spec, using named edits only. An edit whose
  anchor is not found exactly once stops the run.
- This increment makes two edits:
  - **probe**, in all seven cases (`D-20260928-09cd4b`). The `read` probe over MCP becomes
    `new_delivery` through `launch_instructions` 1 on `claude-code` 2.1.283. The observed text is
    the one the real probe recorded. The host configuration, the profile and every route outcome
    name that client, and a qualified start's outcome names `new_delivery`. Record and step names
    say `delivery` where they said `read`.
  - **frontier**, in TUI-ENTRY-UNKNOWN. Its preparation states no frontier for the Instructions
    pin, as FOCUS, KO-STATE and OPTIONS state none for the same shape.
- `runv1.py` runs every V1 case as the driver does, with a draft in place of the frozen scenario
  where one exists.

## How it was checked

- **Unit tests.** `test_routes.py` has 26 tests: offers, selections and history, through the
  journal. `WORKENV OK` was reached with everything staged.
- **Mutation sweep.** `v1-slice5/mutate5a.py` makes 39 mutations of `cli.py` and the journal. On
  the first run, four were missed. Each miss was a test gap, and each now has a test:
  - a question probe for a decide route;
  - a selection naming a record that is not an offer;
  - a payload whose `basis` is not a preparation's;
  - a noted request that returns two records.

  All 39 are caught now.
- **The V1 cases, with drafts** (`v1-slice5/runv1-inc1.txt`): 12 passed, 3 failed, 7 blocked.
  - The 3 failures are the ones the re-freeze already carries: DEL-PERSONAL, N15-C11-POS and
    CMP-QUALIFIED.
  - Six entrance cases now pass the given probe and the real `route.offer`, and stop at
    `surface.drive`, which is the next increment. REPO-NO-ENV also passes its real
    `operation.history.read`. With the frozen scenarios, the same cases stopped at the probe.
  - TUI-ENTRY-UNKNOWN is blocked before any step, on the driver's `event_reply_lost` feature
    (increment 4).
- **Controls on the cases.** Each break was reverted after its run.
  - Breaking the target clause of scope membership makes REPO-NO-ENV fail at `read_history`.
  - Breaking the action table makes the offers of N16, FOCUS and REPO-NO-ENV fail at their offer
    step.

## Found for the next increment

**N16-ENTRANCES-POS states the start differently from the other cases that state it.**

- In N16, Enter dispatches `route.select` itself. Its selection names a start request that no step
  submits, and the outcome's output is a digest the owner mints.
- Seven cases state it the other way: the six TUI entrance cases, and N16-C12-POS. In these, Enter
  dispatches `preparation.compose`, and `route.select` then names that request and answers with
  the preparation it returned.
- `route.select` follows the seven, so N16 is restated in the second increment, together with its
  trace values. Each entrance gets a compose step, and each trace dispatches and calls the
  compose request.

## What this does not show

- **Two parts are exercised only by unit tests.** Every case blocks before its `route.select`
  step, so no case exercises it yet. The same holds for UNKNOWN's history read.
- **The workbench's `home3` state is left at layout 5.** It is the fourth slice's evidence, and
  opening it with this code would migrate it to layout 6. The fifth slice's real use runs on a new
  state root.
