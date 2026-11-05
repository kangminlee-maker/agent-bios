---
created_at: 2026-11-04T02:32:00+09:00
head: fedc526
kind: design
supersedes: null
---

# S3 judges the observations the pinned ledger holds due, and records resolutions it can derive again

WP-08 commit 4b connects S3 to the derivation commit 4a landed
(`2026-11-04T0212--dd8f9eb--a-window-resolution-is-derived-by-code-in-section-11-order-and-an-instance-is-eligible-or-unknown.md`).
The lead approved the five questions of commit 4 on 2026-11-04, each with a condition, and each section below names
its question. The plan amendment written with this commit
(`2026-11-04T0229--fedc526--plan-amendment-s3-reads-the-expected-observations-due-from-the-pinned-ledger.md`) withdraws
WP-21's seeds file.

## What lands

| Piece | Where |
| --- | --- |
| The pinned ledger, read from the declaration's checkout | `stage_read.pinned_ledger` |
| The expected observations due | `stage_read.due_observations` |
| Their text in the read packet | `stage_read.expected_text` |
| The search forcing expansions | `stage_read.searched`, `Reader.file` |
| One occasion judged once | `stage_read.answer_problems` |
| Instances kept when their quotes locate | `stage_read.keep` |
| The scope and its basis | `stage_read.observation_scope` |
| The instances and resolutions written | `stage_read.follow_up` |
| The reader that derives the resolutions again | `stage_read.stored_resolutions` |
| The incomplete statuses as one constant | `views.INCOMPLETE_STATUSES` |
| A checkout holding the ledger in every golden run | `views.golden(ledger_doc=)` |
| The premise of Q4, held where it is made | census self-test |

The commit also records D-20261104-1092d3 (Q1) and D-20261104-1f1083 (Q4).

## Q1: the due list is the pinned ledger's

S3 reads `design/session-distill/ledger.json` under the declaration's `destinations.checkout`. It reads the file only
when the file hashes to `starting_hashes.ledger`. These are refused by name:

- LEDGER_UNREADABLE: the file cannot be read;
- LEDGER_BASE_STALE: the file is not the pinned one;
- LEDGER_INVALID: the file does not hold under `ledger.validate_ledger`.

An expected observation is due when all of these hold:

- a decision of an earlier run holds it. A migrated element (`ledger.is_legacy`) is no run's decision, and a decision of
  this run, by the run directory's name, is not yet due;
- its expiry, a day, is not before the window's first day. An expiry that is no day is EXPECTED_EXPIRY_UNREADABLE.

The id is `<entry id>@<deciding run>`. A schema 1 ledger holds nothing due. So the owner's ledger holds nothing due
until the cutover, and the path runs on fixtures only (plan amendment of 2026-11-03, row 12).

**For C1 and the live legs.** A real declaration must pin the hash of the checkout's ledger, or S3 refuses
LEDGER_BASE_STALE before any call.

## The text the model sees (for review X of the live legs, commit 7)

The read template does not change. What fills its `{{expected}}` slot does. Before this commit the slot held only
`none`. Now each due observation is rendered as four lines:

```
- <entry id>@<run>
  occasion: <occasion_criteria>
  exposure rule: <exposure_rule>
  expected behaviour: <expected_behavior>
```

With nothing due, the slot still says `none`. The retrieval terms are never shown. Code searches the full source with
them and forces the expansions they match, so the model cannot be steered to a match by a term. The template's own
words about observations, unchanged since commit 1, ask for:

- every occasion in the owned records;
- `exposure` `eligible` if the window shows its exposure rule held before the decision or action, else
  `exposure_unknown`;
- `verdict` against the expected behaviour;
- the quotes showing both.

## Row 10: the search forces expansion

Before a window's decisions are checked, the reader searches each file's view with the union of the due observations'
retrieval terms (`views.forced_by_search`). Every own omission of a clipped record the search matches becomes
`must expand (search_match)`, in the packet and in the stage's check. An omission a pending event already forces keeps
`pending_event`. A skip of a search-forced omission is EXPANSION_SKIPPED, and the decision log records the forcing as
`search_match`.

A match clipped only in another window's overlap forces nothing. That record's own window shows it or decides it. The
file's read record counts the matches and lists the omissions they forced (`searched`).

## Instances

An observation of an accepted answer is kept when every one of its quotes locates. Otherwise it is dropped with its
code, as a claim is, and it is no instance. Its quotes' evidence is stored with the claims'. Its occasion is named
`<view name>#<entry>`. An answer that judges one occasion of one observation twice fails the stage's check
(RECORD_INTEGRITY).

## Q2: the scope is every declared transcript source and every session of the window

When every unit has been read, `observation_scope` builds the scope design §5.4 describes (plan amendment row 5):

- every declared transcript source; one that is unreadable or missing makes the basis incomplete (F04);
- every session of the window in them, a unit with every member:
  - a member's row is its unit's;
  - an excluded row is out of scope;
  - a unit S3 read ends with its own status, and is view and source complete when each of its files is;
  - a session owing nothing is complete.

`views.coverage_basis` sets the one basis, and every instance carries it.

**The consequence, for the owner, through the lead.** In production almost every window may hold one session read
partly, failed, deferred or unreadable. Then the basis is `incomplete` and `observed` stays `pending`, as design §11
and F04 say it must. So that this can be seen, `observations/resolutions.json` lists the resolutions left pending only
because the basis is incomplete (`pending_because_incomplete`). These are the ones that would not be pending on a
complete basis. The file also names the sessions and sources that made the basis incomplete. `read.json` counts both.
Revisit when production runs never reach `observed`.

## Q4: the share of unowned records owed to the window S3 reads is zero, and a census control holds it

The census counts unowned records only against the windows already run other than the one being run (`earlier` in
`census.build`, `w != window_id`). So no record owned by the window S3 reads is unowned, and `observation_scope` takes
no unowned input. Plan amendment row 5's unowned clause binds resolutions about earlier windows, which are WP-21's.

The premise is held by the census self-test control **"4b Q4: a census never counts the window it is run for among
the windows unowned records are owed to"**. It re-runs window 1 over the state the window's first run left, with a
file rewritten and one first seen since, and requires that none of their records be counted as unowned. Reverting the
exclusion fails it by name. D-20261104-1f1083 records the alternatives closed:

- pending every absence whenever any unowned record is reported;
- per-window counts in the census;
- a list of judged windows that S3 checks.

## Q5: a stored resolution is believed only after it is derived again

`observations/<window>.jsonl` holds the instances. `observations/resolutions.json` holds:

- the basis;
- each instance line's digest;
- each due observation's resolution;
- what made the basis incomplete.

Both files are the stage's recorded outputs. `stored_resolutions` derives each recorded resolution again from the
stored instances and basis before it returns them. These are refused by name:

- INSTANCE_IMMUTABLE: an instance line that is not the one recorded;
- RESOLUTION_DRIFT: a resolution its instances do not derive;
- RESOLUTION_DRIFT: instances of an observation with no resolution.

WP-21's close is the consumer that will read the file. Rendering and the ledger close stay WP-21's (plan amendment
row 6).

## Controls

The S3 self-test has 120 controls; 31 of them are this commit's.

- **A golden run with a schema 2 ledger of four expected observations:**
  - the packets list exactly the due one and the one due on its expiry's day, with their text, and no retrieval term;
  - the search forces the clipped record that holds the term, and not its twin with the same head and tail, and the
    decision log says `search_match`;
  - one instance is stored with basis `source`, its occasion qualified and its evidence stored;
  - the observation with a retyped quote is dropped as QUOTE_MISMATCH;
  - the resolutions are `observed` and `no_occasion`, and `read.json` counts them;
  - the instances and resolutions files are recorded outputs;
  - `stored_resolutions` believes them, and refuses three tamperings by name.
- **By themselves:**
  - the due rule over its cases: due, due on the expiry's day, expired, this run's, migrated, schema 1, an expiry that is
    no day;
  - the ledger pin read from a moved checkout, then stale, invalid and missing;
  - a search-forced omission skipped;
  - a pending event's forcing kept;
  - one occasion judged twice;
  - the scope complete, with one source unaccounted, and with one unit failed, each with its causes named;
  - an observed occasion in an incomplete scope counted as pending because incomplete, while one pending for its own
    reason is not.
- **Census:** the Q4 control above.

The pretrial (`work/impl/wp08/c4b/c4b-revert.py`, author-side) reverts each rule in turn. It runs the unmutated suites
whose bytes changed or that read what changed: stage_read, views, measures, evidence, claims, records and census.
