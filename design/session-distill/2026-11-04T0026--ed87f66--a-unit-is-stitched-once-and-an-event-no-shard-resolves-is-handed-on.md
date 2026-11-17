---
created_at: 2026-11-04T00:26:00+09:00
head: ed87f66
kind: design
supersedes: null
---

# A unit is stitched once, and an event no shard resolves is handed on

WP-08 commit 3 (the plan's done-when 3 and 4, and plan amendment row 1). After every window of a unit's files has a
result, S3 makes one stitch for the unit: the events its reading left `pending`, and the ones an earlier run left
pending on its files, each joined to the claims recorded after it, or left `unresolved`. This record states what lands
and the choices made where the plan and design leave a gap. The implementer's five questions were answered by the lead
on 2026-11-04 (defaults approved, with the conditions below); the Q1 choice is D-20261104-88e68e. The code is
`session-distill/runlib/stage_read.py` (`Timeline`, `later`, `joinable_claims`, `shard_plan`, `stitch_problems`,
`Reader.stitch`, `current_events`), the packet `session-distill/packets/stitch.md`, the stored record
`session-distill/schemas/event.schema.json` with `runlib/claims.py`.

## What lands

| Part | Behaviour |
| --- | --- |
| When | A unit is stitched only when its reading finished (every window and expansion accepted, every own omission decided, every overlap row credited, no other version unresolved). A unit whose reading did not finish is not stitched and no call is made: it processes nothing, so nothing it could join would count. |
| What is listed | Every event of this reading still `pending`, and every coverage `pending_events` entry on a file of the unit (carried). Each event lists under `joinable` the claims it may join, each with its `quotes_after`. An event's own claims are never joinable to it. |
| Joinable | A claim with at least one quote of a record the run processes (in-window or backlog, never context) that stands after the event. A resolution cites at least one `quotes_after` and may cite the claim's other quotes beside it, such as an exposure the overlap shows (`joinable_claims`, `stitch_problems`). |
| Order | `Timeline`: a record's instant is S1's (`coverage.Ownership`: its own timestamp, else its predecessor's, a leading one the first that follows), kept at the latest at or before it within its session. Within a session a record stands by (segment order, line); across members by instant, an equal instant counting as after (`later`). A claim whose order against the event cannot be known - a member with no instant - is left out and counted per event (`unordered`). |
| Packets | Cut by what they measure: each shard's packet is rendered as it is sent, under the longest call id a retry can have, and its driver bytes, counted by `bound.driver_bytes` as dispatch counts them, kept within the bound the admitted declaration gives a view-window call less `CORRECTION_ROOM` (4,096 bytes) for the one retry's correction. S2's overhead plays no part. |
| Shards | `shard_plan`: events in groups whose own rows take at most half of what the bound leaves beside the packet's fixed part; each group gets the claims its events may join, in order, in shards whose measured packet fits. A group's events go through its shards in order: an event a shard resolves is not sent on, one whose claims fill a shard is carried to the next to see the rest, and one no shard resolves is `unresolved` by the last shard that listed it. A row that fits no shard is refused by name (STITCH_OVER_BOUND), and the unit is quarantined. |
| No claim to join | An event with no joinable claim is `unresolved` by code, with no call: the only answer a call could give. |
| The check | `stitch_problems` is the stitch's `stage_check` (the slot of commit 2b, with its one corrective retry): one resolution for each listed event and none for another (SET_MISMATCH), no repeat, a resolved one names claims and quotes and an unresolved one neither, every claim one the packet lists as joinable, every quote one of the claims it names, and at least one of them a `quotes_after` (RECORD_INTEGRITY). It reads only the attempt's answer. |
| A failed call | A shard's call the gate and the check refused twice decided nothing. No event of the stitch is written `unresolved`: every one stays pending and is named in the unit's record as undecided with the call (STITCH_CALL_FAILED), nothing of the stitch is appended or handed on, and the unit is `read_partial`, so its reading is read again. An `unresolved` from the model in an earlier shard is not final until the group's last shard has answered. |
| What is stored | Each decided event of this reading gets a second line in its file's event store: the same record with `outcome` resolved or unresolved and `stitched_from` naming the claims that resolved it (empty when unresolved), as `event.schema.json` states. `claim_ids` keeps the event's own claims. A carried event the stitch resolves gets a line of its own: `claim_ids` empty, `stitched_from` the resolving claims, `carried_from` its coverage origin `{window, first_record}`, `kind` "carried" and a description code writes. `claims.validate_record` allows an empty `claim_ids` only on such a line; an event of a run's own reading names a claim as before. A carried event left unresolved gets no line: it stays in coverage as it was. The store is append-only and digest-checked against the read records (EVENT_IMMUTABLE), as the claims' is; `current_events` is the one reader of an event's current state. The unit's read record holds the stitch: its calls with each attempt's check, the resolutions with the evidence ids and the call or code that decided each, the carried events not shown, the unordered counts, and each appended line's digest. |
| What is handed on | Only by a processed unit. An unresolved event of this reading becomes a pending event of its result, at its first record (`first_record`, 0-based) and the window of that record (§5.2: the run's window, or the window a backlog record is owed to). A carried event the stitch resolved becomes a resolved event of the result. |
| Carried events | Shown at their first record in this run's projection, each block cut to the overlap's 700 bytes and marked `"cut": true`, with `carried_from`. `coverage.observe` updates a version in place when a file was only appended to - its earlier records the new file's prefix - and adds a version when it was rewritten, so an event on an appended file keeps its version number and is shown, and one on a rewritten file, or whose first record holds no content block, is not shown, stays pending, and is named with its reason. |
| Event ids | Made from the run's name, the window's place and the answer's own id. They were made from the window's place alone, and the same local id in window 1 of the same view in two runs gave one id, so the next run's own event collided with the carried one. The call id is not used, since its attempt number would give one answer two ids. Claim ids, which do not leave their run, are unchanged. |

Removed: the reason "N pending events and no stitch call", which made every unit with a pending event `read_partial`.

## Choices made here

1. **A carried event is shown from this run's projection** (D-20261104-88e68e). Coverage's pending entry holds only
   `{id, transcript, version, window, first_record}`, by schema, and `session-distill/coverage.json` is tracked by
   git. Closed: writing the model's description into the coverage state, which would put the owner's session content
   into a tracked file; reading the earlier run's directory, which nothing keeps. Appended and rewritten files differ
   as stated above.
2. **The outcome rests on what the run processes.** Design §5.2: the stitch of a later run "joins them to outcome
   records it processes". At least one cited quote is of an in-window or backlog record after the event; a context
   quote may stand beside it (e6cb055 lets a claim rest on the overlap's exposure). An outcome shown only in the overlap
   after the window is read as context in run N and joined in run N+1, which is done-when 4. Closed: every cited quote
   processed, which refuses a sound resolution whose exposure is in the overlap; offering every later claim, under which
   run N would resolve on context.
3. **The order of members is by instant, and an unknown order is not "after".** An equal instant counts as after; a
   claim in a member without an instant is left out and counted. Closed: placing records with no instant at the
   earliest, which showed them before or after the event by accident.
4. **The shard rule carries an event from shard to shard.** The amendment's sentence - "an event is carried through
   the shards to the last one and is resolved there, or it ends unresolved" - is read as: an event goes through its
   group's shards in order until one resolves it, and is unresolved when the last has not. Closed: listing every event
   in every shard and deciding only in the last, whose call cannot see the claims of the shards before it.
5. **Shards are measured, not estimated.** Each packet is rendered and counted as dispatch counts it. Closed: cutting
   against the room a window's text gets (S2's overhead reservation), which estimates a stitch by a window's template.
6. **A call that failed decided nothing.** As a failed window does, it leaves the unit unprocessed, and its events are
   pending, never `unresolved`. Closed: processing the unit and handing undecided events on, which splits one reading
   between two runs and records a failure as a verdict.
7. **A carried event's line names its origin and no claim.** This run has none of the event's own claims. Closed: an
   empty `claim_ids` on any event, which would weaken the rule that a reading's event names a claim; a carried line
   copying the resolving claims into `claim_ids`, which mixes the cause's claims with the outcome's.

None of these reopens an owner decision or changes cost beyond the calls the plan counted (one stitch per unit, more
only when a unit needs shards).

## The packet

`packets/stitch.md` gains one paragraph and one phrase: the lists are one JSON object per line; an event names its
joinable claims, each with its `quotes_after`, and a resolution cites at least one of them, a claim's other quotes
beside; a carried event shows its first record; a `cut` text holds only its beginning. This changes what the model is
asked, for the X side of the review gate. Its fixed part leaves 4,860 of the 12,288 overhead bytes (`packet.py
--self-test`), a figure that no longer bounds the stitch.

## Controls (`stage_read.py --self-test`, 89 in all)

- done-when 3 (golden): a cause in window 1 whose outcome lands in window 5 (`fx_apart_records`) is resolved,
  `stitched_from` naming the outcome's claim and its evidence on the outcome window's record; the twin whose outcome
  window claims nothing of it is stitched by a call, left unresolved, and handed on at its first record.
- done-when 4: run N reads the outcome only as context, leaves the event unresolved by code with no call and hands it
  on; coverage, folded in the fixture alone, holds it; run N+1 (`views.golden(window=, state=, prefix_ok=)`), on the
  file the host appended to since - a new sha, the same version - shows it at its first record, joins it to the outcome
  N+1 processes with a context quote beside, hands it back resolved, writes its carried line, and coverage after N+1 no
  longer holds it.
- The shard rule, end to end under a bound 4,000 bytes above the packet's fixed part: three events, two shards; the
  event the first shard resolves is not in the second, the event whose claims fill the first is carried to the second
  and resolved there, the carried one is unresolved by its last shard, and every call's driver bytes, as dispatch
  recorded them, are within the bound. With the second shard's call failing twice, the event the first shard answered
  unresolved is not written unresolved, stays pending named undecided, and the unit is `read_partial`. `shard_plan` on
  its own: grouping, measured shards of only the joinable claims, and both STITCH_OVER_BOUND refusals.
- Run A: one stitch over the unit's own pending event and the carried one, in record order, the carried one shown at
  its first record; a first answer joining what is not joinable fails the check by its lines and is retried; the packet
  lists only joinable claims; the unresolved event is handed on and the carried one is not; window and stitch lines in
  the event store; EVENT_IMMUTABLE; the stitch's bound is the declaration's view-window bound less the correction room.
- Run B: a unit whose reading did not finish is not stitched and hands on nothing. Run F: a stitch whose two answers
  both join what is not listed leaves the unit `read_partial`, appends nothing, and names every event undecided.
- `stitch_problems`: one departure per rule, and a claim's other quote beside a `quotes_after` holds;
  `joinable_claims`: processed quotes after the event, an equal instant in another member, never the event's own claim,
  one before it or one quoting only context, and a member with no instant counted; `Timeline` and `later`: the leading
  fill, the running instant, the line order within a session, instants across members, unknown without one; a carried
  event on a rewritten file or with no block is not stitched and named; an event of a run's own reading with no claim
  is refused and only a carried line may name none; the stitch's check is pure on a read-only copy; the same window
  read by two runs gives two event ids.

## Not here

Observation instances and `derive_resolution` (commit 4), resumability (commit 5), the live legs of done-when 3 on the
real seat (commit 7). WP-09 (S4) reads the outcomes through `current_events`; a carried event's line has `kind`
"carried", since its kind is in the run that read its window.
