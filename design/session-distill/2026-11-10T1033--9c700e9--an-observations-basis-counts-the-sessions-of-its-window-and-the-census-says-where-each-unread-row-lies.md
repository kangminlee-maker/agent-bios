---
created_at: 2026-11-10T10:33:00+09:00
head: 9c700e9
kind: design
supersedes: null
---

# An observation's basis counts the sessions of its window, and the census says where each unread row lies

WP-08d, commit 1 (brief `work/lead/wp08d-brief.md`, lead decision D-20261106-208882). Pre-production analysis A2
(2026-11-06) found that `stage_read.observation_scope` counted every census row of a declared transcript source,
whether or not the row held a record of the window, and that an `unknown_provenance` row always counted as incomplete.
The owner's census keeps 36 such rows; 35 were last written before any recent window. So every basis settled
`incomplete`, and `observed`, `no occasion` and the effect ratio were never reached. C1's run 0708c read both of its
units whole and still settled `incomplete`, with 35 `unknown_provenance` causes. The decision: a row is in scope when
it has a record in the window, or when its overlap cannot be determined.

## What lands

| Piece | Where |
| --- | --- |
| Where an unread row lies against the window | `census.unread_overlap`, called from `census.build` |
| The rows that need it, and the values that mean "no record of the window" | `census.UNREAD_STATUSES`, `census.OUTSIDE` |
| Two new `window_overlap` values | `schemas/census.schema.json`: `before_window`, `undetermined` |
| The scope by window | `stage_read.observation_scope` |
| What the scope left out, counted | `read.json` `observations.outside_window` |

## Where each row's overlap comes from

The census already wrote `window_overlap` for every row it reads in full. These are the eligible rows and the members
of eligible roots. The value comes from their record timestamps (`coverage.Ownership`): `inside`, `straddles_start`,
`straddles_end`, `straddles_both` or `context_only`. That is unchanged.

The rows it does not read in full were left without a value. These are `unknown_provenance` rows (every reason:
`no_session_meta`, `child_without_parent`, `orphan_child`, `originator:*`, `agent-bios:unpinned`, `no_entrypoint`,
`no_timestamps`), `unreadable` rows, and the `child_of` members of such roots. `census.unread_overlap` now writes their
value from the best evidence each of the row's files gives, in this order:

1. **The file-time bound.** A file last modified before the window starts holds no record of the window. A record is
   written no earlier than its timestamp. When this decides every file of the row, the row is `before_window`.
2. **Record timestamps.** A file the bound cannot rule out is read to the end, complete lines only, as `read_full`
   reads it. The row then lies inside, across or outside the window by its timestamps (`overlap_of`). A file the bound
   decided counts as a file with records before the window.
3. **Undetermined.** A segment named with no path, a file that cannot be read (an unreadable rollout included), and a
   file with no timestamped record leave the row `undetermined`.

The same rule applies to Claude and Codex rows. A Codex thread in several files is judged over all its segments.

Rows with no value:

- **`excluded` rows and the members of excluded roots** stay without a value. They are out of every scope with their
  root, so the census does not look at them.
- **`known_absent` rows** stay without a value. They name a file that is gone, so nothing can be read.

The bound fails only where a record's timestamp is later than its writing (a skewed clock), or where a file's time was
set back by hand. Both are outside what the census can see.

## The scope by window

`observation_scope` keeps the shape the Q2 record gave it
(`2026-11-04T0232--fedc526--s3-judges-the-observations-the-pinned-ledger-holds-due-and-records-resolutions-it-can-derive-again.md`):
every declared transcript source, and every session of the window, a unit with every member. "Of the window" is now
the census's evidence.

**When a row is out of scope.** A row stands for its unit: the root and every `child_of` member, since S3 answers a
unit through its root. The row is out of scope only when every one of those files has a `window_overlap` in
`census.OUTSIDE` (`context_only` or `before_window`). So an `unknown_provenance` root last written before the window is
still in scope when one of its members holds a record of the window.

**What keeps a row in scope.** An `undetermined` overlap, or none at all (a census written before this commit), keeps
the row in scope. So an older run directory settles as it did before.

**What does not change.** A unit S3 read keeps its own status in the scope, so a unit of the window read partly,
failed or deferred still makes the basis `incomplete`. A unit S3 read that holds no record of the window — its
backlog only — is out by the same rule. Its readings are late evidence of their own windows (design §5.2), and they
are written under `late` with basis `incomplete`.

**What is counted.** `read.json` counts the rows that would have made the basis incomplete and were left out as
outside the window, by status and evidence (`outside_window`, for example `{"unknown_provenance/before_window": 35}`).

S2's `unowned` count and S3's carried events do not change the rule. The census counts unowned records only against
windows already run other than this one (Q4 of the same record), so no record of this window is unowned. A carried
event belongs to a unit, and the unit's row carries its overlap like any other row.

## Controls

census self-test:

- **"D-208882: an unread row lies against the window by its evidence ..."** — fourteen rows, Claude and Codex:
  - in the window: `inside`;
  - last written before it: `before_window`;
  - records before it, written in it: `context_only`;
  - no timestamp, written in it: `undetermined`;
  - no timestamp, written before it: `before_window`;
  - an unknown root out of the window whose member is in it: root `before_window`, member `inside`;
  - an excluded root and its member: no value;
  - an eligible row: `inside`;
  - unreadable rollouts written in and before the window: `undetermined` and `before_window`.
- **"D-208882: the census document with the new window_overlap values meets its schema and its sets add up"**.

stage_read self-test (rows written as the census writes them; no owner data is read):

- unknown rows outside the window leave a complete scope `source` and are counted;
- an unknown row with a record in the window makes it `incomplete` and is named;
- an `undetermined` row, and a row an older census left without a value, keep it `incomplete`;
- an unknown root out of the window with a member in it keeps it `incomplete`, named by the root;
- a unit of the window read partly still makes it `incomplete` beside rows outside the window;
- a unit S3 read with its backlog only, failed, does not block the window;
- **C1 0708c's shape** as a fixture: both units read whole, 35 unknown rows out of the window, the owner's reason
  mix; this settles `source`;
- **the analysis's replay** as a fixture: 36 rows out of the window settle `source`, and the same rows without
  evidence (as built) settle `incomplete` with all 36 named.

Each control fails by name when its fix alone is reverted. The pretrial (`work/impl/wp08d/pt8d-pretrial.py`, rowset 1,
over commit 1's tree) reverts one fix per row:

- **census rows:** the unread rows not looked at; no file-time bound; an unstamped file read as outside; unreadable
  rows not looked at; members of unknown roots skipped; the schema not extended. The census validates its document
  as it builds it, so the last is refused there (CENSUS_INVALID) and fails the schema's existing control by name;
- **stage_read rows:** every row counted; a row standing alone without its members; members only; `None` counted as
  outside; `undetermined` counted as outside; `read.json` without the count; and a fix that over-reaches, the units S3
  read leaving the scope with the rows outside the window, which the partly-read and failed-unit controls catch.

Every row is caught by the controls it names and by no other, with no traceback; the module suites pass unchanged.

## What this amends

| Record | Amended |
| --- | --- |
| Q2 of `2026-11-04T0232--fedc526--...` ("every session of the window in them") | A session is of the window when one of its unit's files may hold a record of it, by the census's `window_overlap`; an undetermined or missing overlap counts as in. |
| Item 7 of `2026-11-03T1250--4070468--a-run-reads-the-census-prefix-and-the-unit-is-a-root-with-every-descendant.md`, and plan WP-05's interface (`window_overlap ∈ {inside, straddles_start, straddles_end, context_only}`) | `window_overlap` also takes `before_window` and `undetermined`, and is written for the unread rows above as well as the rows read in full. |

## Closed

- Counting every census row of a declared source whether or not it holds a record of the window (as built,
  D-20261106-208882).
- Deciding the overlap in the scope (WP-08) by reading the files at S3. The census owns reading the sources. S3 reads
  the census document under the digest S1 recorded, so a second reading at S3 would judge files outside its pinned
  inputs.

Still open: the owner's Q2 question on read statuses (B3, an `observed` with a partial-basis mark), and the owner
classifying the three unknown originators (B1+).

Revisit when `undetermined` rows become a frequent cause of an incomplete basis in production, or when a clock skew
puts a record of the window in a file written before it.
