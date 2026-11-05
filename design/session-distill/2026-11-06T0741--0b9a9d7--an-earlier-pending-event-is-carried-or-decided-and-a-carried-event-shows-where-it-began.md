---
created_at: 2026-11-06T07:41:00+09:00
head: 0b9a9d7
kind: design
supersedes: null
---

# An earlier pending event is carried or decided, a carried event shows where it began, a placed cluster can be a principle, and identical text in two places is a hint

WP-09, commit 6: the fixes for review X round 1 (rework, four major findings, F1 to F4) and the lead's rule for
identical text. This record covers:
- `subject`, `origin_of`, `population_problems`, `origin_evidence`, `lineages`, `evidence_bar`, `g_problems`,
  `from_cluster`, `answer_problems`, `FormLabels` and `run` in `session-distill/runlib/stage_form.py`;
- `relative_path`, `eligible_units`, `redundancy_pairs`, `upward_clusters` and `build` in
  `session-distill/runlib/lifecycle_intake.py`;
- `unit_files` in `session-distill/runlib/stage_read.py` (moved out of `stage_read.run`, so S4 joins a file to its unit
  as S3 does);
- `session-distill/schemas/form.schema.json`, `session-distill/schemas/intake.schema.json` and
  `session-distill/packets/form.md`.

The records of commits 2, 4 and 5 (`2026-11-06T0551`, `T0613`, `T0650`) stay as written. Where this record differs from
them, this one describes the code from this commit on.

Two lead decisions are recorded with this commit: D-20261106-bb8809 (a type G candidate from a placed cluster) and
D-20261106-b12b67 (where a resolved carried event began).

## F1: an earlier pending event never drops out

X found that a pending event an earlier run left on a file, which this run's stitch did not resolve, was in no list:
not a subject, not `carried_forward`. S4 now reads the coverage state S1 pinned (`coverage.json`, a new input) and
accounts for each earlier pending event of the window's units:

| The event's unit | Where the event goes | `why` |
|---|---|---|
| processed (`read_complete`), its stitch resolved the event | a subject event, with its origin (F3) | - |
| processed, its stitch did not resolve it | `carried_forward`, `origin: earlier_run` | `unresolved` |
| processed, its stitch left it unstitched | `carried_forward`, `origin: earlier_run` | `not_stitched` |
| not processed (`read_partial`, `deferred`, `failed`) | `carried_forward`, `origin: earlier_run` | `unit_not_formed` |

The events this run's processed units hand on are listed as before, `origin: this_run`, `why: unresolved`.

A processed unit's stitch must decide exactly the earlier pending events of its files: the carried resolutions and the
`not_stitched` rows together equal that set, and each event appears once. Otherwise S4 is refused,
`SET_MISMATCH <unit>: earlier runs left ... pending on its files`. A file is joined to its unit by
`stage_read.unit_files`, the function S3 itself uses.

The coverage state's pending events carry no run id, so `earlier_run` names no run. `pending_outside` counts the
pending events on files of no unit of this window. They belong to later windows and are not this window's to list.

`carried_forward` rows are `{event_id, unit, file, window, first_record, origin, why}`. The population's counts add
`carried_forward_why` and `pending_outside`.

## F2: a type G candidate from a placed cluster (D-20261106-bb8809)

X found that a placed cluster, which design §7.4 sends to S4 as a type G input, could never become a candidate: the
schema required an event, and an instance had to be a claim of this window. The lead decided:

- Each entry of a cluster has its own label, `u<n>.<m>` (`u1.1`, ...). The packet shows each entry with its lesson and
  where its stored evidence is (claim id, evidence id, locator, session, from the ledger).
- A type G candidate distilled from a cluster names the cluster in `tension.cluster` and cites at least three entries
  of that cluster in `tension.instance_entry_ids`. Entries of another cluster are no instances of it
  (`G_ANTI_ABSTRACTION`), and an entry label the packet does not show is `UNKNOWN_LABEL` and counts for nothing.
- Only such a candidate may have empty `event_ids`. Every other candidate with no event is `CANDIDATE_WITHOUT_EVENTS`.
- The same rule is stated in three places: the schema (`candidate_event_ids`, `entry_ids` and their comments), the
  packet (`form.md`) and the check (`g_problems`, `from_cluster`, `answer_problems`).
- The evidence bar (done-when 4) passes the entry ids to the lineage-count interface (`lineages`). The ledger's
  provenance records each entry's own lineages, not whether two entries share one, so the count is not known and the
  bar is `held` with that reason. For instance claims, S4 counts their S3 units as a disclosed stand-in until S5
  counts lineages (D6).

S4 now makes its call when the subject holds an event or the intake holds a placed cluster. A window whose units
resolved no event still forms from a cluster.

The alternative this closes: forming no cluster G until a claim of the current window supports it. That would make
§7.4's upward input reach S4 and never be formable on its own.

## F3: where a resolved carried event began (D-20261106-b12b67, option (가))

X found that an event an earlier window left open and this window's stitch resolved reached S4 with its outcome
claims only. The situation and the action are in its first record, which belongs to the earlier window, so S4 could not
judge `observed_event` or `causal_support` for it.

S4 now shows that first record as the event's `origin`:
- Its blocks are taken from this run's projection (`stage_read.projected_blocks`), each cut at 700 bytes
  (`views.OVERLAP_ITEM_BYTES`), exactly as S3's stitch showed them when it resolved the event.
- Each block is made an evidence record from the immutable copy (`evidence.make`, window role `context`) and held to
  the projection's text. Its packet label is a `q` label like any quote, and its stored id is
  `origin:<view>#<record>`.
- A first record the projection does not hold, or holds otherwise than the copy, is `RECORD_INTEGRITY` naming the
  event. S4 does not form from an event whose origin it cannot show.
- A block whose text names a secret cannot be stored as a quote (`EVIDENCE_QUOTE_SENSITIVE`). It is shown with
  `"citable": false` and cannot be cited.
- An origin quote an accepted answer cites is verified again (`evidence.verify`: the copy's hash, the locator, the
  projection's span) before `candidates.json` stores its evidence record under `origin_evidence`. One that no longer
  verifies is `RECORD_INTEGRITY`.
- `form.md` states the roles: origin quotes show the situation and what was done at that point; outcome claims show
  what came of it.

The limitation to know: the origin is cut at 700 bytes, so what was done may lie past the cut. In the golden fixture,
pe-1's first record is a long tool result (`views.fx_clipped`); the packet shows its first 700 bytes, marked
`"cut": true`, and the sentence planted in its middle lies past the cut. `form.md` tells the model so. The stitch saw the same 700 bytes when it
resolved the event, so S4 sees no less than the judgement it builds on.

The alternatives this closes:
- (나) S3 writes the run name into each pending event, and S4 reads the earlier run's claim store. That makes S4 depend
  on another run's directory, which may be gone or rewritten, and on a field the coverage state does not carry.
- (다) Refuse every resolved carried event whose origin cannot be found. S4 now shows the origin from this run's own
  projection, so the event is refused only when that projection fails its integrity check.

## F4: every list is held to its rows

X found that `population_problems` trusted the population's id lists, so a row could be removed while its id stayed.
Now each list is derived from the rows and must agree exactly:

- `candidate_ids`, `rejected_finding_ids` and `non_finding_ids` are exactly their rows' ids, in order;
- no candidate id is listed twice;
- the lifecycle rows are exactly the intake's candidates, each with the intake's source and no event;
- `event_membership` is exactly what the rows place, and names no candidate the population does not list;
- every event of the subject is placed exactly once, and nothing else is placed;
- `carried_forward` and `not_formed` equal the subject's;
- the counts are the ones the rows and the subject give (`population_counts`, the one place they are computed).

Each disagreement is `SET_MISMATCH` by name.

## Identical text in two places is a redundancy hint

Commit 4 folded identical texts into one unit before pairing. That treated a project file copied into several
checkouts and the same rule written in two different files alike. The lead's rule:

- Copies with the same relative path in the same layer are one file's copies: they are folded and counted
  (`identical_copies_folded`).
- Identical text with a different relative path, or in a different layer, is one redundancy candidate per group,
  `match: identical`, similarity 1.0, naming one unit of each place. It is not paired again as a near pair.

The relative path (`relative_path`), from inventory data:
- A native unit's path is recorded as `<host>:<type>:<path the host reported>` (`inventory.member_carrier`), and its
  `provenance.scope` is the session's working directory, masked as the path is. The reported path less the scope is
  the relative path, so `<HOME>/a/CLAUDE.md` and `<HOME>/a-wt/CLAUDE.md` read `CLAUDE.md` alike. A path outside the
  scope is kept whole.
- Every other layer's path is already the checkout's own (a catalog guide, `<ledger>#<entry>`, an overlay) and is
  used as it is.

The groups count toward the ceiling: `REDUNDANCY_OVER_CEILING` compares the near pairs plus the identical groups with
`tables/redundancy.json`'s ceiling of 200. The table is unchanged.

Over C2-pre w1's current inventory (counts only): 26,836 units; 19,675 of the excluded layer; 564 copies folded; 597
units below `min_keys`; 1,749 eligible; 101 identical groups, all within one layer (98 `native_project`, 3
`native_memory`), each of two places; 18 near pairs at 0.7. That is 119 hints, under the ceiling.

`lifecycle_intake.build` now validates `intake.json`'s document against its schema before it returns it
(`INTAKE_INVALID`).

## What S4 reads, now

`coverage.json` (S1) and `views.json` (S2) join S4's declared inputs, each pinned at admission to its producer's
record. `coverage.json` holds the earlier pending events (F1); `views.json` names each file's projection and immutable
copy (F3).

## Controls added

In `stage_form.py --self-test`:
- F1: the golden window's `carried_forward` holds the event its processed unit hands on and not pe-1, which the
  stitch resolved; an earlier pending event the stitch neither decided nor left unstitched, and one it decided twice,
  are each `SET_MISMATCH` naming the unit; an earlier pending event on a unit S3 did not process is carried forward
  as `unit_not_formed`; over two windows (`fx_two_windows`), the event run N left pending that run N+1 leaves
  unresolved is carried forward from the earlier run, and the one run N+1 joins is a subject with its origin.
- F2: a cluster G with no event and no claim passes the schema and the check and resolves to the entries' ids; two
  entries, entries of another cluster, and an unshown entry are refused; an eventless candidate that is not a cluster
  G is `CANDIDATE_WITHOUT_EVENTS`; entries on another type are `TENSION_OUTSIDE_G`; the packet shows each entry with
  its lesson and evidence; the evidence bar is `at_bar` for three units, `held` for two and `held` for entries.
- F2 at the stage: the golden plan adds a cluster G over the intake's placed cluster, formed with no event and an
  evidence bar held; a window whose subject holds no event still makes the call and forms the cluster G.
- F3: the packet shows pe-1's origin exactly as the stitch was shown it, cut at 700 bytes, while its description holds
  none of it; an origin quote is cited by its label and verified before `candidates.json` stores it; the golden plan
  cites one and `candidates.json` carries its record; a projection whose text differs from the copy, a projection
  missing the first record, and a copy changed after the subject was read are each `RECORD_INTEGRITY`.
- F4: one control per disagreement - a lifecycle, non-finding or rejected-finding row removed with its id kept; a
  membership redirected to another listed candidate; `carried_forward` or `not_formed` emptied; a count off by one; a
  lifecycle row under another source; a row listed twice; a lifecycle row the intake does not hold.

In `lifecycle_intake.py --self-test`: one file's copies in two checkouts are folded and are no hint; identical text in
two places is one hint at 1.0 and is paired no further; the ceiling counts a group as a hint; `build` refuses a
document its schema refuses.

## Not covered

- The live call is not made. The cluster G and the origin quotes are held through the golden host only.
- `fx_two_windows` builds run N+1 from run N's coverage state in one fixture tree. A real second run reads the coverage
  state S1 pins for it, which no control here makes.
- An origin block that names a secret is handled by `EVIDENCE_QUOTE_SENSITIVE`'s branch (shown, not citable). The
  golden fixture holds no such block, so that branch is held by reading the code, not by a control.
