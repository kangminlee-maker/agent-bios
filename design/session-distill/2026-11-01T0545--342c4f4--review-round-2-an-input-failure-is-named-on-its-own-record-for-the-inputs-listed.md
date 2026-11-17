---
created_at: 2026-11-01T05:45:00+09:00
head: 342c4f4
kind: design
supersedes: 2026-11-01T0205--a4533ad--review-round-1-an-unread-or-malformed-input-is-named-where-it-belongs.md
---

# Review round 2: an input's failure is named on its own record, for the inputs and fields listed here

This record closes review round 2 of WP-07 package B. The round's reviewer judged `1bed32c` and returned `rework`
with four findings: three `major` and `reachable`, one `minor` and `impossible-condition` (`wp07b-r2-review.json`,
outside the repository). Four commits on `wp/07b`, `453270e` through `342c4f4`, answer them and one item the lead
added. They change `session-distill/runlib/inventory.py` and `session-distill/schemas/inventory.schema.json`
only.

It follows `2026-11-01T0205--a4533ad--review-round-1-an-unread-or-malformed-input-is-named-where-it-belongs.md` (the
0205 record) on the WP-07 line. It amends only the statements of the 0205 record that section 2 lists, and says
what holds at `342c4f4` instead. The 0205 record stays as written and holds everywhere else, and so does the 2300
record where the 0205 record left it standing.

The common thread. Two of the 0205 record's statements were wider than the code. "Completeness reads every failure
input" held for the inputs its section 4 lists, and not for a damaged or unmapped event's memory directories (#0).
"A malformed input is that input's failure" held for the shapes its section 8 lists, and not for an item's metadata
of another type (#1) or a census that could not be read (#2). This record makes no claim about inputs it does not
list: every "each" and "every" below ranges over a list given beside it.

## 1. What it records

| item | commit | what changed |
| --- | --- | --- |
| F (lead) | `453270e` | the self-test's slow fixture git runs once before its bound; a miss states its own times |
| #0 | `63394e7` | a damaged or unmapped event answers the memory directories it names, and is counted `memory_membership_unknown` |
| #1 | `7be5cac` | `item_problem` checks an item's consumed fields where it enters: the baseline, the snapshot, `item_carriers` |
| #2, #3 | `342c4f4` | the census is read once per run, a failed read is named; a catch-all is judged over all a site's patterns |

`git diff --stat 1bed32c 342c4f4`: 485 lines of `inventory.py` and 5 of the schema changed, 424 insertions and 66
deletions in all.

The commit that adds this record also corrects two comments of `inventory.py` that misstated what the code already
did. It changes no behaviour, and its hook runs the inventory self-test over those bytes:
- `scoped_layer`'s note on a layer row's status said the row is `unknown` "only when no scope of it answered at
  all". The code makes it `unknown` when no scope answered, or when its worst scope is unknown or uncertain;
  otherwise, a scope incomplete or a count alone, `incomplete`; either way the answering scopes' carriers are kept.
  The control written for #0 first expected `incomplete` from that note (section 4);
- `item_carriers`' docstring named a kind and a ref as what makes an item malformed. It is any consumed field of
  another type (section 5).

## 2. Statements of the 0205 record this record amends

- The introduction, "Each is now a declared key or code on the record it belongs to": for the six kinds it lists,
  as sections 2 to 8 there state them. Three more inputs of those kinds were not, and are since this round: a
  damaged or unmapped event's memory directories (section 4 here), an item's consumed fields of another type
  (section 5), and a census that cannot be read (section 6).
- Section 1's row for `d91164b`, "completeness reads every failure input", and section 4's title: completeness reads
  the failure inputs section 4 there lists (an AutoMem member with no usable path, an unread main transcript, a
  version the store did not split) and, since `63394e7`, an event whose AutoMem membership is not known (section 4
  here).
- Section 8's title, "A malformed input is that input's failure", and its "Since `a4533ad`" list: those are the
  shapes section 8 lists. Since `7be5cac` the baseline's and the snapshot's item checks are `item_problem`'s
  (section 5), and since `342c4f4` a census read that fails is the transcript layers' named unknown (section 6).
- Section 2, "`reference_schema_problems` refuses a pattern that matches every probe key anywhere else": it refuses
  a site whose patterns admit every probe key between them (section 7).
- Section 2's `scope_universe` row and section 4's counts: the row gains `memory_membership_unknown` (section 4).
- Section 3's table: two reason keys more (section 3 here); `BASELINE_MALFORMED` and `SNAPSHOT_MALFORMED` refuse an
  item `item_problem` names, each message naming the field.
- Section 9's line on the 2300 record's section 4, "seven": nine, the seven and the two in section 3 here.
- Section 11, the slow fixture-git pair "not changed by this round": changed in this round (section 8).

## 3. New reason keys

No refusal code is new. Reason keys (`UNKNOWN_REASONS`), each in the reason vocabulary control's expected set under
"review round 2" and driven by a document the suite writes:

| key | text | where it is published |
| --- | --- | --- |
| `memory_membership_unknown` | "not an outcome: an injection's AutoMem membership is not known (an unmapped member or an unusable container), so the memory directories it names are not all known" | a count in `scope_universe`; `native_memory`'s current layer row |
| `census_unreadable` | "INPUT_UNACQUIRED: this run's S1 census could not be read, so no transcript is bound to a record here" | the native layers' rows, where an absent census's `census` is |

`MALFORMED_ITEM`, an existing layer reason prefix, now reads `a <layer> item of another shape than the store writes
(<field>)` for every field `item_problem` names, `kind` and `ref` among them.

## 4. A damaged or unmapped event's memory directories (#0)

At `1bed32c`, `outcomes_of` answered an event's memory directories only when the event had no state. An event
with an unmapped member (`member_unmapped`) or an unusable container (`container_unusable`) answered its global
and project scopes with that state and no memory directory at all. A later event of that kind at another project
than an earlier valid AutoMem member left `current`'s `native_memory` complete with the earlier member's units, and
every count 0.

Since `63394e7`:
- every Claude event answers the memory directories it names, each answer carrying the event's state as its global
  and project answers do. A directory named by an unmapped event's usable members is that scope's unknown, by
  `member_unmapped`, its members evidence only;
- an event with a state also adds one `memory_membership_unknown` at its host: an unmapped member may belong to any
  directory, and an unusable container names none, so the directories the event names are not all it delivered.
  The count makes `native_memory`'s current row short of complete (`COUNTED_LAYERS`), the answering scopes' units
  kept. With a named directory unknown the row is `unknown`, by the existing rule for a layer with an unknown scope
  (S-20); with no directory named, the count alone makes it `incomplete`.

S-9's rule for a LATER event at the same project (`memory_membership`) is unchanged.

## 5. An item's consumed fields, checked where it enters (#1)

At `1bed32c`, `baseline_items` and `snapshot_shape` asked of each item only an object with a string `ref`. The other
fields this module reads were taken as the store writes them:
- a `package_id` of another type reached the store's emission, and `EMISSION_NOT_DECLARED_VALUE` refused the whole
  run, for a baseline item and a snapshot item alike;
- a rule's `body`, a member's content, an `origin` or a `primary_member` of another type failed a producer. The layer
  read `incomplete` by `not_admitted`, the valid items' units lost with the bad one's. Under a snapshot, the
  session's selection read `read`, from an inventory whose catalog held no unit.

Since `7be5cac`, `item_problem(item)` names the first of these of another type, or None:
- `kind` and `ref`: strings;
- `package_id`: absent, null or a string;
- `body`: a string for a rule; absent, null or a string for any other kind;
- `members`: absent, null or an object of strings;
- `primary_member`: absent, null or a string;
- `origin`: absent, or an object whose `source_path` is absent, null or a string.
These are the fields this module consumes, not the store's own validator, which requires every field the current
store writes and so could turn a baseline written by an earlier store unknown (decision H). The check is read at:
- `baseline_items`: `BASELINE_MALFORMED`, that baseline's failure row (`input_failed`, category `malformed`);
- `snapshot_shape`: `SNAPSHOT_MALFORMED`, that snapshot's failure (`input_failed` for the sessions naming it, a
  `--pin`'s omission row `failed`, `malformed`);
- `item_carriers`, for every other reader: `MALFORMED_ITEM`, its layer's declared reason; no carrier is handed on.

A snapshot item naming no `kind` is refused at the snapshot now, not in the selection's catalog layer: the self-test
control that asked the earlier rule keeps its fixture and asks this one ("... is that snapshot's failure,
SNAPSHOT_MALFORMED, never an exception's name").

## 6. The census, read once, and a read that fails (#2)

At `1bed32c`, a census that `is_file` and cannot be read (a permission error) raised an OSError out of
`census_entries`, past `run`'s `except Unacquired`, and the run ended with no manifest. A census gone between the
check and the read raised a FileNotFoundError out of it the same way. One run read its census three times: in `run`, in
`transcript_events`, and again in `bind_transcripts`.

Since `342c4f4`:
- `census_entries` maps a FileNotFoundError of the read to `census` (there is no census), any other OSError to
  `census_unreadable`, and a decoding error to `census_malformed` as before. The run publishes; the transcript
  layers carry the named unknown;
- `census_of(ctx, run_dir)` reads the census once and keeps the entries, or the Unacquired its read raised, in
  `ctx["census"]`. `run` and `bind_transcripts` take it, and `transcript_events` takes the entries it is given, so
  the readers of one run cannot see different bytes.

## 7. A catch-all judged over all a site's patterns (#3)

At `1bed32c`, `catchall_sites` judged each key pattern alone. Two patterns that each admit less, `^$` and `[\s\S]`,
together admit every key; planted in `rename`, they passed the guard, and a rename row with an undeclared member
validated. Since `342c4f4` a site is judged by the union of its patterns: a probe key is admitted when any of them
matches it, and a pattern this reader cannot compile still counts as admitting every key. A site is reported once.
On the checked-in schema the one site reported is `note_tree`, the licensed one.

## 8. The self-test's slow fixture git (lead's item F)

Two self-test controls read a marker the slow fixture git writes once it has started, under `tracked_paths`'
3-second bound: "and the fixture git really was the program that did not answer" and "the fixture git writes its
marker inside scratch when its parent's name is shell". In `a4533ad`'s pre-commit trial, six suites at once, they
failed in each suite that ran at that time and passed alone on the same bytes.

The one component measured is the first execution of a freshly written script: up to 0.5 seconds in six suites run
at once, and 0.01 seconds once it has run. That is less than the 3 seconds the trial read past, so that trial's
latency has a cause not determined. Since `453270e`:
- each fixture git runs once before its bound, outside it (`warm_start`, under 30 seconds), writing only a warm
  marker, so the 3-second bound times a program that has already run once. The bound is unchanged;
- two checks say the warm run happened and wrote only its warm marker, one per site;
- the pair's failure details state, in seconds from the start of each call, when the warm marker was written, when
  the bound fired, and when the slow marker was written, or that a marker is absent. A next miss says whether the
  bound fired early, the marker came late, or the fixture never started.
At `453270e`'s bytes the unmutated suite ran six times at once and passed every control; the pre-commit trials of
`7be5cac` and `342c4f4` ran six suites at once, and their unmutated suites were clean.

## 9. Residuals

Carried from the 0205 record's section 10, with one change:
- The counts `no_scope`, `cwd_unreadable`, `transcript_unread` and, since `63394e7`, `memory_membership_unknown` are
  keyed by reason, not bound to the scopes they could affect. A count at one host leaves every native layer it
  lists short of complete at every host. `memory_membership_unknown` lists `native_memory` only, and is not bound to
  the project it was recorded at either: one at any project leaves the layer row short of complete, every directory's
  scope row keeping its own answer. It errs toward an unknown, never toward a wrong answer. Revisit as the 0205
  record says: when a host's scopes can be told apart from a count's source, every count is bound in one change.
- A census that is malformed as a whole leaves every transcript layer unknown (decision D), and now so does one that
  cannot be read.

New:
- The driver checks, before the inventory runs, that the census is the artifact S1 recorded (its sha); that is a
  read of its own. A census changed between that check and the inventory's one read is not caught. Revisit when the
  inventory is handed the stage record's sha and can bind the bytes it read to it.
- `reason_problems` counts a key as reported wherever the source names `UNKNOWN_REASONS["<key>"]` or
  `reason("<key>")`, the self-test included. For a key a control names that way, removing the product's only report
  of it is not seen as `REASON_UNUSED`. Measured for `census_unreadable` in a pre-commit trial, where the reason
  vocabulary control, which asks what the suite's runs published, did fail. How many keys are in that position was
  not counted.

## 10. Verification

Each commit had a dev pass of the inventory self-test, a pre-commit trial of its new and retargeted revert rows
with the unmutated suite beside them, and the commit hook, under the owner's verification rules of 2026-10-30.
Every new and retargeted row failed by its own control's name, with no self-test section cut short, and each
commit's hook passed with no failing control. The claims for each commit, checked against the commit by the lead,
are outside the repository.

| commit | controls after (dev pass) | new revert rows | retargeted (retired) |
| --- | --- | --- | --- |
| `453270e` | 1118 | F-1, F-2 | |
| `63394e7` | 1121 | R2-0a, R2-0b | S7d-r, R1-2-r (S7d, R1-2) |
| `7be5cac` | 1125 | R2-1a, R2-1b, R2-1c, R2-1d | W1-r (W1); R1-6b retired to R2-1b |
| `342c4f4` | 1130 | R2-2a, R2-2b, R2-2c, R2-3 | R1-6e-r (R1-6e) |

A row is retargeted when its old text is gone and its protection stands: the same mutation at the new text, under
the control that now watches it. The commit adding this record changes comments only (section 1); its hook runs the
inventory self-test over the staged bytes. The final revert sweep of every live row at this record's head, and the suites on
a clean tree, are not in this record.
