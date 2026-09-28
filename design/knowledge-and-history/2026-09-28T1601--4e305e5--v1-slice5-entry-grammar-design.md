---
created_at: 2026-09-28T16:01:14+09:00
head: 4e305e5
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260928-380689, D-20260928-d6ff3a, D-20260928-09cd4b
---

# V1, fifth slice, second increment: one entry grammar, and the cases restated to it

This is the second increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md):
the entry model (`workenv/tui.py`) and `surface.drive`. It fixes one grammar for the entry,
derived from SSOT S11. The seven V1 entrance cases are restated to that grammar as drafts, and
the P01 re-freeze at the end of the slice carries the restatements.

## Why the cases are restated

The seven cases were written separately, and they disagree about the same situation in thirteen
structural ways. The owner saw the full list on 2026-09-28. Examples:

- Which of the nine positions are drawn.
- Where focus starts.
- Whether an unqualified route is drawn, and as what.
- Whether the tool is drawn.
- Which effects the start action states.
- Which owner calls a frame records.
- What an exact link opens.

They also state labels that no record holds. Examples are a repository name the binding does not
carry, a person's name, a date in a case with no clock, and a client version this machine does
not have.

One model cannot meet them all, so the cases are restated. `D-20260928-380689` decides how they
are judged: the runner holds a trace to everything but its element labels.

## The judge: a trace is held without its labels

`gates/workenv/conformance/executor.py` holds a returned `surface_trace` to the stated one with
every element's `label` left out on both sides. Everything else is compared exactly:

- element ids, roles, focus, selection, execution and state;
- marks, `shown`, `refers_to`, `value` and effects;
- the view;
- calls and dispatched requests.

Once held, the trace the owner returned is the one later digests are taken over. Wording is held
by the entry model's own unit tests against its catalog.

## What the model reads

The entry model is a function. It takes the drive request, the `surface_script` and what the
owner holds, and returns the frames. It writes nothing.

- **The offer.** The latest route offer this installation holds from the script's entrance.
- **The positions.** For each position of the basis, the collection the owner holds, else the
  sources it holds there, each with its accepted revision.
- **The context.**
  - The repository binding of a selected repository: its remote, branch and commit.
  - The probe each offered route names.
  - The latest history answer the journal holds for the selected scope.

V1 has no owner operation that lists a scope's sources, so the model reads these kept records
directly. `calls` records the owner operations whose requests a frame names:

- The history read the frame draws the checkpoint and the unknown start from. It is cited by its
  held request, with `reads: inventory`, in the first frame that shows it.
- The request an input dispatches:
  - `preparation.compose` reads `bodies` when its basis applies any source, else `nothing`;
  - `operation.query` reads `nothing`.

The client a trace names is the entry model itself: `{"name": "agent-bios-entry", "version":
"1"}`. The version moves when the grammar does, as the preparation adapter's version does. It
is not the package's version, so a release does not change the cases.

## Views

| Entrance | First view |
| --- | --- |
| `studio_hub` | `hub` |
| every other entrance | `w01` |
| a script with a `link` | `w01`, with the link's `target`, `return_view` and draft |

- **`w02`** is the detail of one position. `return_view` is `w01`, and `target` is the position.
- **`selected_scope`** is the scope of the start route, else the actor's personal scope. Every
  view carries it.
- **`browse_scope`** is left out: V1 never browses another scope than the selected one.
- **`draft_request_id`** is the unknown start the history shows, while it is unknown. A link's
  draft takes its place.

## W01

The elements, in this order:

1. **`context.location`** (context). It refers to the selected scope. A repository's label comes
   from its binding (the remote's last path segment and the branch). A personal scope says it is
   this device.
2. **`context.checkpoint`** (context), when the history holds a checkpoint. It shows the last
   checkpoint's note as a note from when it was written, and it refers to that checkpoint's
   record.
3. **`result.draft`** (result, state `unknown`, or `partial`, or `pending` for a start still in
   review or executing) and **`action.check`** (action). Both are present when the history shows
   an unknown start, and both refer to that request.
4. **`positions.<layer>.<role>`** (selection). There is one for each layer of the basis: the
   selected scope's, then personal when that is another. Each layer has one for each role:
   Instructions, knowledge, memory. Each refers to its position, view `original`.
5. **`field.note`** (field), present with a start action. Its value is what was typed, kept
   exactly, and it goes with the start as the request's `rationale`. It is an optional note,
   not a goal or a task.
6. **`execution.tool`** (setting), present with a start action. Its value is the display name
   of the chosen route's host (`Claude Code`, `Codex CLI`). Its effect is `model_calls`.
7. **`blocker.<layer>.<action>`** (blocker, state `blocked`), one for each route the offer states
   is not qualified. It refers to the route, and its label says why and how to fix it.
8. **`action.start`** (action). It refers to the chosen start route. Its effects are
   `file_changes` and `model_calls`.
9. **`help.keys`** (help). It lists only the keys that do something on this frame.
10. **`result.start`** (result, state `pending`). It is appended after a start is dispatched, and
    it refers to that request.

## States and selection

S11 and the schema keep the proposed default, the person's choice, and focus as three facts.

| Position | State | Selection and marks |
| --- | --- | --- |
| A collection is held with entries switched on | `installed` (Instructions), `not_checked` (knowledge, memory) | `selected`, `[x]`: the person's recorded choice, which the composition applies |
| A collection is held and switched off, or has no entries | `checked_empty` | `none`, `[ ]` |
| No collection; an Instructions source with an accepted revision | `installed` | `suggested`, `[x]` and the catalog's suggestion mark: included in this start unless the person excludes it |
| No collection; a knowledge or memory source with an accepted revision | `not_checked` | `none`, `[ ]`: its body is read only for a task, so the start does not include it unless chosen |
| No collection; a source registered without an accepted revision | `configured` | `none`, `[ ]` |
| Nothing held | `checked_empty` | `none`, `[ ]` |

- **Space** changes the selection of a position whose sources have an accepted revision and no
  held collection. It moves between included and excluded, and the result is `selected` or
  `none`: after Space the choice is the person's.
- A position with a held collection is changed through that collection, not here.
- **The start pins** the accepted revision of every source whose position is included by this
  frame, and whose position the composition does not already apply through a collection. Pins
  follow element order.
- **The tool** is `suggested` with the suggestion mark until ← or → changes it. It is then
  `selected`, with no suggestion mark. ← and → do something only when the offer's qualified start
  routes name more than one host.

## Focus and keys

**Where focus starts:**

- on `action.check` when a start is unknown;
- else on the element a link targets;
- else on the first position;
- else on the first Tab stop.

**Tab stops** are, in element order: `action.check`, `field.note`, `execution.tool` (only when it
has alternatives) and `action.start`. Tab and Shift-Tab move to the next or previous stop, and
wrap.

| Key | What it does |
| --- | --- |
| ↓ / ↑ | Move through the positions. From outside them, ↓ goes to the first position and ↑ to the last. |
| Enter | On a position, opens `w02`. On `action.start`, starts (below). On `action.check`, dispatches `operation.query` for the unknown request. On a field, a setting or a blocker, it does nothing. |
| Esc | Returns to `return_view` and clears `target` and `return_view`, keeping focus and selection as they were. With no `return_view`, `w01` goes to the hub with `return_view` `w01`. |
| Space | As under "States and selection". |
| ← / → | Change the tool, as under "States and selection". |
| Text and paste | Go into a focused field, code point for code point, with no normalisation. Newlines and escape bytes are kept as data. Elsewhere they do nothing: no letter is a shortcut. |
| Backspace | Removes the field's last code point. |
| Resize | Moves the terminal and recomputes `shown`. |
| Locale | Changes the catalog's wording and marks. Ids, selections, states and values stay. |

**Enter on `action.start`:**

- While a start is unknown, nothing is dispatched. The start action shows `blocked`, and focus
  goes to `action.check`.
- Otherwise the model builds and dispatches one `preparation.compose`:
  - Its basis is the start route's scope, then the person's, with the pins above.
  - It declares `session.routing.activate`.
  - It carries the note as `rationale` when there is one.
  - The request states the drive request's actor and access generation, targets the person, and
    has an id the model mints.
- The start action is `executing` and `pending`, and `result.start` is appended.

**A dispatched action.** Every dispatched action stays `executing` and `pending`, whether it is
a start or a check. A pure drive never receives the answer, so it shows none. The terminal (the
third increment) draws the answer when it comes.

## The hub, W02 and links

- **The hub.** Its elements are:
  - `context.location`;
  - `signal.draft` (signal, state `unknown`, marks `?`, referring to the request), when a start
    is unknown;
  - `job.prepare` (action), which opens `w01`;
  - `help.keys`.

  Focus starts on the signal, else the job. Enter on the signal opens `w01` with focus on
  `action.check`. The hub's jobs are the ones V1 serves; S11's other spokes arrive with their
  nodes.
- **W02.** Its elements are `context.location`, `detail.<layer>.<role>` (detail, focused, the
  position's state, referring to the position) and `help.keys`.
- **A link.** It opens `w01` with its target focused. Esc returns to its `return_view` and clears
  the target.

## `shown`

- Each element is one line: its marks, then its label. The line has `columns − 2` cells, because
  focus takes a two-cell gutter.
- A field's value follows on up to three wrapped lines.
- A cell count gives two cells to East Asian wide and fullwidth characters. Combining marks and
  Hangul medial and final jamo get none, and a control character gets two, because it is drawn
  as a caret pair.
- An element whose line or value is wider than that is `clipped`, and never shrunk.
- An element that starts below the last row is `off_screen`.

## The catalog

- `ko`, `en` and `ja` come from one table in `workenv/tui.py`: every label, and the suggestion
  mark.
- A unit test holds that the three locales name the same keys, and that no label carries S11's
  authoring questions or explains selection semantics.

## The cases, restated

`restate.py` makes these edits in the workbench drafts. Labels are left as each case states them
where the element survives. A new element states its Korean catalog label, which is not compared.

- **All seven:**
  - The trace client becomes `agent-bios-entry` 1.
  - W01 draws the six positions of a repository, or the three of a person.
  - W01 draws the note field and the tool.
  - Every unqualified route is a blocker.
  - The start effects are `file_changes` and `model_calls`.
  - `result.start` is `pending`.
  - Instructions with no collection are `suggested` with the suggestion mark.
  - Initial focus follows the rule above.
  - `calls` follow the rule above.
  - The dispatched request's id is minted by the entry, learned from the trace, and put into the
    compose step's request.
  - Scripts gain the Tab presses the note field adds before the start action.
- **ACCOUNT-FREE, FOCUS, OPTIONS, REPO-NO-ENV:** as above.
  - REPO-NO-ENV loses the `source.observe` call, because its frame draws nothing from that
    observation.
  - REPO-NO-ENV also loses `context.environment`.
  - Its checkpoint refers to the binding record.
- **KO-STATE:**
  - The binding observes a branch long enough that the location is clipped at 80 columns and
    whole at 100.
  - Its first frame focuses the first position.
- **OPTIONS' exact link:** It draws the whole of W01, with the start action focused.
- **UNKNOWN:**
  - The start's note is typed into the field. Before, it came from no input.
  - The reopened entry uses `result.draft`, `action.check` and the hub's `signal.draft`.
  - A dispatched check stays `executing`.
  - The Instructions frontier edit of the first increment stays.
- **N16-ENTRANCES-POS:** It is restated to the grammar the other six cases state.
  - Each entrance's offer gains a Codex start route, qualified by a given Codex `new_delivery`
    probe, so ← and → have a second host to choose.
  - The person holds one personal knowledge source, so Space has something to select in every
    entrance.
  - Each entrance's drive ends in `preparation.compose`, submitted as its own step, and
    `route.select` names that request.
  - The claim stays the case's own: choosing the environment leaves the tool, and choosing the
    tool leaves the environment.

## Not in this increment

- The terminal, which draws these frames and submits what they dispatch (the third increment).
- The driver's `event_reply_lost` feature, and who asks again after an unconfirmed start (the
  fourth).
- Any other hub job, `browse_scope` across Teams, and access-limited or locked frames (later
  nodes).
