---
created_at: 2026-11-06T08:26:00+09:00
head: e44d63e
kind: design
supersedes: null
---

# S4 is bounded by its own seat, measures every attempt, closes a dead run, and holds what it reads to the records that wrote it

WP-09, commit 7: the fixes for review X round 2 (rework; F1 to F4, X's last round) and review W round 1 (rework; F1
to F5). This record covers:
- `g_problems`, `cluster_entries`, `from_cluster`, `origin_of`, `s3_outputs`, `processed_record`, `subject`,
  `population_problems`, `form_budget`, `tokens_of`, `bound_problems` and `run` in `session-distill/runlib/stage_form.py`;
- `read_rel` and the outputs S3 records, in `session-distill/runlib/stage_read.py`;
- `provenance_problems` in `session-distill/runlib/records.py`, called where every stage is admitted (`run_stage`);
- `Supervisor.item`'s `packet_check` in `session-distill/runlib/dispatch.py`;
- the S4 seat's capacity in `session-distill/seats.json`, and `session-distill/tables/form_capacity.json`;
- `session-distill/packets/form.md` and `session-distill/schemas/form.schema.json`.

The records of commits 5 and 6 (`2026-11-06T0650`, `T0741`) stay as written. Where this record differs from them, this
one describes the code from this commit on. In particular, commit 5's bound (rule (a) of S3's window bound, 112,109
bytes) is gone.

Two lead decisions are recorded with this commit: D-20261106-0765d5 (a producer's inputs are checked at admission) and
D-20261106-224fa3 (S4's bound is its own seat's capacity).

## X round 2

**F1: a cluster G cites three entries of its cluster, whatever claims are beside them.** A type G candidate that cites
entries of a placed cluster is on the cluster path. On it, at least three distinct entries the packet shows under the
cluster the candidate names are required, with or without claims. Before, one or two entries passed when three claims
were also cited, and such a candidate could rest on no event. Only a type G candidate with three such entries may have
empty `event_ids` (`from_cluster` now counts them). A type G candidate that cites no entry still needs three claims.

**F2: an origin is held to the immutable copy before it is shown, quotable or not.** `origin_of` now checks, in order:
- the copy's hash is the version the view names (`evidence.copy_problem`); otherwise `RECORD_INTEGRITY` naming the
  event and `SOURCE_TAMPERED`;
- each block's whole projected text is what the copy projects at that record (`evidence.projection_of`); otherwise
  `RECORD_INTEGRITY`.

Only then is a block made a quote. A block whose text names a secret (`EVIDENCE_QUOTE_SENSITIVE`) is shown and marked
not citable, as before, but now only after it has passed the same check. Before, that branch was taken before the
comparison, so an edited projection of a sensitive block was shown as the event's origin.

**F3: the packet states what entries do not show.** `form.md` now says that three entries let the model propose the
principle but do not show three independent lines of evidence, since entries may come from the same work, so the
evidence bar stays held. The schema's `tension` comment says the same.

**F4: an absent list is named.** `population_problems` first checks that each of the population's ten fields is
present and of its kind (`POPULATION_FIELDS`). One that is not is `SET_MISMATCH <field>: absent ...`, and nothing else
is judged. Before, a deleted `carried_forward` or `not_formed` raised `KeyError`.

## W round 1

**F1: a processed unit's read record is held to S3's record.** S3 now records each unit's read record
(`read/<unit>.json`, `stage_read.read_rel`) as one of its outputs. For every unit S3 processed (`read_complete`), S4
requires:
- S3's record holds that read record as an output;
- the file is that output byte for byte;
- it lists exactly the files the unit's result read (`readings`).

Otherwise S4 is refused by the unit's name (`RECORD_INTEGRITY`, or `SET_MISMATCH` for the file list). S4 also checks
that `read-results.json` is the one S3's record holds (`INPUT_INVALID S3`), so the read records are held to the record
of the same results. Before, a missing read record became an empty file list, and the unit's resolved events dropped
out with no refusal.

**F2: a producer's inputs are checked at admission (D-20261106-0765d5).** For each input a stage admits, the stage that
produced it recorded its own inputs with their digests. Where one of those is an artifact this stage also admits, the
two digests must be equal; otherwise the stage is refused, `INPUT_STALE <producer>: it read <artifact> at <digest>`.
- An output's digest says the producer wrote it and nothing changed it since. It does not say the producer read what
  is there now. S1 run again at the same declaration sequence left S3's results valid alone and stale beside the new
  census, and S4 admitted both.
- The check is in `records.run_stage`, so every stage keeps it. The S2 and S3 suites pass unchanged.
- It compares only artifacts the stage admits now. A producer's input the stage does not admit is not checked here.

**F3: every attempt is measured as it is sent.** `gate.correction` is unbounded, and a call without a view window is not
bounded by the dispatcher. So:
- `dispatch.Supervisor.item` takes `packet_check`, a function of the text an attempt would send. It is asked before each
  attempt is reserved. Failure lines stop the item by name, with nothing reserved for that attempt.
- S4 passes its bound as that function. The retry's packet, the payload with its correction, is measured as dispatch
  measures it.
- S4 is still admitted only with room for one correction (`stage_read.CORRECTION_ROOM`, 4,096 bytes). A correction
  larger than that room now refuses the retry (`FORM_OVER_BOUND S4: this attempt's packet ...`) instead of sending it.

**F4: a dead run's reservation is closed.** `stage_form.run` now calls `Supervisor.interrupted(S4)` right after
admission, under S4's stage lock and before any reuse or reservation, as `stage_read.run` does for S3:
- a reservation never dispatched is released unspent;
- a dispatched one's runner is stopped by its recorded identity, and the call is charged;
- a runner that may still be running (spawning, no identity recorded) refuses the run, `RESUME_HOST_UNVERIFIED`.

What was closed is in `form.json` as `interrupted`. Before, the open reservation made the next run's reservation
`CALIBRATION_SERIAL`, and S4 could not run again.

**F5: S4's bound is its own seat's capacity (D-20261106-224fa3).** `form_budget` reads:
- the S4 seat's context capacity, which seats.json declares with its basis (`gate.seat_capacity`), at the host version
  the dispatcher runs. No declared capacity is `FORM_CAPACITY_UNKNOWN`.
- the host's measured hermetic allowance (3,795 for Claude 2.1.317). None is `ALLOWANCE_UNMEASURED`.
- the output reservation the call declares, `OUTPUT_CAP` 32,000.
- the bytes a token covers, `tables/form_capacity.json`: 1.94, the fewest of the 1.94 to 2.19 that C1's six live
  S3 calls measured, so a packet's tokens are counted high.

A packet is within the bound when its driver bytes as tokens (rounded up), plus the allowance, plus the output
reservation, are at most the capacity (`bound_problems`). S3's window bound (`bound.INPUT_BOUND`) is not used.

Where the capacity comes from. Every live Claude result reports `modelUsage.contextWindow`, but no S4 call has been
made. The installed host caches its model catalogue (`~/.claude/cache/model-catalog`, the catalogue
`gates/check-model-currency.py` reads). On 2026-11-06 its entry for `claude-opus-5-5` gave
`runtime.max_input_tokens` 1,000,000 and `max_output_tokens` 128,000. Three of the seven catalogue files carry
`runtime`, and all three agree; the freshest was fetched at 2026-11-06T01:08+09:00. The same catalogue gives
`claude-sonnet-5-5` 1,000,000, which is that seat's measured `contextWindow` in seats.json. So seats.json now
declares `claude:claude-opus-5-5/high` at 1,000,000, host version 2.1.317, with that basis. No calibration call is
needed before the first live S4 call; that call's result carries a `contextWindow` to compare.

What this changes for C2. At 1,000,000 tokens the capacity admits a packet of about 1.87 MB of driver bytes with its
correction room. C2-pre estimated S4 at 43k to 88k input tokens, which commit 5's bound would have refused at its upper
end; this bound admits it. The packet's size is still measured and reported by the dry run before any call.

The two limits to know:
- 1.94 bytes a token was measured on S3 packets of the sonnet seat, not on a formation packet of the opus seat. The
  first live S4 call's driver bytes and reported input tokens give S4's own ratio.
- The capacity is the catalogue's statement, not yet a host-reported `contextWindow` of an opus call.

## Controls added

In `stage_form.py --self-test` (124 controls):
- X F1: a cluster G citing one, and two, entries beside three claims is `G_ANTI_ABSTRACTION` and, resting on no
  event, `CANDIDATE_WITHOUT_EVENTS`.
- X F2: an intact origin read as naming a secret is shown, cut as the stitch cut it, and not citable; the same origin
  with its projection edited is `RECORD_INTEGRITY`; an origin whose copy changed is refused with `SOURCE_TAMPERED`
  before it is read. The "names a secret" reading is planted by bending `projection.evidence_quote_admissible` for
  the control, so the golden fixture's origin takes that branch; the rule itself is held by projection's own suite.
- X F3: `form.md` and the schema state that three entries do not establish three independent lineages.
- X F4: `carried_forward` and `not_formed` deleted are each `SET_MISMATCH` by name.
- W F1: a processed unit's read record deleted, edited, cut to no file (with S3's record made to hold the cut
  record), or not held by S3's record, is refused by the unit's name; results that are not the ones S3's record holds
  are `INPUT_INVALID`.
- W F2: S1 run again at the same sequence under S3's results stops S4 at admission (`INPUT_STALE S3`), before any
  record of S4.
- W F3: with a bound narrowed to the admitted packet and its correction room, an answer naming a hundred unknown claim
  labels makes a correction larger than the room, and the retry is refused before it is reserved: one S4 call, the
  record failed. A bound one byte short of the packet with its room is refused at admission.
- W F4: a reservation left open by a dead run is released unspent and the call is made; a reservation marked
  dispatched and spawning, with no runner recorded, refuses the run with `RESUME_HOST_UNVERIFIED`, nothing sent.
- W F5: the limits are the seat's declared capacity with its basis, the allowance, the output cap and the fewest bytes
  per token; no capacity is `FORM_CAPACITY_UNKNOWN`; a packet that fills a capacity exactly passes and 100 bytes more
  are `FORM_OVER_BOUND`; a packet over S3's window bound and within the capacity passes.

In `records.py --self-test`: a consumer admitting what its producer read is admitted; the producer's input made again
at the same sequence is `INPUT_STALE`; an input whose producer read nothing the consumer admits is held to its own
record alone.

## Not covered

- The live call. The capacity and the byte-to-token ratio are the first things it can check.
- A dead S4 run whose runner is still alive is stopped by `stop.stop_recorded`, which dispatch's and S3's suites hold;
  S4's controls plant the never-dispatched and the unverified cases only.
