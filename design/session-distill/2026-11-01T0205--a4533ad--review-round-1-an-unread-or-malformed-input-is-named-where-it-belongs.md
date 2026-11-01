---
created_at: 2026-11-01T02:05:00+09:00
head: a4533ad
kind: design
supersedes: 2026-10-30T2300--b2c8ef1--an-inventory-answer-is-per-session-and-says-what-it-could-not-know.md
---

# Review round 1: an input the inventory could not read, or read in another shape, is named where it belongs

This record closes review round 1 of WP-07 package B. The round's reviewer judged `b8f4010` and returned `rework`
with seven findings, all `major` and all `reachable` (`wp07b-r1-review.json`, outside the repository). Five commits
on `wp/07b` answer them, `3ff97c5` through `a4533ad`. They change `session-distill/runlib/inventory.py` and
`session-distill/schemas/inventory.schema.json` only.

It follows `2026-10-30T2300--b2c8ef1--an-inventory-answer-is-per-session-and-says-what-it-could-not-know.md` (the
2300 record) on the WP-07 line, as that record followed package A's last, so the line stays one line. It amends
only the statements of the 2300 record that section 9 lists, and says what holds at `a4533ad` instead. The 2300
record stays as written and holds everywhere else. Two of the 2300 record's statements were already the rule and
were not what the code did at `b2c8ef1`; they are true since `c93a3d0` (sections 5 and 6).

The common thread. At `b2c8ef1` (whose product code is the reviewed `b8f4010`'s: the commits between them,
`c01fbe1`, `80d6cb4` and `b8f4010`, changed only the 2300 record and `inventory.py`'s `self_test`), seven findings
of six kinds gave a confident answer where an input had not been read, had been read in a shape its writer does not
write, or did not belong to the session being answered:
- a document member the schema never declared;
- a failure input the completeness test did not read;
- a delivered body's own units left out of its segment's context;
- a Codex pin's body as a session's current injection;
- an upper bound admitted after an earlier backward step;
- a malformed file of the owner's state, which refused the whole run instead of being that input's failure.

Each is now a declared key or code on the record it belongs to.

## 1. What it records

| finding | commit | what changed |
| --- | --- | --- |
| #5 | `3ff97c5` | `current.json` and `selection.json` are judged whole against their own schema roots, which now declare `reference`, `produced_by` and `renames` |
| #2, #3, A | `d91164b` | completeness reads every failure input: an AutoMem member with no usable path, an unread main transcript, a carrier version the store did not split |
| #0 | `7641125` | a mapped injection occurrence's recorded version is in its segment's universe; the cross check counts an inventory's carriers as the producer does |
| #1, #4 | `c93a3d0` | a Codex `--pin`'s `current` injection is `unknown: id_space`; an undated event's upper bound needs no backward step anywhere before it |
| #6 | `a4533ad` | a malformed baseline, snapshot or census is its own input's failure, by a declared code or key |

`git diff --stat b8f4010 a4533ad`: 907 lines of `inventory.py` and 84 of the schema changed, 922 insertions and 69
deletions in all.

## 2. The published shape (amends the 2300 record's section 2)

`current.json` holds `document`, `closure_rule`, `reference`, `produced_by`, `units`, `unknown_entries`, `layers`,
`renames`, `scopes` and `scope_universe`, every one required by its schema root `current_document`. `selection.json`
holds the same but `scopes` and `scope_universe`, every one required by `selection_document`. At `b2c8ef1` both
documents published `reference`, `produced_by` and `renames`, and neither root declared them.
`document_contract_problems` kept only the members a reference point's root declared before validating, so any
member added beside the units and layer rows was never judged. Validated directly against its root, each document
was refused. That filter is deleted, and every document is validated whole (`3ff97c5`).

The three members, each a `$defs` entry the code's table is bound to, so a field the schema declares and the table
has no rule for is refused at emission:
- `reference_block` (`REFERENCE_TABLE`): `kind` (one of `UNIT_REFERENCES`), `complete`, `incomplete_reasons`, and
  `commit` or `content_ref` as the kind carries them (both optional).
- `reference_produced_by` (`PRODUCED_BY_TABLE`): `module`, `design`, `state_root` (string or null), and `notes`,
  closed over the fourteen `NOTE_KEYS`, each value a `note_tree`.
- `rename`: one closed row over the fields of both rename shapes (`RENAME_TABLE`, `RENAME_AMBIGUOUS_TABLE`),
  `unit_id` required. The schema policy has no `oneOf`, so each shape is held to its own fields by its table on the
  emission path, as the 2300 record's section 3.17 does for the limitation row.

`note_tree` is a producer note as `as_tree` emits it. Its objects take any string key, through a `^` key pattern
beside `additionalProperties: false`. Below the declared note keys, a note's shape belongs to its producer;
copying fourteen producer shapes into the schema would be a second copy of them. Such a pattern is an open object
that the closed-object lint does not see, so it is licensed to this one site as data: `CATCHALL_SITE =
"#/$defs/note_tree"`. `reference_schema_problems` refuses a pattern that matches every probe key anywhere else, or
one it cannot compile (`REFERENCE_CATCHALL_ELSEWHERE`). It also compares the schema's note keys with `NOTE_KEYS`,
the rename row's fields with the two tables', and the reference kinds with `UNIT_REFERENCES`, each side required
non-empty (`REFERENCE_NOTES_MISMATCH`, `REFERENCE_RENAME_MISMATCH`, `REFERENCE_KINDS_MISMATCH`).

`scope_universe`'s per-host row gains two counts, `memory_path_unusable` and `transcript_unread`, declared and
required by the schema. The row is now `no_scope`, `cwd_unreadable`, `memory_path_relative`,
`memory_path_unusable`, `global_excluded_by_launch`, `ineligible` and `transcript_unread` (`UNIVERSE_COUNTS`).

## 3. New reason keys and refusal codes

Reason keys (`UNKNOWN_REASONS`), each in the reason vocabulary control's expected set under "review round 1" and
driven by a document the suite writes:

| key | text | where it is published |
| --- | --- | --- |
| `memory_path_unusable` | "not an outcome: an AutoMem member records no usable path, so the directory it belongs to is unknown" | a count in `scope_universe`; `native_memory`'s current layer row |
| `transcript_unread` | "unknown: a main transcript of this host was not read, so a newer outcome it records for any scope is unknown" | a count in `scope_universe`; the four native layers' current rows |
| `carrier_malformed` | "incomplete: a carrier version this row names did not split, its text being malformed" | a release index row's reasons |
| `carrier_unsupported` | "incomplete: a carrier version this row names is of a form no splitter supports" | a release index row's reasons |
| `census_malformed` | "INPUT_UNACQUIRED: this run's S1 census is not the shape S1 writes, so no transcript is bound to a record here" | the native layers' rows, where an absent census's `census` is |

Refusal codes, each the first word of a refusal and never a published reason key:

| code | refuses | what it reaches |
| --- | --- | --- |
| `REFERENCE_CATCHALL_ELSEWHERE`, `REFERENCE_NOTES_MISMATCH`, `REFERENCE_RENAME_MISMATCH`, `REFERENCE_KINDS_MISMATCH` | a schema that disagrees with the code's reference tables, or a catch-all key pattern outside `note_tree` | the schema check (section 2) |
| `RELEASE_SPLIT_DIFFERS` | a complete release index row naming, as a member or as a mapped occurrence's recorded bytes, a version whose store `split` is not `split` | the run (`release_cross_problems`) |
| `BASELINE_MALFORMED` | a baseline `inventory.json` that is not an object, or one with an item that is not an object with a string `ref` | that baseline's failure row, category `malformed` |
| `SNAPSHOT_MALFORMED` | a verified snapshot whose `items`, `output.unavailable` or `output.instruction_text` is not the shape the store writes | that snapshot's failure, category `malformed` |

The 2300 record's section 4 lists "two reason keys beyond the contract's list"; there are now seven: those two and
the five above.

## 4. Completeness reads every failure input (#2, #3, decision A)

At `b2c8ef1` the completeness tests of three layers read some of their failure inputs and not others. Each answered
complete while an input it should have counted had failed.

An AutoMem member with no usable directory (#2, `d91164b`). A rejected `native_memory` member, its content
unusable, still names its directory, so that scope is answered and incomplete (S-6). A rejected member that names no
directory was dropped, and `native_memory` was published complete with the valid member's units. It is now counted
at its host: by `memory_path_relative` when its path is not absolute, as a valid member's is, and by the new
`memory_path_unusable` when it records no path at all. Both counts make `native_memory`'s current row incomplete
(`COUNTED_LAYERS`), the valid units kept.

An unread main transcript (decision A, option 1; `d91164b`, its loop `7641125`). A main transcript whose read is any
of `READ_FAILURES` (`unbound`, `binding_invalid`, `no_path`, `changed`, `unreadable`) may record a newer outcome for
any scope. It is counted per host as `transcript_unread` in `scope_universe`, and a host with only such a transcript
enters the universe. The count makes each of the four `SCOPED_LAYERS` (`native_global`, `native_project`,
`native_memory`, `native_undivided`) short of complete: `incomplete` with the read scopes' units kept, or `unknown`
when no scope of the layer answered. The row's reason reads `transcript_unread <n> at <host>: <text>`. A subagent
transcript is not counted, since no child outcome answers a scope. The count is not filtered by host (section 7).

A version the store did not split (#3, `d91164b`). The 2300 record's section 3.4 made a reference row split each
carrier alone. A release index row did not read that outcome: a segment whose member, or whose mapped occurrence's
recorded bytes, did not split published the row complete. `run` now builds the store first, and
`release_index(ctx, shared, store)` reads each named version's `split` from it, never computing it a second time.
A version that is `malformed` or `unsupported` makes the row `incomplete` by `carrier_malformed` or
`carrier_unsupported` (rank 3, beside `member_rejected`), the row keeping its source. `release_cross_problems`
refuses a complete row naming such a version (`RELEASE_SPLIT_DIFFERS`), reading the store directly.

## 5. A Codex `--pin` is evidence about the pin, never about a session's current injection (#1)

The 2300 record's section 3.3 puts `current`'s injection for a Codex `--pin` under `unknown: id_space`. At
`b2c8ef1` the code did not: `_selection_injection` answered `current`'s session injection from the pin's snapshot
for either host. A Codex `--pin` run with an equal-id rollout in the census published the layer complete, the pin's
body its units, while that rollout's own pin was `id_space`. Since `c93a3d0` it raises `unknown: id_space` when the
reference point is `current` and the snapshot's host is Codex. The selection reference point keeps the pin's
evidence, and a Claude `--pin` still answers `current` from its snapshot. Section 3.3's text is unchanged; it is now
what the code does.

## 6. An undated event's upper bound needs time order up to it (#4)

The 2300 record's section 3.15 admits one upper bound for an undated event: the instant of the first later record
of the same transcript with a supported instant, when its instants are non-decreasing up to it. At `b2c8ef1`,
`brackets` compared only the two supported instants on either side of the line. A transcript recording 12:00, 09:00,
an undated injection and 10:00 gave the undated event the bound 10:00. Another session's injection at 11:00 was then
taken as later, and answered `native_global` for it. Since `c93a3d0`, `brackets` admits the bound only when the
supported instants never step back from the transcript's first one up to and including the bounding record. The
bracketing of an undecodable line uses the same function, so the same rule. Section 3.15's text is unchanged; it is
now what the code does.

## 7. A delivered body's own units are in its segment's context (#0; amends section 3.8)

At `b2c8ef1` a segment's universe was its event members and the carriers of the inventory layers its rows point at.
A confirmed session injection's recorded bytes were in neither. Its units had no edges in the segment's context
set, its mentions of a native `CLAUDE.md` reached nothing there, and `published_closures` over the context set held
none of them.

Since `7641125`, `universe_of` adds, for each index row's `occurrence_refs`, the recorded version
`(carrier_id, version_sha256)` of each occurrence whose method is neither `unmapped` nor absent. An exact match's
recorded version is the selected body's own; a normalised match's is a version of its own. These are event members
of the universe, with their own edges. The context set's id is over every carrier version of the universe, so two
segments of one session whose native files and injection in force are equal share one `x-`. A segment whose
carriers differ in one version's bytes gets an `x-` of its own.

What an inventory contributes. An inventory's carriers in a universe are those of the layers its segments point at
(`universe_of`'s second part); every other carrier there is an event carrier with edges of its own. The producer
always counted so; the cross check (`context_cross_problems`) counted every carrier of every named inventory. The
two had never disagreed, because no event member was any inventory's carrier. An exact injection's recorded version
is also its selection inventory's `session_injection` carrier, a layer no segment points at, so once it was in the
universe the cross check refused every run with an exact delivery (`CONTEXT_EDGE_UNRESOLVED`). It now takes the
producer's definition per context set. A context set no segment names keeps every named carrier, and is refused as
`CONTEXT_SET_UNRESOLVED`.

## 8. A malformed input is that input's failure (#6)

The 2300 record's section 3.12 and S-25: a failure reaches the inventory of THAT baseline and the sessions naming
it, and nothing else. At `b2c8ef1` a file of the owner's state that parses as JSON of another shape than its
writer's escaped that rule:
- a baseline `inventory.json` of `[]` raised AttributeError out of `freeze_inputs`, and the run was refused
  (`RELEASE_INVENTORY_UNRESOLVED`); one with an item that is not an object raised TypeError in
  `shared_inventories`;
- a snapshot whose `output.unavailable` holds a row that is not an object raised TypeError in the emission, and the
  run was refused; one whose `instruction_text` is not a string was a selection `read`, with nothing delivered and
  nothing unknown;
- a census that is not an object, or holds a row that is not one, raised AttributeError out of `census_entries`,
  and one that is not JSON raised a decoding error (a ValueError) out of it by the same path. `run` catches
  `Unacquired` only, so the run ended with no manifest.

Since `a4533ad`:
- `baseline_items` refuses `BASELINE_MALFORMED`. `baseline_once` already turns a refusal into that baseline's
  failure row, so its release inventory is `unknown` by `input_failed (release_baseline: malformed)` and every
  other inventory publishes.
- `snapshot_shape`, after the store's `verify_snapshot`, refuses `SNAPSHOT_MALFORMED` unless `items` is a list of
  objects with a string `ref`, `output.unavailable` a list of objects with string `ref`, `surface` and `reason`,
  and `output.instruction_text` a string. These are the parts this module reads and the verifier does not check.
  The snapshot fails, which reaches the sessions naming it (`input_failed`) and a `--pin` naming it (its snapshot
  omission row, `failed`, `malformed`). Whether an unavailable `ref` is one of the snapshot's items stays the
  emission's refusal.
- `census_entries` raises `census_malformed` for a census that is not JSON, not an object, whose `transcripts` is
  not a list, or that holds a row that is not an object. The census is unusable as a whole, since a row skipped
  would be a session nobody counted (decision D). `run` and `bind_transcripts` turn that into the transcript layers'
  named unknown, and the run publishes. S1 always writes `transcripts` (`runlib/census.py`).

Readers left as they were, because their callers already isolate a failure per input: `read_pin` (refused by name,
per session), the runtime state (an omission row), the ledger and the store's own state readers (a layer row), and
`transcript_records` (non-object lines counted).

## 9. Statements of the 2300 record this record amends

- Section 2, the table's `current.json` and `selection.json` rows: each also holds `document`, `reference`,
  `produced_by` and `renames`, all required by its root (section 2 here).
- Section 2 and section 3.11, `scope_universe` and "a layer row is complete only when every scope answers and those
  counts are zero": the counts include `memory_path_unusable` (native_memory) and `transcript_unread` (all four
  scoped layers), section 4.
- Section 3.4: besides a reference row, a release index row that names a version the store did not split is
  `incomplete` by `carrier_malformed` or `carrier_unsupported`, and a complete one is refused
  (`RELEASE_SPLIT_DIFFERS`), section 4.
- Section 3.8, "A context set's id is over every carrier version of its universe": the universe also holds each
  mapped injection occurrence's recorded version, and an inventory's carriers in it are those of the layers its
  segments point at, section 7.
- Section 3.16: a rejected AutoMem member whose path is relative counts as `memory_path_relative` too, and one with
  no path as `memory_path_unusable`, section 4.
- Section 4, "Two reason keys beyond the contract's list": seven, section 3.
- Section 6's reason-vocabulary residual counts keys by the documents that carry them (eighteen and 22). Those are
  `b2c8ef1`'s figures, not re-measured for the five new keys.
- Sections 3.3 and 3.15 are unchanged in text, and were not what the code did at `b2c8ef1`; sections 5 and 6 here.
- Section 3.12's chain: `input_failed` now also covers a malformed baseline or snapshot (section 8).

## 10. Residuals

- The three counts `no_scope`, `cwd_unreadable` and `transcript_unread` are keyed by reason, not by host. A count
  at one host leaves every listed native layer short of complete at every host. An unread Claude main transcript
  also makes Codex's native layers incomplete, and the reverse, and a Claude count reaches `native_undivided`, which
  no Claude transcript carries. It errs toward an unknown, never toward a wrong answer. Revisit when a host's scopes
  can be told apart from the count's source. Then every count is bound to its host in one change, never
  `transcript_unread` alone, which would make the three disagree.
- A census that is malformed as a whole leaves every transcript layer unknown, the sessions it would have bound
  included. A row skipped instead would be a session nobody counted (decision D's alternative, not taken).

## 11. Verification

Each commit had a dev pass of the inventory self-test, a pre-commit trial of its new and retargeted revert rows
with the unmutated suite beside them, and the commit hook, under the owner's verification rules of 2026-10-30.
Every new row failed by its own control's name, with no self-test section cut short, and each commit's hook passed
with no failing control. The claims for each commit, checked against the commit by the lead, are outside the repository.

| commit | controls after (dev pass) | new revert rows |
| --- | --- | --- |
| `3ff97c5` | 1089, the dev pass on the bytes one change before the committed ones; that change adds no control (the comparison loop of `reference_schema_problems` respelled, the same comparison, so revert row L1's target occurs once) | R1-5a, R1-5b, R1-5c |
| `d91164b` | 1099 | R1-2, R1-3a, R1-3b, R1-Aa, R1-Ab |
| `7641125` | 1108 | R1-0a, R1-0b, R1-0c, R1-Aa-r, Y79-r (R1-Aa and Y79 retired) |
| `c93a3d0` | 1112 | R1-1, R1-4 |
| `a4533ad` | 1116 | R1-6a to R1-6g |

`a4533ad`'s pre-commit trial ran its unmutated suite beside five rows at once. That suite was not clean: two slow
fixture-git controls ("and the fixture git really was the program that did not answer", "the fixture git writes
its marker inside scratch when its parent's name is shell") failed in it and in each of those five rows, and in
neither of the two rows that ran after. The pair is a known failure under parallel load, recorded apart, and not
changed by this round. The lead ruled the dev pass of the same bytes, run alone (1116 controls, none failing), the
unmutated record for that commit.

The final revert sweep of every live row at this record's head, and the suites on a clean tree, are not in this
record.
