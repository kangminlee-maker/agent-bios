---
created_at: 2026-09-28T17:36:38+09:00
head: 4e305e5
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260928-380689, D-20260928-c4d88e, D-20260928-d6ff3a
---

# V1, fifth slice, second increment: the entry model, and the entrance cases restated to it

This is the second increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md),
built to the [16:01 entry grammar](2026-09-28T1601--4e305e5--v1-slice5-entry-grammar-design.md).
The entry model draws each frame and names the request an input dispatches. No terminal draws
its frames yet; that is the third increment. V1 is not complete, and no node is accepted by this
work.

## What was written

- **`workenv/tui.py`: the entry model and C12 `surface.drive`.** The module docstring states the
  grammar. The model reads what the owner keeps:
  - the latest route offer from the script's entrance, with each route's probe read now;
  - each position's held collection, else its sources and their accepted revisions;
  - the selected repository's binding;
  - the latest history answer held for the selected scope.

  It writes nothing. `surface.drive` answers `previewed` with the trace, and its dispatcher only
  records. The trace names the client `agent-bios-entry` 1.
- **The catalog.** `ko`, `en` and `ja` have the same keys and placeholders. Two labels were
  shortened so that every label carrying no held name fits one line of an 80-column terminal in
  all three locales:
  - the blocker, which says why a route is blocked and how to fix it;
  - the English label of an unknown start.

  Before, the blocker was 87 to 105 cells wide, and a case at 80 columns clipped it.
- **The payload.** `workenv/tui.py` is in `package.json` `files[]`, the ontology graph counts 124
  payload files, and `ONTOLOGY_MAP.html` is regenerated.

## The conformance machinery

- **The executor holds a trace without its labels** (`D-20260928-380689`). Everything else in a
  `surface_trace` is compared exactly. Later digests are taken over the trace the owner returned.
- **The scenario generator carries a minted request id into its answers.** An entry mints the id
  of a request it dispatches. A case states that id as `$req:<name>`, which its trace returns
  first.
  - The result and receipt of the request copy the request's id. Before, they copied the stand-in
    value and not the fact that it is minted. The executor then compared the stand-in with the
    real id and failed.
  - Now the copy keeps the minted join. `scenarios.py --check` shows no frozen scenario changes:
    162 specs, 0 problems.

## The case drafts

Per `D-20260928-d6ff3a`, the restated cases stay in the workbench until the P01 re-freeze:
`team-env-20260920/v1-slice5/`.

- `restate.py` now calls `entry.py`, which states each drive frame by frame, by hand:
  - where focus goes;
  - what is selected;
  - what is dispatched and called;
  - what is not shown whole.
- An element that survives keeps the label its case gave it. A new element takes the Korean
  catalog's label. N16's element ids all changed, so its labels are the catalog's.
- `$req:<name>` replaces the fixed id of each request an entry dispatches, in the trace, the
  compose request, the selection and the outcome.

What each case now states:

| Case | Restated |
| --- | --- |
| ACCOUNT-FREE | three personal positions, the note, the tool; Tab, Tab, Enter; the compose reads nothing |
| FOCUS | six positions; the decide route as a blocker; Instructions suggested; the note adds one Tab |
| REPO-NO-ENV | the history read is the only call on the first frame; no `source.observe` call and no environment element; the checkpoint refers to the binding |
| KO-STATE | the binding's branch makes the location clipped at 80 columns and whole at 100, in Korean and English; the note keeps the script's jamo as given |
| OPTIONS | the note adds one Tab; the exact link draws the whole of W01 with the start focused, and Esc clears its target |
| N16-ENTRANCES-POS | see below |
| UNKNOWN | the start's note is typed; the reopened entry focuses the check, Esc opens the hub and Enter on its signal returns; the check stays executing; the start is blocked and hands focus back |

- **OPTIONS' link.** The model reads the offer from the script's own entrance. The case now offers
  the start route to the `work_link` entrance before driving the link (`D-20260928-c4d88e`).
- **N16-ENTRANCES-POS.**
  - Each entrance's offer has a Codex start route first and a Claude Code route second. A
    given Codex `new_delivery` probe qualifies the Codex route. Codex is 0.157.1, the version on
    this machine.
  - The person holds one personal knowledge source. Its register and commit steps are copied from
    CMP-STORAGE's `my_tables`.
  - Each drive does the same things: it moves to that knowledge position, selects it with Space,
    moves to the tool, and changes it to Claude Code with the right arrow.
  - Enter then dispatches `preparation.compose`, pinning the knowledge revision. A compose step
    per entrance returns a preparation with that unit, and `route.select` names that request.
  - The hub entrance reaches W01 through its prepare job.
  - The number of ↓ presses differs by entrance, because each shows a different number of
    positions. The case's text no longer says the keys are the same.

## How it was checked

- **Unit tests.**
  - `test_tui.py` has 52 tests: catalog, cells, drawing, selection, keys, views, dispatch, unknown
    starts, `shown` and the pure preview.
  - `test_executor.py` has 87 tests, three of them new.
  - `test_scenarios.py` has 47 tests, one of them new.
  - `WORKENV OK`, `check-ontology` and `check-lexicon` passed with everything staged.
- **Mutation sweep.** `v1-slice5/mutate5b.py` makes 87 mutations: 82 of `tui.py`, 3 of the
  trace judge and 2 of the generator.
  - On the first runs, 6 were missed and 1 hung.
  - One miss was a condition no input could reach. A position a collection applies carries no
    pins, so `not position.collection` in Space changed nothing. The same condition in the pins
    was found while the mutations were written. Both were removed from the code.
  - The other five misses were test gaps, and each now has a test:
    - a committed start is no draft;
    - the marks count toward a line's width;
    - the compose carries the drive request's access generation;
    - the trace names the client literally;
    - a record of another kind, shaped like a trace, keeps its labels.
  - The mutation that hung was replaced by one that ends. Runs now time out at 180 seconds.
  - All 87 are caught now.
- **The V1 cases, with drafts** (`v1-slice5/runv1-inc2.txt`): 18 passed, 3 failed, 1 blocked.
  - All six entrance drafts that can run pass. N16 runs 19 steps.
  - The 3 failures are the ones the re-freeze already carries: DEL-PERSONAL, N15-C11-POS and
    CMP-QUALIFIED.
  - TUI-ENTRY-UNKNOWN is blocked on the driver's `event_reply_lost` feature (increment 4).
- **Controls on the cases** (`v1-slice5/control5b.py`). `tui.py` was restored after each run.
  - Leaving the person's layer out of the positions fails FOCUS and N16 at their drives.
  - Changing a catalog label fails neither.

## What this does not show

- **UNKNOWN's restated trace has not run.** It waits for increment 4. The unit tests exercise the
  same behaviour against a real unknown activation:
  - the draft and its focused check;
  - the query the check dispatches;
  - the blocked start;
  - the hub's signal.
- **No person has seen a frame.** The terminal is the third increment. Input-method composition
  on a real terminal is observed by TUI-OBS-KOREAN-TERMINAL, not by these cases.
- **A shifted element is reported indirectly.** When elements shift, the executor names the first
  minted value it cannot find. It does not name the shifted element. The failure is still at the
  drive step.
