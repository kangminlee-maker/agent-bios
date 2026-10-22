---
created_at: 2026-10-22T19:49:00+09:00
head: 2c1235a
kind: design
supersedes: null
---

# Every layer of the inventory names its producer, and an empty answer is not an absent one

This record settles what WP-07 of `2026-10-20T2119--cc0498f--implementation-plan.md` decided while
building `session-distill/runlib/inventory.py` — S2's inventory of design §6.1. The plan, design
§6.1, §6.3 and §6.4 stand otherwise. It also names one tension between §6.1 and §6.4 that this
package did not resolve, because resolving it is WP-10's decision, not this one's.

## The layer and producer table is data

`LAYERS` in `session-distill/runlib/inventory.py` is one row per §6.1 layer, and each row names the
producer for each reference point. §6.1's four bullets become ten layers, so that a status is about
one carrier kind rather than a group: `catalog`, `adopted_packages`, `overlays`, `native_global`,
`native_project`, `native_settings`, `native_memory`, `session_injection`, `ledger_incubating`,
`ledger_keep`.

A layer is in `layers[]` of every reference point, with one of four statuses, and never absent:

- `complete` — every carrier the producer read split and reproduced byte for byte.
- `unsupported` — a carrier's structure is one the splitter cannot divide (a Python member that
  does not parse, a split that does not reproduce its carrier).
- `incomplete` — the producer ran and something it needed was missing or unreadable, **or** it read
  carriers and produced no unit. A layer is never silently empty: carriers without units is a
  defect, stated as one.
- `unknown` — no record of that layer exists at this reference point.

**An empty answer is not an absent one.** A producer that read its input and found nothing — no
adopted package installed, no personal overlay, no standing `keep` record — reports `complete` with
`units: 0` and `empty: true`. Only a producer that could not look at all reports `unknown`. Without
that distinction an owner with no personal overlay would make every reference point incomplete
forever, which would turn §6.4's every `gap` into `unknown` and empty the pipeline of findings.

## What the producers read, and what they will not read

- **Native layers.** The plan has them captured from the host homes at S0 into the run. No such
  capture exists yet: the declaration records a hash per layer (`starting_hashes.layers`), not the
  text. So the native producers read a capture root the caller names (`--native-root HOST=PATH`),
  or the live host homes when the caller passes **`--native-live`**, and otherwise report `unknown`
  with that reason. The live route is opt-in because the alternative — reading the owner's home by
  default — would make an inventory of a checkout read personal files nobody asked for.
- **Memory entries belong to a project.** A host home holds a memory directory for every project
  the owner ever opened; this run reads only `projects/<slug>/memory/*.md` for the project roots it
  was given (`--project`), where the slug is the project path with every non-alphanumeric character
  a dash, which is the layout the host uses. Sweeping every project read 1,287 carriers and 35,331
  units on this machine — neither this run's library nor reproducible.
- **Session-level injection exists per session.** At *selection* it is the pinned snapshot's
  compiled instruction text. At *current* it is the same text, when a pin names a session: "all
  layers now" can only mean the injection that session received. With no pin the layer is
  `unknown`, which is also what §6.3 says about a session without an activation pin.
- **Rules are one bullet line**, which is all the catalog compiler takes from `claude/CLAUDE.md`;
  every other kind carries its member files. One splitter serves all three reference points,
  because a catalog item, a baseline item and a snapshot item carry the same `members`,
  `primary_member` and `origin.source_path`.
- **The release reference point** comes from the pin's `inputs.baseline_ref` when there is a pin,
  and from the installed state's `selected_baseline_ref` when there is not, with the fallback named
  in the artifact's notes. §6.1's "unknown unless an install record maps the session's time to a
  baseline" is about a *session's* release; a library reference point with no session has the
  installed baseline as its record.

## The owner's state is read through frozen copies

`InstructionsStore`'s public methods — `status`, `list_items`, `snapshot_inventory` — take the
transaction lock and recover pending transactions. They write. So the overlay and snapshot
producers copy the few files they read (`runtime/state.json`, the baseline tuple, the pin, the
snapshot directory, the authoring state and its learning journals) and resolve over the copies
through the store's own non-locking internals (`_runtime_state`, `_user_state`,
`_effective_items`) and its module-level `verify_snapshot`. The native files the layers name are
copied the same way; a host's transcripts are never walked.

Every file under the state root and the authoring root is hashed before and after a run, and a
difference refuses the whole inventory by name, **`STATE_WRITTEN`**, rather than reporting a result
that came with a write. The control beside it calls the store's own recovering entry point on a
fixture state and shows the write the frozen route avoids.

## What the inventory joins, and what it does not run

The inventory loads two shipped modules by the path of the checkout it is reading — the catalog
loader and the store — so that the units it splits are the items the compiler would compile and the
overlays are the ones the store would resolve, rather than a second reading of either. Both are
declared in `session-distill/runlib/dispatch.py` `DYNAMIC_LOADS` as read and not traced, with the
reason each carries: the catalog loader runs nothing, and the one module it imports keeps its
executors in the installer's `main()`; the store runs no executor at all, and the importer its
`plan`, `apply` and install paths resolve by a module name no trace can read is a path the
inventory never calls. The module is also listed in `session-distill/tables/ledger_readers.json`,
because the ledger layer reads the ledger directly.

## Units, identity and context

- A unit is `{unit_id, layer, path, heading, n, text, sha, class}` as §6.1, plus
  `operative_context` and `version_sha256` as the plan asks; `class` carries §6.1's
  `operative|reference`, and `contract_problems` parses §6.1's own sentence out of the design
  rather than keeping a second copy of the list.
- `sha` is the fragment hash the plan calls `fragment_sha256`: one field, one authority. The same
  fragment in the same carrier at two reference points keeps one `unit_id` and one `sha`; what
  differs is `version_sha256` and `operative_context`.
- **`operative_context`** is the requirement set §6.3 asks a read to cover: the unit, its carrier's
  frontmatter (the trigger), the headings enclosing it (the exceptions), and the carriers its text
  names — which is how a context spans two guides. A mention that names a heading
  (`guides/second.md § Exceptions`) narrows to that heading's units; a mention without one stands
  for the named carrier's trigger. Nothing pulls in a whole other guide, because a requirement set
  that large would read as unread for every session.
- **A rename needs a requirement that moved.** `renames[]` pairs a unit with the unit id its
  fragment had at *release* when the carrier differs, and only for `operative` fragments that name
  one carrier on each side. The first rule tried matched the boilerplate heading every guide shares
  and reported twenty renames between two carriers that had nothing to do with each other.

## The release mapping is judged against the baseline file, not against itself

Every item of the baseline the *release* reference point names must carry at least one unit, and the
expected set is read from that baseline file again rather than from what the producer emitted:
`BASELINE_UNMAPPED <ref>` names the item that has none, and lands in the reference point's
`incomplete_reasons`. The control that plants a missing mapping asserts that the expected set it
judges against did not change with the mutation — a control that shrinks its own expected set
proves nothing, which is the trap the plan names for this package (F06).

On this machine the installed baseline holds 104 items and every one of them maps.

## Named and not resolved: whose completeness the gap rule reads

§6.1 says an unknown layer makes a reference point incomplete. §6.4 says an incomplete reference
point turns `gap` into `unknown`. Historical overlays and native layers are unknown by §6.1 itself,
so *release* is incomplete on every machine, and the two sentences together make every `gap`
`unknown` — which would leave §6.3's `not_delivered` unshowable, though §6.3 defines it as a state
the pipeline reports.

This package does not choose. The artifact carries the per-layer statuses as data and the reference
point's own flag exactly as §6.1 defines it, so either reading can be taken without reproducing the
inventory. The alternatives, for WP-10:

1. **The gap rule reads the layers in its own scope.** A library `gap` is judged against the
   `catalog` layer's completeness, not the whole reference point's. `not_delivered` stays showable;
   the flag keeps §6.1's meaning.
2. **The gap rule reads the reference point's flag**, as §6.4 says literally. Every `gap` at
   *release* is `unknown` until a historical native and overlay capture exists, and the pipeline
   proposes nothing from an absence.
3. **A capture makes the question go away.** The installer or the store records the overlay and
   native state per release, and *release* becomes completable. That is new machinery, outside
   WP-07 and WP-10.

Default if nobody decides: alternative 1, with the layer whose completeness was read named in every
absence claim.

## What this closes

- The native layers read from the host homes by default.
- Memory entries swept across every project in a host home.
- A layer reported as absent when its producer looked and found nothing.
- A rename map derived from any matching fragment.
- Resolving overlays or snapshots through a store method that locks or recovers.
