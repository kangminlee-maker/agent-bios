---
created_at: 2026-11-06T06:13:00+09:00
head: 8c8493e
kind: design
supersedes: null
---

# The lifecycle intake is derived by code from five sources, each candidate by an id of its own

WP-09, commit 4 (plan WP-09 done-when 3). This record covers:
- `session-distill/runlib/lifecycle_intake.py` and `schemas/intake.schema.json`;
- `tables/redundancy.json`;
- the move of the schema 1 migration into `runlib/ledger_migration.py`.

The lead decisions it carries out, all from WP-09 stage 0:

| Decision | What it settles |
|---|---|
| D4 | the source of the legacy intake |
| D5 | the redundancy similarity and its scope |
| D6 (iii) to (v) | the G inputs |
| D7 | lifecycle candidates are formed by code and never sent to the model |

## Five sources, one id each

Every lifecycle candidate is `<source>:<target>`. So two candidates of one entry are two rows of the population, told
apart by id: for example, a legacy candidate of an incubating entry, and a redundancy candidate of the same entry's
`ledger_incubating` unit. The lead kept that layer in scope on purpose. S6 judges the two at once.

### `due_decision:<entry>@<run>`

- **What enters.** `ledger.unresolved_incubates` (commit 3) gives every incubate a run decided that no later decision
  resolves. Of those, an incubate whose expiry is on or before the window's last day enters.
  - The last day of a half-open window is the day before an end at midnight.
  - An incubate on a placed entry is a pending intervention. It enters too, marked `pending_intervention`.
- **What it carries.**
  - The decision it resolves.
  - The window's occasions for its observation: S3's instances in `observations/<window>.jsonl` (locator, exposure,
    verdict, basis) and the resolution in `observations/resolutions.json`.

### `legacy:<entry>`

Every `incubating` entry that has received no applied decision of a run enters, marked `legacy, observation unavailable`.
This holds in every run until such a decision arrives. The two scratch runs show it: once an entry receives an applied
decision, it enters neither as legacy nor as due.

The pin is read as S3 reads it (`stage_read.pinned_ledger`). A schema 1 pin is migrated in memory by the cutover's own
`migrate`, and its file is never written (D4).

To keep runlib from importing a script, the migration moved unchanged into `runlib/ledger_migration.py`:
`PREFIXES` through `migrate`, with `MigrationError`. `migrate-ledger.py` imports every one of those names, so its checks,
its reader inventory and its self-test are as they were. Both `--self-test` and `--check` pass in the worktree, 267
entries.

The self-test copies the repository's tracked ledger into a scratch checkout and checks three things:
- it is schema 1 and migrates in memory;
- every one of its `incubating` and `incubating-G` entries is a legacy candidate (142 today);
- its bytes are unchanged.

### `obsolete_hint:<unit>`

`obsolete_hints(index_rows)` reads rows of the occasion index S12 will write (WP-21): `{window_start, unit_id, matched,
basis}`. A unit becomes a hint when its latest windows end in at least three in a row that are of basis `source` and
have no match.
- A window of another basis breaks the run, as a match does. Design §7.1's "three consecutive windows of basis source"
  is read as consecutive source windows, not three source windows among others.
- The index does not exist. The rows are golden here. A run with no index takes no hint, and the intake's
  `notes.obsolete_hint` names WP-21.

### `redundancy_hint:<unit>|<unit>`

D5 is a normalised BM25.
- **Keys.** A unit's keys are those of the full-source search (`search.WORD`, `search.CJK` bigrams).
- **One direction.** Unit A's score over unit B, divided by A's score over itself.
- **The pair's similarity.** The smaller of the two directions. So a short unit whose every key a longer unit holds is
  no pair.
- **Which units.** Operative units of `inventory/current.json`, outside the layers `tables/redundancy.json` excludes.
  The only excluded layer is `native_undivided`, with its reason (the lead's scope decision).
- **The ceiling.** More pairs than the table's ceiling are refused (REDUNDANCY_OVER_CEILING), never cut.

**Two additions came from measurement, not from D5.** They are this implementer's proposal, and the lead is asked to
confirm or reject them before the X request:

1. **Identical text is folded.** Units of identical text (one fragment `sha`) are one instruction delivered by several
   carriers. They are folded into one before pairing, and the copies are counted.
2. **Short units are left out.** A unit with fewer than `min_keys` (3) distinct keys is left out, and counted.

The reason is what C2-pre w1's current inventory showed:

| Units in scope | Count |
|---|---|
| operative units outside `native_undivided` | 3,022 |
| distinct texts among them | 2,346 |
| identical copies (299 of them in `native_project`, the same project files in several worktrees) | 676 |
| one- or two-key units (JSON values, bare markers) | 532 |

Those 532 short units form one clique: 141,250 pairs at similarity 0.9 and above. Every threshold would then be refused
by the ceiling, and none of those pairs is an instruction anyone merges.

**The threshold** (`work/impl/wp09/logs/redundancy-measure-1.log` and `-2.log`):
- 40 units of this repository's shipped instructions (1,435 operative units) were each planted with four kinds of
  near-duplicate: one word changed, the last fifth dropped, the halves swapped, every fourth word dropped.
- Every planted variant scores 0.725 or more against its original.
- With folding and the floor, 0.7 pairs 13 units of the repository and 18 of w1. At 0.6 the counts are 32 and 40.
- The table fixes 0.7, with the ceiling 200 (about ten times w1's count).

At w1, folding and the floor leave 1,749 eligible units. The 18 pairs are:

| Layers of the pair | Pairs |
|---|---|
| catalog / catalog | 15 |
| native_project / native_project | 2 |
| native_memory / native_memory | 1 |

### `g_cluster:<unit>`

This is design §7.4's upward distillation, under D6 (iii)'s reading of "share retrieved principle text": the lead asked
that this reading be recorded and reviewed by X.
- **Retrieval.** Each placed learning's lesson and principle are a query over the same eligible units. The learning's
  top hit is the unit with the highest score; on a tie, the smallest id.
- **Clusters.** Placed learnings that share a top hit form a cluster when there are at least three.
- **Packet.** A cluster's lessons are what the formation packet shows under its `u` label. The model may propose the
  parent principle as a type G candidate (commit 1's `tension.cluster`).
- **Arc retrospectives.** None. The declaration has no field that names an arc, and `notes.g_cluster_arc` says so
  (D6 (iv)).
- **Correction clusters** are S4's own formation (D6 (v)). They are checked by commit 1's G_ANTI_ABSTRACTION, not by the
  intake.

At w1, with the owner's ledger migrated in memory, there are 3 clusters, of sizes 3, 4 and 4:
- two target `catalog` units;
- one targets a `ledger_incubating` unit: three placed learnings whose closest unit is an incubating learning's text.

## INTAKE_INCOMPLETE

`intake_problems(intake, sources)` holds an intake against a fresh derivation of every source, by id. It names:
- an id that a source derives and the intake lacks;
- an id the intake holds and no source derives;
- an id the intake holds twice.

## Counts at C2-pre w1

These are counts only. The intake's `notes` carry the exclusion counts so that C2's report shows them.

| Source | Count |
|---|---|
| due decisions (the ledger is schema 1, so no run decision exists) | 0 |
| legacy | 142 |
| obsolete hints (no index) | 0 |
| redundancy pairs | 18 |
| G clusters | 3 |
| units left out as `native_undivided` | 19,675 |
| identical copies folded | 676 |
| units below the floor | 597 |

The count below the floor is 597, not the 532 of the clique, because folding keeps the first unit of each text by id.

## Open

1. **Folding and the floor** await the lead's confirmation (above).
2. **An upward-distillation G candidate.** Commit 1's guard asks for three claim ids as instances. A G candidate that a
   placed cluster alone supports has its instances in the cluster's placed learnings, not in this window's claims. As
   the code stands, such a candidate is refused unless the window holds three claims. The question for X: should a
   cluster's placed learnings count as instances, and which of their evidence would a judge then read?
3. **The occasion index.** Its location and its writer are WP-21's. The rows here are an interface, not a file.

## Controls

`lifecycle_intake.py --self-test` holds 26 controls, and runs in the umbrella after S4 form's suite. The pretrial, in
three logs:

| Log | Rows | Result |
|---|---|---|
| `pt9-4.log` | 21: the none rows of the intake, migrate-ledger and S4 form; 18 rows that each revert one rule | — |
| `pt9-4b.log` | 3 | — |
| `pt9-4c.log` | every row again, after the fixture change | none rows PASS; the 18 reverting rows CAUGHT by name; traceback False |

Two rows missed in `pt9-4.log`: the reference unit and the excluded-layer units. The fixture's copies had identical
text, so folding hid them. The fixture was made to hold near-duplicates instead, and both rows were caught in
`pt9-4b.log`.

migrate-ledger's self-test needs a git repository, which the pretrial's copies are not (READERS_UNDISCOVERABLE). It ran in
the worktree and runs in the hook.
